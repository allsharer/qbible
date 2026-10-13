"""Reproducibly build bundled translation packs from vendored sources.

Usage (from the source tree)::

    python3 -m qbible.build_data            # builds build/translations/kjv.sqlite
    python3 -m qbible.build_data --check    # verify the source checksum only

The source archive's SHA-256 must match ``data/sources/SOURCES.json``; the
built pack is validated and a report is written next to it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import QBibleError
from .importer import TranslationInfo, import_file, sha256_file
from .paths import share_dir
from .validation import validate_pack


def main(argv: list[str] | None = None) -> int:
    root = share_dir()
    ap = argparse.ArgumentParser(prog="qbible-build-data", description=__doc__.splitlines()[0])
    ap.add_argument("--sources", type=Path, default=root / "data" / "sources")
    ap.add_argument("--out-dir", type=Path, default=root / "build" / "translations")
    ap.add_argument("--translation", default="kjv")
    ap.add_argument("--check", action="store_true", help="verify the source checksum and exit")
    args = ap.parse_args(argv)

    manifest = json.loads((args.sources / "SOURCES.json").read_text(encoding="utf-8"))
    if args.translation not in manifest:
        print(f"No source registered for '{args.translation}'.", file=sys.stderr)
        return 2
    entry = manifest[args.translation]
    src = args.sources / entry["file"]
    if not src.is_file():
        print(f"Source file missing: {src}\nDownload it from {entry['url']}", file=sys.stderr)
        return 4
    digest = sha256_file(src)
    if digest != entry["sha256"]:
        print(f"Checksum mismatch for {src}:\n  expected {entry['sha256']}\n  actual   {digest}",
              file=sys.stderr)
        return 4
    print(f"Source verified: {src.name} sha256={digest}")
    if args.check:
        return 0

    t = entry["translation"]
    info = TranslationInfo(
        id=t["id"], name=t["name"], abbreviation=t["abbreviation"], language=t["language"],
        licence=t["licence"], copyright=t["copyright"], attribution=t["attribution"],
        source_name=entry["source_name"], source_url=entry["url"], source_file=entry["file"],
        source_sha256=digest, retrieved=entry["retrieved"], versification=t["versification"],
        notes=t["notes"],
    )
    out = args.out_dir / f"{t['id']}.sqlite"
    try:
        result = import_file(src, entry["format"], info, out, overwrite=True)
    except QBibleError as e:
        print(f"Import failed: {e}", file=sys.stderr)
        return 4
    print(f"Built {result.path}: {result.book_count} books, {result.verse_count} verses")
    if result.excluded:
        ex = ", ".join(f"{k} ({v})" for k, v in result.excluded.items())
        print(f"Excluded non-canonical books (verses): {ex}")

    report = validate_pack(out)
    text = report.to_text()
    if result.excluded:
        text += "\nExcluded from source (not part of the 66-book canon): " + \
            ", ".join(f"{k} ({v} verses)" for k, v in result.excluded.items()) + "\n"
    (args.out_dir / f"{t['id']}-validation.txt").write_text(text, encoding="utf-8")
    print(text)
    if not report.ok:
        out.unlink()
        print("Validation failed; the pack has been removed.", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
