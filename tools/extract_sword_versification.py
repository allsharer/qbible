#!/usr/bin/env python3
"""Regenerate qbible/resources/versification/kjv.json from SWORD's canon.h.

The KJV versification table (verses per chapter) is taken from the CrossWire
SWORD Project, an independent source from the eBible.org text export, and
is used only as numeric reference data for validation.

Usage:
    curl -sSLo /tmp/canon.h https://crosswire.org/svn/sword/trunk/include/canon.h
    python3 tools/extract_sword_versification.py /tmp/canon.h qbible/resources/versification/kjv.json
"""

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(src_path: str, out_path: str) -> None:
    src = Path(src_path).read_text(encoding="utf-8")
    books = re.findall(r'\{"([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*(\d+)\}', src)
    body = src[src.index("int vm[] = {"):]
    body = body[: body.index("};")]
    nums = [int(n) for n in re.findall(r"\b\d+\b", re.sub(r"//.*", "", body))]

    catalogue = json.loads((ROOT / "qbible/resources/books.json").read_text(encoding="utf-8"))["books"]
    if len(books) != len(catalogue):
        sys.exit(f"expected {len(catalogue)} books in canon.h, found {len(books)}")
    out, i = {}, 0
    for (_name, _abbr, osis, chapters), book in zip(books, catalogue):
        if osis != book["osis"]:
            sys.exit(f"book order mismatch: canon.h {osis} vs books.json {book['osis']}")
        n = int(chapters)
        out[book["id"]] = nums[i : i + n]
        i += n
    if i != len(nums):
        sys.exit("verse table length does not match chapter counts")
    doc = {
        "schema": 1,
        "name": "KJV",
        "description": "Expected verses per chapter for the King James Version versification.",
        "source": "CrossWire SWORD Project include/canon.h (vm[] table), "
                  "https://crosswire.org/svn/sword/trunk/include/canon.h",
        "retrieved": datetime.date.today().isoformat(),
        "total_verses": sum(sum(v) for v in out.values()),
        "books": out,
    }
    Path(out_path).write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} books, {doc['total_verses']} verses -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
