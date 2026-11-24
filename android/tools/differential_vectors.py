#!/usr/bin/env python3
"""Generate large differential test vectors from the desktop engine.

Unlike ``spec/*.json`` (small, reviewed, committed), these files are generated
at build time into ``android/build/qbible-data/`` and compared by the Kotlin
tests (``DifferentialTest``): thousands of reference inputs (every book
name, id and alias in many chapter/verse forms, prefixes, junk) and a few
hundred pseudo-random search queries, run through the Python reference
parser and the Python FTS5 search. A desktop-created ``user.sqlite`` is also
written so the Kotlin user store can be checked against the real format.

Usage: python3 android/tools/differential_vectors.py OUT_DIR
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qbible.books import catalogue  # noqa: E402
from qbible.errors import QBibleError  # noqa: E402
from qbible.reference import find_references, parse, parse_key, resolve  # noqa: E402
from qbible.repository import TranslationPack  # noqa: E402
from qbible.search import search  # noqa: E402

PACK = ROOT / "build" / "translations" / "kjv.sqlite"


def reference_inputs(rng: random.Random) -> list[str]:
    out: list[str] = []
    forms = ["", " 1", " 3", " 1:1", " 2:3-5", " 3v4", " 1-2", " 4:1-", " 150", " 999", " 1000",
             " 1:1-2:3", " 2.3", " 2 3", " 1 vv 2", " 1:2-1:9", " 5-", " 2:3 - 4", " 0", " 1:0",
             " 1–2", " 3:16,17", ".", " 1:1 ;"]
    for b in catalogue():
        names = {b.id, b.name, b.slug, b.osis, *b.aliases, b.name.upper(), b.name.lower()}
        if b.name[0].isdigit():
            n, rest = b.name.split(" ", 1)
            roman = {"1": "I", "2": "II", "3": "III"}[n]
            word = {"1": "First", "2": "Second", "3": "Third"}[n]
            names |= {f"{n}{rest}", f"{roman} {rest}", f"{word} {rest}", f"{n}st {rest}" if n == "1" else f"{n}nd {rest}"}
        for i in range(2, len(b.name) + 1):
            names.add(b.name[:i])
        for name in sorted(names):
            out.append(name + rng.choice(forms))
            out.append(name + rng.choice(forms))
    alphabet = "abcdefghijklmnopqrstuvwxyz ABCJ0123456789:.-v–,;’'é "
    for _ in range(1500):
        out.append("".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14))))
    out += ["Song of Solomon 2", "song of songs 2:1", "Psalm 23", "Psalms 22-23", "Jude", "Jude 3-",
            "Philemon 1", "3 John 1:14", "  john   3 : 16 ", "JOHN 3V16", "Mar 4:1-5:2", "1Sam 4:1",
            "Gen 1:1-2:3", "Rev 22:21", "Obadiah 1:21", "Ps 119:176", "Ps 119:177", "Esther 8:9",
            "1 Jn 5:7", "Jn 3:16 ", "John 3:16–18", "John 3:16—18", "Rom 8:28.", "x" * 201]
    return out


def reference_case(text: str, counts) -> dict:
    case: dict = {"input": text}
    try:
        ref = parse(text)
        case["parsed_key"] = ref.key()
        passage = resolve(ref, counts)
        case["display"] = passage.display()
        case["key"] = passage.key()
    except QBibleError as e:
        case["code"] = e.code
    return case


def key_cases(rng: random.Random) -> list[dict]:
    keys = ["JHN", "JHN.3", "JHN.3.16", "JHN.3.16-JHN.3.21", "GEN.1.1-GEN.2.3", "PSA.22-PSA.23", "JHN.3.16-ROM.1.1",
            "jhn.3.16", "XXX.1.1", "JHN.3.", "JHN..3", "1JN.5.7", "JHN.0", "JHN.3.0", ""]
    out = []
    for k in keys:
        case = {"input": k}
        try:
            r = parse_key(k)
            case["key"] = r.key()
            case["display"] = r.display()
        except QBibleError as e:
            case["code"] = e.code
        out.append(case)
    return out


def find_cases(pack: TranslationPack) -> list[dict]:
    texts = [
        "Read Rom 8:28 and John 3:16-18 tonight", "Psalm 23 is short; Ps 23 is not linked", "see 1 Cor 13:4-7",
        "Gen 1:1-2:3 and Jude 3 and Jude 1:3", "I John 4:8, First John 4:8", "Song of Solomon 2:1",
        "John 3:37 does not exist", "love your neighbour", "Mark 4:1-", "Jn 3:16", "Matthew 5:3-12; Luke 6:20",
        "x John 3:16y", "3:16", "Revelation 22", "Rev 22:21.", "Philemon 1:4", "Esther 8:9 is long",
    ]
    out = []
    for t in texts:
        out.append({"text": t, "found": [
            {"start": f.start, "end": f.end, "text": f.text, "key": f.reference.key()}
            for f in find_references(t, pack.is_valid)
        ]})
    return out


def search_queries(rng: random.Random, pack: TranslationPack) -> list[dict]:
    words = [r[0] for r in pack.conn.execute(
        "SELECT text FROM verses WHERE id % 97 = 0")]
    vocab = sorted({w.strip(".,;:?!()’'[]¶").lower() for t in words for w in t.split()} - {""})
    cases = []
    for i in range(400):
        n = rng.choice([1, 1, 2, 2, 3])
        parts = []
        for _ in range(n):
            w = rng.choice(vocab)
            r = rng.random()
            if r < 0.12 and len(w) > 3:
                w = w[: rng.randint(2, len(w) - 1)] + "*"
            elif r < 0.2:
                w = "-" + w
            parts.append(w)
        if rng.random() < 0.2 and n > 1:
            q = '"' + " ".join(p.lstrip("-").rstrip("*") for p in parts) + '"'
        else:
            q = " ".join(parts)
        mode = rng.choice(["auto"] * 6 + ["phrase", "all", "any"])
        sort = rng.choice(["canonical", "canonical", "relevance"])
        testament = rng.choice([None, None, None, "OT", "NT"])
        limit = rng.choice([5, 20, 50])
        case = {"query": q, "mode": mode, "sort": sort, "testament": testament, "limit": limit, "offset": 0}
        try:
            r = search(pack, q, mode=mode, sort=sort, testament=testament, limit=limit)
            case["total"] = r.total
            case["keys"] = [f"{h.verse.book_id}.{h.verse.chapter}.{h.verse.verse}" for h in r.hits]
            case["segments"] = [h.segments for h in r.hits]
        except QBibleError as e:
            case["code"] = e.code
        cases.append(case)
    return cases


def desktop_user_db(path: Path) -> dict:
    """A user.sqlite written by the desktop UserStore, and what it contains."""
    from qbible.userdata import UserStore
    if path.exists():
        path.unlink()
    store = UserStore(path)
    store.add_bookmark("kjv", parse("John 3:16-21"), "Gospel in a nutshell")
    store.add_bookmark("kjv", parse("Psalm 23"))
    store.add_bookmark("kjv", parse("Mark 4:1-"))  # unresolved open range is stored as parsed
    for r in ["Genesis 1", "Romans 8:28", "Genesis 1", "Jude"]:
        store.record("kjv", parse(r))
    return {
        "bookmarks": [b.to_dict() for b in store.bookmarks()],
        "history": [h.to_dict() for h in store.history(50)],
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: differential_vectors.py OUT_DIR", file=sys.stderr)
        return 2
    out = Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261123)
    pack = TranslationPack(PACK)
    counts = pack.verse_counts
    data = {
        "references": [reference_case(t, counts) for t in reference_inputs(rng)],
        "keys": key_cases(rng),
        "find": find_cases(pack),
        "search": search_queries(rng, pack),
        "user": desktop_user_db(out / "desktop-user.sqlite"),
    }
    fd, tmp = tempfile.mkstemp(dir=out)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, out / "differential.json")
    print(f"{out}/differential.json: {len(data['references'])} references, {len(data['search'])} searches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
