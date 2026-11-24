#!/usr/bin/env python3
"""Make the Android copy of a qbible translation pack (FTS5 index -> FTS4).

Android's built-in SQLite always has FTS3/FTS4 but does not promise FTS5, so
the Android app ships a copy of the pack in which the FTS5 table
``verses_fts`` is replaced by an FTS4 table ``verses_fts4``. Everything else
(meta, books, chapters, verses) is copied unchanged.

The FTS4 table stores, for each verse, the exact token stream of the desktop
FTS5 index (``textfmt.tokens`` of the plain text, joined by single spaces), so
FTS4's ``simple`` tokenizer reproduces it exactly whatever compile options the
device's SQLite has. Before writing, the script checks that this token stream
is identical, verse by verse and position by position, to what the FTS5 index
actually contains (via ``fts5vocab``), and that per-token match counts agree.

Usage (from the repository root, Python 3.10+, standard library only):

    python3 android/tools/make_android_pack.py SRC.sqlite DEST.sqlite

Exit status 0 on success, 1 on any verification failure (no DEST is left).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qbible.textfmt import plain, tokens  # noqa: E402

FORMAT = "qbible-translation-pack"
INDEX_NAME = "verses_fts4"
INDEX_FORMAT = "fts4-tokens-v1"


def fail(msg: str) -> None:
    print(f"make_android_pack: {msg}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verse_tokens(conn: sqlite3.Connection) -> dict[int, list[str]]:
    return {vid: tokens(plain(text)) for vid, text in conn.execute("SELECT id, text FROM verses ORDER BY id")}


def fts5_tokens(conn: sqlite3.Connection) -> dict[int, list[str]]:
    """The token stream the desktop FTS5 index really holds, per verse."""
    conn.execute(f"CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main, verses_fts, 'instance')")
    out: dict[int, dict[int, str]] = {}
    for term, doc, _col, offset in conn.execute("SELECT term, doc, col, offset FROM temp.vocab"):
        out.setdefault(doc, {})[offset] = term
    conn.execute("DROP TABLE temp.vocab")
    return {doc: [pos[i] for i in sorted(pos)] for doc, pos in out.items()}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: make_android_pack.py SRC.sqlite DEST.sqlite", file=sys.stderr)
        return 2
    src, dest = Path(argv[1]), Path(argv[2])
    if not src.is_file():
        fail(f"{src} does not exist. Build it with 'python3 -m qbible.build_data'.")

    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    meta = dict(s.execute("SELECT key, value FROM meta"))
    if meta.get("format") != FORMAT or meta.get("schema_version") != "1":
        fail(f"{src} is not a schema-1 qbible translation pack.")

    ours = verse_tokens(s)
    theirs = fts5_tokens(s)
    # Verses with no tokens at all would be absent from fts5vocab.
    for vid, toks in ours.items():
        if theirs.get(vid, []) != toks:
            fail(f"token mismatch in verse {vid}: FTS5 has {theirs.get(vid)}, textfmt gives {toks}")
    if set(theirs) - set(ours):
        fail("FTS5 index has rows that are not verses")
    total_tokens = sum(len(t) for t in ours.values())

    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".android-pack-", suffix=".sqlite", dir=dest.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        d = sqlite3.connect(tmp)
        s.backup(d)
        s.close()
        d.execute("DROP TABLE verses_fts")
        d.execute(f"CREATE VIRTUAL TABLE {INDEX_NAME} USING fts4(body, tokenize=simple)")
        d.executemany(
            f"INSERT INTO {INDEX_NAME} (docid, body) VALUES (?, ?)",
            ((vid, " ".join(toks)) for vid, toks in ours.items()),
        )
        d.execute(f"INSERT INTO {INDEX_NAME}({INDEX_NAME}) VALUES ('optimize')")
        extra = {
            "search_index": INDEX_NAME,
            "search_index_format": INDEX_FORMAT,
            "search_index_rows": str(len(ours)),
            "search_index_tokens": str(total_tokens),
            "android_pack_source_sha256": sha256(src),
        }
        d.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", extra.items())
        d.commit()

        # Spot-check: per-token document counts agree with the FTS5 index.
        s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        for tok in ["the", "lord", "faith", "wept", "caesar", "s", "ae", "jesus", "love", "selah"]:
            (a,) = s.execute("SELECT count(*) FROM verses_fts WHERE verses_fts MATCH ?", (f'"{tok}"',)).fetchone()
            (b,) = d.execute(f"SELECT count(*) FROM {INDEX_NAME} WHERE {INDEX_NAME} MATCH ?", (f'"{tok}"',)).fetchone()
            if a != b:
                fail(f"count mismatch for {tok!r}: FTS5 {a}, FTS4 {b}")
        s.close()
        (ok,) = d.execute("PRAGMA integrity_check").fetchone()
        if ok != "ok":
            fail(f"integrity_check: {ok}")
        d.execute("VACUUM")
        d.close()
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(f"{dest}: {len(ours)} verses, {total_tokens} tokens, sha256 {sha256(dest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
