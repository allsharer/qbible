#!/usr/bin/env python3
"""Export language-neutral search test vectors to ``spec/search-cases.json``.

The vectors are produced by running the desktop search engine
(``qbible.search``, FTS5) against the built KJV pack. Other clients (the
Android app's Kotlin port, which uses FTS4) must reproduce them exactly:
the parsed terms, the error code for rejected queries, the total, the
ordered result keys (canonical and relevance order) and the highlight
segments.

Usage, from the repository root, after ``python3 -m qbible.build_data``:

    python3 tools/export_search_cases.py            # rewrite spec/search-cases.json
    python3 tools/export_search_cases.py --check    # exit 1 if the file is out of date

``tests/test_search.py`` also checks that the committed file still matches.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qbible.books import catalogue  # noqa: E402
from qbible.errors import SearchQueryError  # noqa: E402
from qbible.reference import Reference  # noqa: E402
from qbible.repository import TranslationPack  # noqa: E402
from qbible.search import parse_query, search  # noqa: E402

PACK = ROOT / "build" / "translations" / "kjv.sqlite"
OUT = ROOT / "spec" / "search-cases.json"

# Query parsing only (no database): input -> terms, or the error code.
PARSE_CASES = [
    ('faith "without works" -dead belie*', "auto"),
    ("faith hope", "auto"),
    ('"faith without works"', "auto"),
    ("brother's keeper", "auto"),
    ("brother’s keeper", "auto"),
    ("“fear not”", "auto"),
    ('"unterminated phrase', "auto"),
    ("-\"fear not\" love", "auto"),
    ("Cæsar", "auto"),
    ("café", "auto"),
    ("believ* -believe", "auto"),
    ("a - b", "auto"),
    ("x\") OR NEAR(a b) ; DROP TABLE verses; --", "auto"),
    ("works without faith", "phrase"),
    ('"quoted" -minus star*', "phrase"),
    ('faith "hope charity" -love', "all"),
    ("xylophone -wept", "any"),
    ("", "auto"),
    ("   ", "auto"),
    ("!!!", "auto"),
    ('""', "auto"),
    ("-love", "auto"),
    ("-love -fear", "auto"),
    ("love", "regex"),
    ("a b c d e f g h i j k l m n o p", "auto"),
    ("a b c d e f g h i j k l m n o p q", "auto"),
    ("x" * 300, "auto"),
    ("x" * 301, "auto"),
]

# Full searches against the KJV pack.
SEARCH_CASES = [
    dict(q="faith", limit=25),
    dict(q='"faith without works"'),
    dict(q="faith without works"),
    dict(q="works without faith", mode="phrase"),
    dict(q="Jesus wept", mode="phrase", context=1),
    dict(q="LORD", limit=5),
    dict(q="lord", limit=5),
    dict(q='"Fear Not"', limit=5),
    dict(q='"fear not"', limit=5),
    dict(q="brother's keeper"),
    dict(q="brother’s keeper"),
    dict(q='"brother\'s keeper"'),
    dict(q='"fear not abram"'),
    dict(q="caesar's", limit=25),
    dict(q="Cæsar", limit=5),
    dict(q='"the LORD is my shepherd"'),
    dict(q="xylophone"),
    dict(q="love", limit=10),
    dict(q="love", limit=10, offset=10),
    dict(q="love", limit=10, offset=307),
    dict(q="love", limit=25, sort="relevance"),
    dict(q="love", limit=10, offset=40, sort="relevance"),
    dict(q="the", limit=20, sort="relevance"),
    dict(q="faith hope charity", limit=25, sort="relevance"),
    dict(q='"in the beginning"', sort="relevance"),
    dict(q="believ*", limit=25, sort="relevance"),
    dict(q="lord -god", limit=25, sort="relevance"),
    dict(q="mercy truth", mode="any", limit=25, sort="relevance"),
    dict(q='"my beloved" son', limit=25, sort="relevance"),
    dict(q="faith", testament="NT", limit=5),
    dict(q="faith", testament="OT", limit=5),
    dict(q="faith", book="ROM", limit=25),
    dict(q="grace", book="EPH", sort="relevance", limit=25),
    dict(q="xylophone wept", mode="any"),
    dict(q="wept"),
    dict(q="love -fear", limit=5),
    dict(q="love fear", limit=5),
    dict(q='love -"perfect love"', limit=5),
    dict(q="believ*", limit=5),
    dict(q="believe", limit=5),
    dict(q='"brother s*"', limit=10),
    dict(q='"son of ma*"', limit=10),
    dict(q="lov* -love", limit=10),
    dict(q="faith hope", mode="all", limit=10),
    dict(q='"and it came to pass"', limit=5),
    dict(q="selah", limit=5, testament="NT"),
    dict(q="sin", book="EXO", limit=25),
    dict(q="God", book="PHM"),
    dict(q="alpha omega", limit=10),
    dict(q="'; DROP TABLE verses; --"),
    dict(q="love\" OR 1=1 --", limit=5),
    dict(q="NEAR(love faith)", limit=5),
    dict(q="* OR *", limit=5),
    dict(q="verses_fts MATCH 'x'"),
    dict(q="%_%"),
    dict(q="love", limit=0),
    dict(q="love", limit=501),
    dict(q="love", offset=-1),
    dict(q="love", sort="random"),
    dict(q="love", testament="XX"),
    dict(q="love", context=6),
]

DEFAULTS = dict(mode="auto", limit=20, offset=0, sort="canonical", book=None, testament=None, context=0)


def key_of(v) -> str:
    b = catalogue().get(v.book_id)
    return Reference(b, v.chapter, v.verse, v.chapter, v.verse).key()


def build() -> dict:
    parse = []
    for q, mode in PARSE_CASES:
        case = {"query": q, "mode": mode}
        try:
            case["terms"] = [t.describe() for t in parse_query(q, mode)]
        except SearchQueryError as e:
            case["error"] = e.code
        parse.append(case)

    pack = TranslationPack(PACK)
    searches = []
    for spec in SEARCH_CASES:
        args = {**DEFAULTS, **spec}
        q = args.pop("q")
        book = catalogue().get(args["book"]) if args["book"] else None
        case = {"query": q, **{k: v for k, v in args.items()}}
        try:
            r = search(pack, q, **{**args, "book": book})
        except SearchQueryError as e:
            case["error"] = e.code
            searches.append(case)
            continue
        case["terms"] = [t.describe() for t in r.terms]
        case["total"] = r.total
        case["has_more"] = r.has_more
        case["results"] = [
            {
                "key": key_of(h.verse),
                "segments": h.segments,
                **(
                    {"context_before": [key_of(v) for v in h.context_before],
                     "context_after": [key_of(v) for v in h.context_after]}
                    if args["context"] else {}
                ),
            }
            for h in r.hits
        ]
        searches.append(case)

    return {
        "description": (
            "Language-neutral search test vectors, exported from the desktop search engine "
            "(qbible.search, FTS5) by tools/export_search_cases.py against the bundled KJV pack. "
            "Any qbible client must produce the same 'terms' (Term.describe), the same error "
            "'code' for rejected queries, and for searches the same 'total', 'has_more', ordered "
            "result keys (canonical order, or BM25 relevance with ties broken by verse order) and "
            "highlight segments."
        ),
        "translation": pack.meta.get("id"),
        "translation_text_sha256": pack.meta.get("text_sha256"),
        "defaults": DEFAULTS,
        "parse": parse,
        "search": searches,
    }


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    if not PACK.is_file():
        print(f"{PACK} not found; run 'python3 -m qbible.build_data' first.", file=sys.stderr)
        return 2
    text = render()
    if "--check" in argv:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} is out of date; run tools/export_search_cases.py", file=sys.stderr)
            return 1
        print(f"{OUT} is up to date.")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
