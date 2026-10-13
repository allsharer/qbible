"""Application services shared by the CLI, interactive mode and web server.

Interfaces call :class:`BibleService` and never touch SQL, parsing rules or
formatting rules directly. JSON-ready dictionaries produced here define the
HTTP API payloads (see ``docs/API.md``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .books import Book, catalogue
from .config import Config
from .errors import ReferenceSyntaxError
from .paths import Locations, locations
from .reference import Passage, Reference, chapter_reference, find_references, parse, parse_key
from .repository import Repository, TranslationPack, Verse
from .search import SearchResult, search
from .textfmt import parts, plain, starts_paragraph
from .userdata import UserStore


@dataclass
class PassageView:
    translation: TranslationPack
    passage: Passage
    verses: list[Verse]
    previous: Reference | None
    next: Reference | None

    @property
    def reference(self) -> Reference:
        return self.passage.reference

    def to_dict(self) -> dict:
        p = self.passage
        book = p.book
        chapters: list[dict] = []
        for v in self.verses:
            if not chapters or chapters[-1]["chapter"] != v.chapter:
                chapters.append({"chapter": v.chapter, "verses": []})
            chapters[-1]["verses"].append(verse_dict(v))
        whole = p.reference.start_verse is None
        return {
            "translation": translation_summary(self.translation),
            "reference": {
                "key": p.key(),
                "display": p.display(),
                "book": book.to_dict(),
                "start": {"chapter": p.start[0], "verse": p.start[1]},
                "end": {"chapter": p.end[0], "verse": p.end[1]},
                "whole_chapters": whole,
                "chapter_verse_count": self.translation.verse_counts[book.id][p.start[0] - 1],
            },
            "chapters": chapters,
            "previous": nav_dict(self.previous),
            "next": nav_dict(self.next),
        }


def verse_dict(v: Verse) -> dict:
    return {
        "verse": v.verse,
        "text": plain(v.text),
        "raw": v.text,
        "paragraph": starts_paragraph(v.text),
        "parts": [p.to_dict() for p in parts(v.text)],
    }


def nav_dict(ref: Reference | None) -> dict | None:
    if ref is None:
        return None
    return {"key": ref.key(), "display": ref.display(), "book": ref.book.to_dict(),
            "chapter": ref.start_chapter}


def translation_summary(pack: TranslationPack) -> dict:
    i = pack.info()
    return {"id": i["id"], "name": i["name"], "abbreviation": i["abbreviation"]}


class BibleService:
    def __init__(self, repository: Repository, user: UserStore, config: Config | None = None,
                 default_translation: str | None = None):
        self.repo = repository
        self.user = user
        self.config = config
        self.default_translation = (
            default_translation
            or (config.get("reading.translation") if config else None)
            or "kjv"
        )

    @classmethod
    def from_environment(cls, locs: Locations | None = None) -> "BibleService":
        locs = locs or locations()
        config = Config(locs.config_file)
        return cls(Repository(locs.translation_dirs()), UserStore(locs.user_db), config)

    # -- translations -----------------------------------------------------------
    def pack(self, translation: str | None = None) -> TranslationPack:
        return self.repo.get(translation or self.default_translation)

    def translations(self) -> list[dict]:
        return [p.info() for p in self.repo.packs.values()]

    def books(self, translation: str | None = None) -> list[dict]:
        pack = self.pack(translation)
        return [
            {**b.to_dict(), "chapters": len(pack.verse_counts[b.id]), "verses": pack.verse_counts[b.id]}
            for b in pack.books
        ]

    # -- references ----------------------------------------------------------------
    def parse(self, text: str) -> Reference:
        return parse(text)

    def resolve(self, text: str, translation: str | None = None) -> Passage:
        return self.pack(translation).resolve(self.parse(text))

    def parse_any(self, text_or_key: str) -> Reference:
        """Accept either a human reference or a stable key (``JHN.3.16``)."""
        try:
            return parse_key(text_or_key)
        except Exception:
            return parse(text_or_key)

    def find_references(self, text: str, translation: str | None = None) -> list[dict]:
        pack = self.pack(translation)
        return [
            {"start": f.start, "end": f.end, "text": f.text, "key": f.reference.key(),
             "display": f.reference.display()}
            for f in find_references(text, pack.is_valid)
        ]

    # -- reading ---------------------------------------------------------------------
    def passage(self, ref: Reference | str, translation: str | None = None,
                *, whole_book_as_first_chapter: bool = False) -> PassageView:
        pack = self.pack(translation)
        if isinstance(ref, str):
            ref = self.parse_any(ref)
        if ref.is_whole_book and whole_book_as_first_chapter:
            ref = chapter_reference(ref.book, 1)
        p = pack.resolve(ref)
        verses = pack.passage_verses(p)
        prev = pack.adjacent_chapter(p.book, p.start[0], -1)
        nxt = pack.adjacent_chapter(p.book, p.end[0], 1)
        return PassageView(pack, p, verses, prev, nxt)

    def chapter(self, book: Book, chapter: int, translation: str | None = None) -> PassageView:
        return self.passage(chapter_reference(book, chapter), translation)

    def random_verse(self, translation: str | None = None, testament: str | None = None) -> PassageView:
        pack = self.pack(translation)
        v = pack.random_verse(testament)
        book = catalogue().get(v.book_id)
        return self.passage(Reference(book, v.chapter, v.verse, v.chapter, v.verse), translation)

    def step_from(self, ref: Reference, step: int, translation: str | None = None) -> Reference | None:
        pack = self.pack(translation)
        p = pack.resolve(ref)
        anchor = p.start[0] if step < 0 else p.end[0]
        return pack.adjacent_chapter(p.book, anchor, step)

    # -- search ------------------------------------------------------------------------
    def search(self, query: str, translation: str | None = None, *, book: str | None = None,
               **kw) -> SearchResult:
        pack = self.pack(translation)
        b = None
        if book:
            b = catalogue().resolve(book)
            if not pack.has_book(b):
                raise ReferenceSyntaxError(f"{b.name} is not in this translation.")
        return search(pack, query, book=b, **kw)

    def search_dict(self, result: SearchResult, translation: str | None = None) -> dict:
        pack = self.pack(translation)
        cat = catalogue()

        def ref_of(v: Verse) -> dict:
            b = cat.get(v.book_id)
            r = Reference(b, v.chapter, v.verse, v.chapter, v.verse)
            return {"key": r.key(), "display": r.display(), "book": b.to_dict(),
                    "chapter": v.chapter, "verse": v.verse}

        return {
            "translation": translation_summary(pack),
            "query": result.query,
            "mode": result.mode,
            "sort": result.sort,
            "terms": [t.describe() for t in result.terms],
            "total": result.total,
            "offset": result.offset,
            "limit": result.limit,
            "has_more": result.has_more,
            "results": [
                {
                    "reference": ref_of(h.verse),
                    "segments": h.segments,
                    "text": plain(h.verse.text),
                    "context_before": [{"reference": ref_of(v), "text": plain(v.text)} for v in h.context_before],
                    "context_after": [{"reference": ref_of(v), "text": plain(v.text)} for v in h.context_after],
                }
                for h in result.hits
            ],
        }
