"""Translation pack format (version 1).

A *translation pack* is one self-contained SQLite file per translation. It is
immutable once built: the application only ever opens it read-only, and user
data lives in a different database (see :mod:`qbible.userdata`).

The format is deliberately plain so that other clients (for example an
Android app using its platform SQLite) can read it directly.
"""

PACK_FORMAT = "qbible-translation-pack"
PACK_SCHEMA_VERSION = 1

PACK_SCHEMA = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Books present in this translation, in canonical order.
CREATE TABLE books (
    id        TEXT PRIMARY KEY,                -- USFM code, e.g. 'JHN'
    ord       INTEGER NOT NULL UNIQUE,         -- canonical order (1 = Genesis)
    name      TEXT NOT NULL,                   -- display name in this translation
    testament TEXT NOT NULL CHECK (testament IN ('OT', 'NT')),
    chapters  INTEGER NOT NULL CHECK (chapters > 0)
);

-- Versification actually present in this translation.
CREATE TABLE chapters (
    book_id TEXT NOT NULL REFERENCES books(id),
    chapter INTEGER NOT NULL CHECK (chapter > 0),
    verses  INTEGER NOT NULL CHECK (verses > 0),
    PRIMARY KEY (book_id, chapter)
) WITHOUT ROWID;

-- id = book_ord * 1000000 + chapter * 1000 + verse, so ORDER BY id is canonical order.
CREATE TABLE verses (
    id      INTEGER PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id),
    chapter INTEGER NOT NULL CHECK (chapter > 0),
    verse   INTEGER NOT NULL CHECK (verse > 0),
    text    TEXT NOT NULL,                     -- exactly as in the source
    UNIQUE (book_id, chapter, verse)
);

-- Contentless full-text index over normalised text (rowid = verses.id).
CREATE VIRTUAL TABLE verses_fts USING fts5(
    body,
    content = '',
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def verse_id(book_order: int, chapter: int, verse: int) -> int:
    return book_order * 1_000_000 + chapter * 1000 + verse
