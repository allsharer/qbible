"""Scripture reference parsing, validation, formatting and detection.

Parsing is translation-independent and produces a :class:`Reference`.
Resolution against a translation's versification (chapter and verse counts)
produces a :class:`Passage` with concrete start and end verses, or raises a
specific error. Invalid references are never clamped or redirected.

Supported input forms (case-insensitive, flexible spacing)::

    John                 whole book
    John 3               whole chapter
    Genesis 1-3          chapter range
    John 3:16            one verse      (also 3.16, 3 16, 3v16)
    John 3:16-21         verse range    (hyphen, en dash or em dash)
    Genesis 1:1-2:3      range across chapters
    Jude 3               verse 3 of a single-chapter book

Book names may be full names, ids (JHN), listed abbreviations, unambiguous
prefixes, numbered with digits, ordinals or Roman numerals (1 John, First
John, I John, 1Jn).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

from .books import Book, BookCatalogue, catalogue
from .errors import (
    InvalidChapterError,
    InvalidVerseError,
    ReferenceSyntaxError,
    UnknownBookError,
)

# Books with one chapter in every mainstream English versification. A bare
# number after these names is read as a verse ("Jude 3"), except "1"
# which means the whole (single) chapter.
SINGLE_CHAPTER_BOOKS = frozenset({"OBA", "PHM", "2JN", "3JN", "JUD"})

_DASHES = "‐‑‒–—―−"
_SPLIT_RE = re.compile(
    r"""^\s*
        (?P<book>(?:[1-3](?:st|nd|rd)?[\s.\-]*)?[^\d]+?)   # book name
        \s*\.?\s*
        (?P<nums>\d.*?)?                                 # chapter/verse part
        \s*$""",
    re.X | re.I,
)
_NUM_PATTERNS = [
    ("c", re.compile(r"^(\d+)$")),
    ("c-c", re.compile(r"^(\d+)-(\d+)$")),
    ("c:v", re.compile(r"^(\d+):(\d+)$")),
    ("c:v-v", re.compile(r"^(\d+):(\d+)-(\d+)$")),
    ("c:v-c:v", re.compile(r"^(\d+):(\d+)-(\d+):(\d+)$")),
]
_MAX_NUMBER = 999


@dataclass(frozen=True)
class Reference:
    """A parsed reference. ``None`` fields mean "the whole" book/chapter."""

    book: Book
    start_chapter: int | None = None
    start_verse: int | None = None
    end_chapter: int | None = None
    end_verse: int | None = None

    @property
    def is_whole_book(self) -> bool:
        return self.start_chapter is None

    @property
    def has_verses(self) -> bool:
        return self.start_verse is not None

    def key(self) -> str:
        """Stable machine key, e.g. ``JHN.3.16-JHN.3.21`` (see :func:`parse_key`)."""
        b = self.book.id
        if self.start_chapter is None:
            return b
        start = f"{b}.{self.start_chapter}" + (f".{self.start_verse}" if self.start_verse else "")
        if self.end_chapter is None or (
            self.end_chapter == self.start_chapter and self.end_verse == self.start_verse
        ):
            return start
        end = f"{b}.{self.end_chapter}" + (f".{self.end_verse}" if self.end_verse else "")
        return f"{start}-{end}"

    def display(self) -> str:
        return format_reference(self)


@dataclass(frozen=True)
class Passage:
    """A reference resolved against a translation: concrete, inclusive bounds."""

    reference: Reference
    start: tuple[int, int]  # (chapter, verse)
    end: tuple[int, int]

    @property
    def book(self) -> Book:
        return self.reference.book

    @property
    def chapters(self) -> range:
        return range(self.start[0], self.end[0] + 1)

    @property
    def is_single_chapter(self) -> bool:
        return self.start[0] == self.end[0]

    def display(self) -> str:
        return self.reference.display()

    def key(self) -> str:
        return self.reference.key()


# --------------------------------------------------------------------------- parsing


def _normalise_input(text: str) -> str:
    t = text.replace(" ", " ")
    for d in _DASHES:
        t = t.replace(d, "-")
    t = re.sub(r"\s+", " ", t).strip().rstrip(".;,")
    return t


def _normalise_numbers(nums: str) -> str:
    n = nums.strip().lower()
    n = re.sub(r"\s*([:.\-])\s*", r"\1", n)  # tidy around separators
    n = re.sub(r"(\d)\s*(?:vv?\.?|verses?)\s*(\d)", r"\1:\2", n)  # 3v16, 3 vv 16
    n = n.replace(".", ":")
    n = re.sub(r"^(\d+) (\d+)", r"\1:\2", n)  # "3 16" -> "3:16"
    n = re.sub(r"-(\d+) (\d+)$", r"-\1:\2", n)
    return n


def parse(text: str, books: BookCatalogue | None = None) -> Reference:
    """Parse ``text`` into a :class:`Reference` (not yet validated)."""
    books = books or catalogue()
    if text is None or not str(text).strip():
        raise ReferenceSyntaxError("Enter a scripture reference, for example 'John 3:16'.")
    raw = str(text)
    if len(raw) > 200:
        raise ReferenceSyntaxError("That reference is too long.")
    t = _normalise_input(raw)
    m = _SPLIT_RE.match(t)
    if not m or not re.search(r"[A-Za-z]", m.group("book") or ""):
        raise ReferenceSyntaxError(f"'{raw.strip()}' does not look like a scripture reference.")
    book = books.resolve(m.group("book"))
    nums = m.group("nums")
    if not nums:
        return Reference(book)

    n = _normalise_numbers(nums)
    if "," in n or ";" in n:
        raise ReferenceSyntaxError(
            "Lists of separate verses are not supported; use one reference or range at a time."
        )
    for kind, pat in _NUM_PATTERNS:
        mm = pat.match(n)
        if mm:
            vals = [int(x) for x in mm.groups()]
            break
    else:
        raise ReferenceSyntaxError(f"Cannot understand the chapter and verse part '{nums.strip()}'.")
    if any(v > _MAX_NUMBER for v in vals):
        raise ReferenceSyntaxError("Chapter and verse numbers must be below 1000.")
    if any(v == 0 for v in vals):
        raise ReferenceSyntaxError("Chapter and verse numbers start at 1.")

    single = book.id in SINGLE_CHAPTER_BOOKS
    if kind == "c":
        (c,) = vals
        if single and c != 1:
            return Reference(book, 1, c, 1, c)
        return Reference(book, c, None, c, None)
    if kind == "c-c":
        a, b = vals
        if single:
            return Reference(book, 1, a, 1, b)
        return Reference(book, a, None, b, None)
    if kind == "c:v":
        c, v = vals
        return Reference(book, c, v, c, v)
    if kind == "c:v-v":
        c, v1, v2 = vals
        return Reference(book, c, v1, c, v2)
    c1, v1, c2, v2 = vals
    return Reference(book, c1, v1, c2, v2)


def parse_key(key: str, books: BookCatalogue | None = None) -> Reference:
    """Inverse of :meth:`Reference.key`."""
    books = books or catalogue()
    m = re.fullmatch(
        r"([0-9A-Z]{3})(?:\.(\d+)(?:\.(\d+))?)?(?:-([0-9A-Z]{3})\.(\d+)(?:\.(\d+))?)?",
        key or "",
    )
    if not m:
        raise ReferenceSyntaxError(f"Invalid reference key: {key!r}")
    b, c1, v1, b2, c2, v2 = m.groups()
    book = books.get(b)
    if b2 and b2 != b:
        raise ReferenceSyntaxError("References spanning several books are not supported.")
    if c1 is None:
        return Reference(book)
    c1 = int(c1)
    v1 = int(v1) if v1 else None
    if c2 is None:
        return Reference(book, c1, v1, c1, v1)
    return Reference(book, c1, v1, int(c2), int(v2) if v2 else None)


# --------------------------------------------------------------------------- resolution


def resolve(ref: Reference, verse_counts: Mapping[str, Sequence[int]]) -> Passage:
    """Validate ``ref`` against a versification and return concrete bounds.

    ``verse_counts`` maps book id to a list of verse counts per chapter.
    """
    book = ref.book
    counts = verse_counts.get(book.id)
    if not counts:
        raise InvalidChapterError(f"{book.name} is not available in this translation.")
    n_ch = len(counts)

    def check_chapter(c: int) -> None:
        if c < 1 or c > n_ch:
            plural = "chapter" if n_ch == 1 else "chapters"
            raise InvalidChapterError(
                f"{book.name} has {n_ch} {plural}; there is no chapter {c}."
            )

    def check_verse(c: int, v: int) -> None:
        n = counts[c - 1]
        if v < 1 or v > n:
            raise InvalidVerseError(
                f"{_chapter_name(book, c)} has {n} verses; there is no verse {v}."
            )

    if ref.start_chapter is None:
        return Passage(ref, (1, 1), (n_ch, counts[-1]))

    sc, ec = ref.start_chapter, ref.end_chapter or ref.start_chapter
    check_chapter(sc)
    check_chapter(ec)
    sv = ref.start_verse or 1
    ev = ref.end_verse if ref.end_verse is not None else counts[ec - 1]
    if ref.start_verse is not None:
        check_verse(sc, sv)
    if ref.end_verse is not None:
        check_verse(ec, ev)
    if (ec, ev) < (sc, sv):
        raise ReferenceSyntaxError(
            f"The range in '{format_reference(ref)}' ends before it begins."
        )
    return Passage(ref, (sc, sv), (ec, ev))


# --------------------------------------------------------------------------- formatting


def _chapter_name(book: Book, chapter: int) -> str:
    return f"{book.singular_name} {chapter}"


def format_reference(ref: Reference) -> str:
    """Human-readable canonical form, e.g. ``John 3:16-21`` or ``Psalm 23``."""
    b = ref.book
    if ref.start_chapter is None:
        return b.name
    sc, sv = ref.start_chapter, ref.start_verse
    ec = ref.end_chapter or sc
    ev = ref.end_verse
    if sv is None:
        if ec == sc:
            return _chapter_name(b, sc)
        return f"{b.name} {sc}-{ec}"
    if ec == sc:
        if ev is None or ev == sv:
            return f"{_chapter_name(b, sc)}:{sv}"
        return f"{_chapter_name(b, sc)}:{sv}-{ev}"
    return f"{b.name} {sc}:{sv}-{ec}:{ev}"


def chapter_reference(book: Book, chapter: int) -> Reference:
    return Reference(book, chapter, None, chapter, None)


# --------------------------------------------------------------------------- detection

_FIND_RE = re.compile(
    r"""(?<![\w:])
        (?P<book>
          (?:(?:[1-3]|I{1,3}|First|Second|Third)\s*)?
          [A-Za-z][A-Za-z]*\.?
          (?:\s+of\s+[A-Za-z]+)?
        )
        \s*
        (?P<c>\d{1,3})
        (?: [:.](?P<v>\d{1,3})
            (?:\s*[-–—]\s*(?P<v2>\d{1,3})(?:[:.](?P<v3>\d{1,3}))?)?
        )?
        (?![\w:])""",
    re.X,
)


@dataclass(frozen=True)
class FoundReference:
    start: int
    end: int
    text: str
    reference: Reference


def find_references(
    text: str,
    is_valid: Callable[[Reference], bool] | None = None,
    books: BookCatalogue | None = None,
) -> list[FoundReference]:
    """Find confidently recognisable references in free text.

    To avoid false links, a match needs either a chapter *and* verse
    (``Rom 8:28``) or a full book name with a chapter (``Psalm 23``). Only
    exact names and listed abbreviations count; prefixes are not guessed.
    ``is_valid`` (usually a check against the translation) filters out
    references to chapters or verses that do not exist.
    """
    books = books or catalogue()
    found: list[FoundReference] = []
    pos = 0
    while True:
        m = _FIND_RE.search(text, pos)
        if not m:
            break
        ref = _found_to_reference(m, books)
        if ref is not None and (is_valid is None or is_valid(ref)):
            found.append(FoundReference(m.start(), m.end(), m.group(0), ref))
            pos = m.end()
        else:
            pos = m.start() + 1
    return found


def _found_to_reference(m: re.Match, books: BookCatalogue) -> Reference | None:
    book_text = m.group("book")
    book = books.exact(book_text)
    if book is None:
        return None
    full_name = book_text.rstrip(".").lower() in {b.lower() for b in (book.name, book.singular_name)}
    c = int(m.group("c"))
    if m.group("v") is None:
        if not full_name or book.id in SINGLE_CHAPTER_BOOKS:
            return None
        return Reference(book, c, None, c, None)
    v = int(m.group("v"))
    if m.group("v3"):
        return Reference(book, c, v, int(m.group("v2")), int(m.group("v3")))
    if m.group("v2"):
        return Reference(book, c, v, c, int(m.group("v2")))
    return Reference(book, c, v, c, v)


def iter_chapters(verse_counts: Mapping[str, Sequence[int]], books: Iterable[Book]):
    """Yield (book, chapter) in canonical order for books present in a translation."""
    for b in books:
        for c in range(1, len(verse_counts.get(b.id, ())) + 1):
            yield b, c
