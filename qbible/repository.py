"""Read-only access to translation packs.

:class:`Repository` discovers packs in the configured directories and exposes
them by translation id. :class:`TranslationPack` reads verses from one pack.
All SQL uses bound parameters.
"""

from __future__ import annotations

import random
import sqlite3
import threading
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from urllib.request import pathname2url

from .books import Book, catalogue
from .errors import DataError, TranslationNotFoundError
from .reference import Passage, Reference, chapter_reference, resolve
from .schema import PACK_FORMAT, PACK_SCHEMA_VERSION, verse_id


@dataclass(frozen=True)
class Verse:
    book_id: str
    chapter: int
    verse: int
    text: str


def open_readonly(path: Path) -> sqlite3.Connection:
    uri = "file:" + pathname2url(str(path.resolve())) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.execute("PRAGMA query_only = ON")
    return conn


def read_meta(path: Path) -> dict[str, str]:
    try:
        conn = open_readonly(path)
        try:
            return dict(conn.execute("SELECT key, value FROM meta"))
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise DataError(f"{path} is not a readable translation pack: {e}") from None


class TranslationPack:
    def __init__(self, path: Path, meta: dict[str, str] | None = None):
        self.path = Path(path)
        self.meta = meta if meta is not None else read_meta(self.path)
        if self.meta.get("format") != PACK_FORMAT:
            raise DataError(f"{self.path} is not a qbible translation pack.")
        try:
            version = int(self.meta.get("schema_version", "0"))
        except ValueError:
            version = 0
        if version != PACK_SCHEMA_VERSION:
            raise DataError(
                f"{self.path} uses pack schema {version}; this qbible supports {PACK_SCHEMA_VERSION}."
            )
        self.id = self.meta["id"]
        self._local = threading.local()

    # -- connection ------------------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            try:
                c = open_readonly(self.path)
            except sqlite3.Error as e:
                raise DataError(f"Cannot open {self.path}: {e}") from None
            self._local.conn = c
        return c

    # -- metadata --------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.meta.get("name", self.id)

    @property
    def abbreviation(self) -> str:
        return self.meta.get("abbreviation", self.id.upper())

    def info(self) -> dict:
        m = self.meta
        return {
            "id": self.id,
            "name": self.name,
            "abbreviation": self.abbreviation,
            "language": m.get("language", ""),
            "licence": m.get("licence", ""),
            "copyright": m.get("copyright", ""),
            "attribution": m.get("attribution", ""),
            "source_url": m.get("source_url", ""),
            "versification": m.get("versification", ""),
            "verse_count": int(m.get("verse_count", "0") or 0),
        }

    @cached_property
    def verse_counts(self) -> dict[str, list[int]]:
        counts: dict[str, list[int]] = {}
        for book_id, verses in self.conn.execute(
            "SELECT c.book_id, c.verses FROM chapters c JOIN books b ON b.id = c.book_id "
            "ORDER BY b.ord, c.chapter"
        ):
            counts.setdefault(book_id, []).append(verses)
        return counts

    @cached_property
    def books(self) -> list[Book]:
        cat = catalogue()
        return [cat.get(bid) for (bid,) in self.conn.execute("SELECT id FROM books ORDER BY ord")]

    @cached_property
    def _chapter_sequence(self) -> list[tuple[Book, int]]:
        return [(b, c) for b in self.books for c in range(1, len(self.verse_counts[b.id]) + 1)]

    @cached_property
    def _chapter_index(self) -> dict[tuple[str, int], int]:
        return {(b.id, c): i for i, (b, c) in enumerate(self._chapter_sequence)}

    def has_book(self, book: Book) -> bool:
        return book.id in self.verse_counts

    # -- retrieval -------------------------------------------------------------
    def resolve(self, ref: Reference) -> Passage:
        return resolve(ref, self.verse_counts)

    def passage_verses(self, passage: Passage) -> list[Verse]:
        b = passage.book
        lo = verse_id(b.order, *passage.start)
        hi = verse_id(b.order, *passage.end)
        rows = self.conn.execute(
            "SELECT book_id, chapter, verse, text FROM verses WHERE id BETWEEN ? AND ? ORDER BY id",
            (lo, hi),
        ).fetchall()
        return [Verse(*r) for r in rows]

    def verse(self, book: Book, chapter: int, verse: int) -> Verse | None:
        row = self.conn.execute(
            "SELECT book_id, chapter, verse, text FROM verses WHERE id = ?",
            (verse_id(book.order, chapter, verse),),
        ).fetchone()
        return Verse(*row) if row else None

    def verses_by_ids(self, ids: list[int]) -> dict[int, Verse]:
        out = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            marks = ",".join("?" * len(chunk))
            for row in self.conn.execute(
                f"SELECT id, book_id, chapter, verse, text FROM verses WHERE id IN ({marks})", chunk
            ):
                out[row[0]] = Verse(*row[1:])
        return out

    def is_valid(self, ref: Reference) -> bool:
        try:
            self.resolve(ref)
            return True
        except Exception:
            return False

    # -- navigation ------------------------------------------------------------
    def adjacent_chapter(self, book: Book, chapter: int, step: int) -> Reference | None:
        """The chapter before (step=-1) or after (step=1), crossing books."""
        seq = self._chapter_sequence
        i = self._chapter_index.get((book.id, chapter))
        if i is None:
            return None
        j = i + step
        if 0 <= j < len(seq):
            return chapter_reference(*seq[j])
        return None

    def random_verse(self, testament: str | None = None, rng: random.Random | None = None) -> Verse:
        rng = rng or random.SystemRandom()
        if testament:
            (n,) = self.conn.execute(
                "SELECT count(*) FROM verses v JOIN books b ON b.id = v.book_id WHERE b.testament = ?",
                (testament,),
            ).fetchone()
            k = rng.randrange(n)
            row = self.conn.execute(
                "SELECT v.book_id, v.chapter, v.verse, v.text FROM verses v JOIN books b ON b.id = v.book_id "
                "WHERE b.testament = ? ORDER BY v.id LIMIT 1 OFFSET ?",
                (testament, k),
            ).fetchone()
        else:
            (n,) = self.conn.execute("SELECT count(*) FROM verses").fetchone()
            row = self.conn.execute(
                "SELECT book_id, chapter, verse, text FROM verses ORDER BY id LIMIT 1 OFFSET ?",
                (rng.randrange(n),),
            ).fetchone()
        return Verse(*row)


class Repository:
    """All translation packs found in the given directories."""

    def __init__(self, directories: list[Path]):
        self.directories = [Path(d) for d in directories]
        self.packs: dict[str, TranslationPack] = {}
        self.problems: list[str] = []
        for d in self.directories:
            if not d.is_dir():
                continue
            for path in sorted(d.glob("*.sqlite")):
                try:
                    pack = TranslationPack(path)
                except (DataError, KeyError) as e:
                    self.problems.append(str(e))
                    continue
                self.packs.setdefault(pack.id, pack)  # earlier directories win

    def ids(self) -> list[str]:
        return list(self.packs)

    def get(self, translation_id: str) -> TranslationPack:
        pack = self.packs.get((translation_id or "").lower())
        if pack is None:
            if not self.packs:
                where = ", ".join(str(d) for d in self.directories)
                raise DataError(
                    "No Bible translations are installed. Build the KJV with "
                    f"'make data' (or 'qbible-build-data') or check the search path: {where}"
                )
            raise TranslationNotFoundError(
                f"Translation '{translation_id}' is not installed. Available: {', '.join(self.packs)}"
            )
        return pack
