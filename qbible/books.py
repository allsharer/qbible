"""Canonical Bible book metadata and book-name resolution.

Book metadata (stable ids, display names, URL slugs, testament, aliases) lives
in ``resources/books.json`` so that other clients (for example a future
Android app) can reuse exactly the same data.

Book ids are USFM/Paratext codes (``GEN`` … ``REV``). They never change, even
if display names are localised later.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import UnknownBookError

RESOURCES = Path(__file__).resolve().parent / "resources"

_ORDINAL_WORDS = {
    "first": "1", "1st": "1", "i": "1",
    "second": "2", "2nd": "2", "ii": "2",
    "third": "3", "3rd": "3", "iii": "3",
}
_ORDINAL_RE = re.compile(r"^(first|second|third|1st|2nd|3rd|iii|ii|i)\s+(?=[a-z])")
_PREFIX_MIN = 3


@dataclass(frozen=True)
class Book:
    id: str
    order: int
    name: str
    slug: str
    osis: str
    testament: str  # "OT" or "NT"
    aliases: tuple[str, ...]

    @property
    def singular_name(self) -> str:
        """Name used when referring to one chapter ("Psalm 23")."""
        return "Psalm" if self.id == "PSA" else self.name

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order": self.order,
            "name": self.name,
            "slug": self.slug,
            "osis": self.osis,
            "testament": self.testament,
        }


def book_key(text: str) -> str:
    """Normalise a book name for lookup: case, ordinals, spaces and dots."""
    t = text.strip().lower().replace("’", "'")
    t = re.sub(r"[. _]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    m = _ORDINAL_RE.match(t)
    if m:
        t = _ORDINAL_WORDS[m.group(1)] + t[m.end():]
    return re.sub(r"[\s'-]", "", t)


class BookCatalogue:
    """All known books, with alias lookup."""

    def __init__(self, books: list[Book]):
        self.books = tuple(sorted(books, key=lambda b: b.order))
        self._by_id = {b.id: b for b in self.books}
        self._by_slug = {b.slug: b for b in self.books}
        self._lookup: dict[str, Book] = {}
        for b in self.books:
            for key in {book_key(b.id), book_key(b.name), book_key(b.slug), book_key(b.osis),
                        *(book_key(a) for a in b.aliases)}:
                other = self._lookup.get(key)
                if other is not None and other is not b:
                    raise ValueError(f"Book alias {key!r} is ambiguous: {other.id} and {b.id}")
                self._lookup[key] = b
        self._names = [(book_key(b.name), b) for b in self.books]

    def __iter__(self):
        return iter(self.books)

    def __len__(self):
        return len(self.books)

    def get(self, book_id: str) -> Book:
        try:
            return self._by_id[book_id.upper()]
        except KeyError:
            raise UnknownBookError(f"Unknown book id: {book_id}") from None

    def by_slug(self, slug: str) -> Book | None:
        return self._by_slug.get(slug.lower())

    def exact(self, text: str) -> Book | None:
        """Resolve a full name, id or listed alias; no prefix guessing."""
        return self._lookup.get(book_key(text))

    def resolve(self, text: str) -> Book:
        """Resolve a user-entered book name.

        Exact names, ids and aliases are tried first. Otherwise an unambiguous
        prefix of a full book name (at least three characters) is accepted,
        e.g. ``Deuter`` or ``Philipp``. Ambiguous input raises
        :class:`UnknownBookError` listing the candidates.
        """
        key = book_key(text)
        if not key:
            raise UnknownBookError("No book name given.")
        book = self._lookup.get(key)
        if book:
            return book
        letters = re.sub(r"^\d", "", key)
        if len(letters) >= 2:
            matches = [b for k, b in self._names if k.startswith(key)]
            if len(matches) == 1 and len(letters) >= _PREFIX_MIN:
                return matches[0]
            if len(matches) > 1:
                names = ", ".join(b.name for b in matches)
                raise UnknownBookError(
                    f"'{text.strip()}' is ambiguous. Did you mean: {names}?", matches
                )
        raise UnknownBookError(f"Unknown book: '{text.strip()}'. Run 'qbible books' to list book names.")

    def alias_keys(self) -> list[tuple[str, Book]]:
        """Every exact lookup key (for reference detection in free text)."""
        return list(self._lookup.items())


@lru_cache(maxsize=1)
def catalogue() -> BookCatalogue:
    data = json.loads((RESOURCES / "books.json").read_text(encoding="utf-8"))
    return BookCatalogue(
        [
            Book(
                id=b["id"], order=b["order"], name=b["name"], slug=b["slug"], osis=b["osis"],
                testament=b["testament"], aliases=tuple(b["aliases"]),
            )
            for b in data["books"]
        ]
    )


@lru_cache(maxsize=4)
def reference_versification(name: str = "kjv") -> dict[str, list[int]]:
    """Expected verses-per-chapter table used to validate imported texts."""
    path = RESOURCES / "versification" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))["books"]
