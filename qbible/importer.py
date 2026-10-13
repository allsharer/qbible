"""Build translation packs from source text files.

Supported input formats:

``vpl``
    eBible.org "verse per line" text: ``GEN 1:1 In the beginning…``. The file
    may be given directly or inside the eBible ``*_vpl.zip`` archive. Books
    outside the 66-book Protestant canon (for example the Apocrypha) are
    excluded and listed in the build report.

``tsv``
    Tab-separated ``book<TAB>chapter<TAB>verse<TAB>text`` with a USFM book
    id (``JHN``) or any book name qbible recognises. Lines beginning with
    ``#`` and blank lines are ignored. Intended for importing other
    legally obtained translations.

Packs are written to a temporary file and moved into place atomically, so a
failed import never leaves a half-written translation behind.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from . import __version__
from .books import catalogue
from .errors import DataError, UnknownBookError
from .schema import PACK_FORMAT, PACK_SCHEMA, PACK_SCHEMA_VERSION, verse_id
from .textfmt import search_text

# eBible.org VPL book codes that differ from USFM codes.
EBIBLE_CODES = {
    "SOL": "SNG", "EZE": "EZK", "JOE": "JOL", "NAH": "NAM", "MAR": "MRK", "JOH": "JHN",
    "PHI": "PHP", "JAM": "JAS", "1JO": "1JN", "2JO": "2JN", "3JO": "3JN",
}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_VPL_RE = re.compile(r"^([0-9A-Z]{3})\s+(\d+):(\d+)\s?(.*)$")


@dataclass
class TranslationInfo:
    id: str
    name: str
    abbreviation: str = ""
    language: str = "en"
    licence: str = ""
    copyright: str = ""
    attribution: str = ""
    source_name: str = ""
    source_url: str = ""
    source_file: str = ""
    source_sha256: str = ""
    retrieved: str = ""
    versification: str = ""
    notes: str = ""

    def validate(self) -> None:
        if not _ID_RE.match(self.id):
            raise DataError(
                "Translation id must be 1-32 lower-case letters, digits or hyphens, e.g. 'kjv'."
            )
        if not self.name.strip():
            raise DataError("A translation name is required.")


@dataclass
class Record:
    book_id: str
    chapter: int
    verse: int
    text: str
    line: int = 0


@dataclass
class BuildResult:
    path: Path
    verse_count: int
    book_count: int
    excluded: dict[str, int] = field(default_factory=dict)
    text_sha256: str = ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_digest(rows: Iterable[tuple[str, int, int, str]]) -> str:
    """Digest of the verse text in canonical order (stored for integrity checks)."""
    h = hashlib.sha256()
    for b, c, v, t in rows:
        h.update(f"{b}\t{c}\t{v}\t{t}\n".encode("utf-8"))
    return h.hexdigest()


# --------------------------------------------------------------------------- readers


def _open_text(path: Path, member_suffix: str) -> io.TextIOBase:
    if zipfile.is_zipfile(path):
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if n.endswith(member_suffix)]
        if len(names) != 1:
            raise DataError(f"Expected exactly one '*{member_suffix}' file inside {path.name}.")
        return io.TextIOWrapper(zf.open(names[0]), encoding="utf-8-sig")
    return open(path, encoding="utf-8-sig")


def read_vpl(path: Path, excluded: dict[str, int]) -> Iterator[Record]:
    """Read eBible VPL text; non-canonical books are counted in ``excluded``."""
    cat = catalogue()
    known = {b.id for b in cat}
    with _open_text(path, "_vpl.txt") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            m = _VPL_RE.match(line)
            if not m:
                raise DataError(f"{path.name}:{n}: unrecognised line: {line[:60]!r}")
            code, c, v, text = m.groups()
            book_id = EBIBLE_CODES.get(code, code)
            if book_id not in known:
                excluded[code] = excluded.get(code, 0) + 1
                continue
            yield Record(book_id, int(c), int(v), text.strip(), n)


def read_tsv(path: Path) -> Iterator[Record]:
    cat = catalogue()
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 4:
                raise DataError(f"{path.name}:{n}: expected 4 tab-separated columns, found {len(cols)}.")
            book, c, v, text = cols
            try:
                b = cat.exact(book) or cat.resolve(book)
            except UnknownBookError as e:
                raise DataError(f"{path.name}:{n}: {e}") from None
            if not (c.strip().isdigit() and v.strip().isdigit()):
                raise DataError(f"{path.name}:{n}: chapter and verse must be numbers.")
            yield Record(b.id, int(c), int(v), text.strip(), n)


FORMATS = ("vpl", "tsv")


def read_records(path: Path, fmt: str, excluded: dict[str, int]) -> Iterator[Record]:
    if fmt == "vpl":
        return read_vpl(path, excluded)
    if fmt == "tsv":
        return read_tsv(path)
    raise DataError(f"Unsupported import format '{fmt}'. Use one of: vpl, tsv.")


# --------------------------------------------------------------------------- builder


def build_pack(records: Iterable[Record], info: TranslationInfo, out_path: Path,
               *, excluded: dict[str, int] | None = None, overwrite: bool = False) -> BuildResult:
    info.validate()
    out_path = Path(out_path)
    if out_path.exists() and not overwrite:
        raise DataError(f"{out_path} already exists. Use --force to replace it.")
    cat = catalogue()

    rows: dict[tuple[str, int, int], Record] = {}
    for r in records:
        if r.chapter < 1 or r.verse < 1:
            raise DataError(f"line {r.line}: chapter and verse numbers must be positive.")
        if not r.text:
            raise DataError(f"line {r.line}: {r.book_id} {r.chapter}:{r.verse} has no text.")
        k = (r.book_id, r.chapter, r.verse)
        if k in rows:
            raise DataError(f"line {r.line}: duplicate verse {r.book_id} {r.chapter}:{r.verse}.")
        rows[k] = r
    if not rows:
        raise DataError("The source contains no verses.")

    order = {b.id: b.order for b in cat}
    ordered = sorted(rows.values(), key=lambda r: (order[r.book_id], r.chapter, r.verse))
    chapters: dict[tuple[str, int], int] = {}
    for r in ordered:
        chapters[(r.book_id, r.chapter)] = max(chapters.get((r.book_id, r.chapter), 0), r.verse)
    book_chapters: dict[str, int] = {}
    for (b, c) in chapters:
        book_chapters[b] = max(book_chapters.get(b, 0), c)
    digest = text_digest((r.book_id, r.chapter, r.verse, r.text) for r in ordered)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(f".{out_path.name}.{os.getpid()}.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(PACK_SCHEMA)
        meta = {
            "format": PACK_FORMAT,
            "schema_version": str(PACK_SCHEMA_VERSION),
            "id": info.id,
            "name": info.name,
            "abbreviation": info.abbreviation or info.id.upper(),
            "language": info.language,
            "licence": info.licence,
            "copyright": info.copyright,
            "attribution": info.attribution,
            "source_name": info.source_name,
            "source_url": info.source_url,
            "source_file": info.source_file,
            "source_sha256": info.source_sha256,
            "retrieved": info.retrieved,
            "versification": info.versification,
            "notes": info.notes,
            "verse_count": str(len(ordered)),
            "text_sha256": digest,
            "imported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "importer": f"qbible {__version__}",
        }
        with conn:
            conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", meta.items())
            for b in cat:
                if b.id in book_chapters:
                    conn.execute(
                        "INSERT INTO books (id, ord, name, testament, chapters) VALUES (?, ?, ?, ?, ?)",
                        (b.id, b.order, b.name, b.testament, book_chapters[b.id]),
                    )
            conn.executemany(
                "INSERT INTO chapters (book_id, chapter, verses) VALUES (?, ?, ?)",
                [(b, c, n) for (b, c), n in chapters.items()],
            )
            conn.executemany(
                "INSERT INTO verses (id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
                [(verse_id(order[r.book_id], r.chapter, r.verse), r.book_id, r.chapter, r.verse, r.text)
                 for r in ordered],
            )
            conn.executemany(
                "INSERT INTO verses_fts (rowid, body) VALUES (?, ?)",
                [(verse_id(order[r.book_id], r.chapter, r.verse), search_text(r.text)) for r in ordered],
            )
        conn.execute("INSERT INTO verses_fts (verses_fts) VALUES ('optimize')")
        conn.commit()
        conn.execute("VACUUM")
        conn.close()
        os.chmod(tmp, 0o644)
        os.replace(tmp, out_path)
    except BaseException:
        conn.close()
        if tmp.exists():
            tmp.unlink()
        raise
    return BuildResult(out_path, len(ordered), len(book_chapters), dict(excluded or {}), digest)


def import_file(source: Path, fmt: str, info: TranslationInfo, out_path: Path,
                *, overwrite: bool = False) -> BuildResult:
    source = Path(source)
    if not source.is_file():
        raise DataError(f"Source file not found: {source}")
    excluded: dict[str, int] = {}
    info.source_file = info.source_file or source.name
    info.source_sha256 = info.source_sha256 or sha256_file(source)
    records = read_records(source, fmt, excluded)
    return build_pack(records, info, out_path, excluded=excluded, overwrite=overwrite)
