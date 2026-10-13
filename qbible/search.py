"""Full-text search over a translation pack.

Query syntax (``mode="auto"``, the default)::

    faith                 verses containing "faith"
    faith hope            verses containing both words (any order)
    "faith without works" the exact phrase (adjacent words, in order)
    love -fear            "love" but not "fear"
    belie*                words beginning with "belie"

Other modes: ``phrase`` treats the whole query as one exact phrase,
``all`` requires every word (quotes ignored), ``any`` matches any word.

Matching is case-insensitive and ignores punctuation, so the phrase
``"fear not"`` also matches "Fear not:". Apostrophes split words the same
way in the query and the text, so ``brother's`` matches *brother’s*.
Ligatures and accents are folded (``caesar`` matches *Cæsar*).

User input is never passed to SQL directly: it is reduced to alphanumeric
tokens, each quoted as an FTS5 string, and bound as a parameter.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .books import Book
from .errors import SearchQueryError
from .repository import TranslationPack, Verse
from .textfmt import fold, parts, tokens

MODES = ("auto", "phrase", "all", "any")
SORTS = ("canonical", "relevance")
MAX_QUERY_LENGTH = 300
MAX_TERMS = 16
MAX_LIMIT = 500

_TERM_RE = re.compile(r'(-?)"([^"]*)"?|(\S+)')


@dataclass(frozen=True)
class Term:
    tokens: tuple[str, ...]
    phrase: bool = False
    prefix: bool = False
    negate: bool = False

    def describe(self) -> str:
        s = " ".join(self.tokens) + ("*" if self.prefix else "")
        if self.phrase:
            s = f'"{s}"'
        return ("-" if self.negate else "") + s

    def fts(self) -> str:
        body = " ".join(f'"{t}"' for t in self.tokens)
        if self.phrase and len(self.tokens) > 1:
            body = " + ".join(f'"{t}"' for t in self.tokens)
        if self.prefix:
            body += " *"
        return f"({body})" if len(self.tokens) > 1 else body


def parse_query(query: str, mode: str = "auto") -> list[Term]:
    if mode not in MODES:
        raise SearchQueryError(f"Unknown search mode '{mode}'. Use one of: {', '.join(MODES)}.")
    q = (query or "").strip()
    if not q:
        raise SearchQueryError("Enter a word or phrase to search for.")
    if len(q) > MAX_QUERY_LENGTH:
        raise SearchQueryError(f"Search text is too long (maximum {MAX_QUERY_LENGTH} characters).")
    q = q.replace("“", '"').replace("”", '"')

    terms: list[Term] = []
    if mode == "phrase":
        toks = tokens(q)
        if toks:
            terms.append(Term(tuple(toks), phrase=True))
    elif mode in ("all", "any"):
        terms = [Term((t,)) for t in tokens(q)]
    else:
        for m in _TERM_RE.finditer(q):
            neg, quoted, word = m.groups()
            if quoted is not None:
                toks = tokens(quoted)
                if toks:
                    terms.append(Term(tuple(toks), phrase=True, negate=bool(neg)))
                continue
            negate = word.startswith("-") and len(word) > 1
            if negate:
                word = word[1:]
            prefix = word.endswith("*")
            toks = tokens(word)
            if not toks:
                continue
            # "brother's" -> tokens ("brother", "s"): keep them adjacent.
            terms.append(Term(tuple(toks), phrase=len(toks) > 1, prefix=prefix, negate=negate))
    if not terms:
        raise SearchQueryError("The search must contain at least one letter or number.")
    if len(terms) > MAX_TERMS:
        raise SearchQueryError(f"Too many search terms (maximum {MAX_TERMS}).")
    if all(t.negate for t in terms):
        raise SearchQueryError("A search needs at least one word to look for, not only excluded words.")
    return terms


def fts_expression(terms: list[Term], mode: str = "auto") -> str:
    pos = [t.fts() for t in terms if not t.negate]
    neg = [t.fts() for t in terms if t.negate]
    joiner = " OR " if mode == "any" else " AND "
    expr = joiner.join(pos)
    if mode == "any" and len(pos) > 1:
        expr = f"({expr})"
    for n in neg:
        expr = f"{expr} NOT {n}"
    return expr


# --------------------------------------------------------------------------- highlighting

_WORD = r"[^\W_]"


def _token_pattern(tok: str) -> str:
    """Regex for one folded token; ``ae`` also matches the ligature æ."""
    return "(?:ae|æ)".join(re.escape(p) for p in tok.split("ae"))


def highlight_regex(terms: list[Term]) -> re.Pattern | None:
    pats = []
    for t in terms:
        if t.negate:
            continue
        body = r"[\W_]+".join(_token_pattern(tok) for tok in t.tokens)
        end = _WORD + "*" if t.prefix else ""
        pats.append(rf"(?<!{_WORD}){body}{end}(?!{_WORD})")
    if not pats:
        return None
    return re.compile("|".join(f"(?:{p})" for p in pats), re.IGNORECASE)


def segments(raw: str, rx: re.Pattern | None) -> list[dict]:
    """Display segments of a verse: ``{"text", "supplied", "match"}``.

    Match positions are found on folded text of the same length so that
    curly apostrophes and diacritics still line up with the original.
    """
    ps = parts(raw)
    plain = "".join(p.text for p in ps)
    spans: list[tuple[int, int]] = []
    if rx is not None:
        searchable = _same_length_fold(plain)
        spans = [m.span() for m in rx.finditer(searchable) if m.end() > m.start()]
    out: list[dict] = []
    pos = 0
    for p in ps:
        start, end = pos, pos + len(p.text)
        cuts = {start, end}
        for a, b in spans:
            if start < a < end:
                cuts.add(a)
            if start < b < end:
                cuts.add(b)
        bounds = sorted(cuts)
        for a, b in zip(bounds, bounds[1:]):
            hit = any(sa <= a and b <= sb for sa, sb in spans)
            seg = {"text": plain[a:b], "supplied": p.supplied, "match": hit}
            if out and out[-1]["supplied"] == seg["supplied"] and out[-1]["match"] == seg["match"]:
                out[-1]["text"] += seg["text"]
            else:
                out.append(seg)
        pos = end
    return out


def _same_length_fold(text: str) -> str:
    out = []
    for ch in text:
        if ch in "æÆ":
            out.append(ch)  # handled by the (?:ae|æ) pattern
            continue
        f = fold(ch)
        out.append(f if len(f) == 1 else ch)
    return "".join(out)


# --------------------------------------------------------------------------- execution


@dataclass
class Hit:
    verse: Verse
    segments: list[dict]
    context_before: list[Verse] = field(default_factory=list)
    context_after: list[Verse] = field(default_factory=list)


@dataclass
class SearchResult:
    query: str
    mode: str
    sort: str
    terms: list[Term]
    total: int
    offset: int
    limit: int
    hits: list[Hit]

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.hits) < self.total


def _scope(book: Book | None, testament: str | None) -> tuple[int, int]:
    if book is not None:
        return book.order * 1_000_000, book.order * 1_000_000 + 999_999
    if testament == "OT":
        return 1_000_000, 39_999_999
    if testament == "NT":
        return 40_000_000, 66_999_999
    return 0, 1 << 62


def search(pack: TranslationPack, query: str, *, mode: str = "auto", limit: int = 20,
           offset: int = 0, sort: str = "canonical", book: Book | None = None,
           testament: str | None = None, context: int = 0) -> SearchResult:
    if sort not in SORTS:
        raise SearchQueryError(f"Unknown sort order '{sort}'. Use one of: {', '.join(SORTS)}.")
    if not (1 <= limit <= MAX_LIMIT):
        raise SearchQueryError(f"The result limit must be between 1 and {MAX_LIMIT}.")
    if offset < 0:
        raise SearchQueryError("The result offset cannot be negative.")
    if testament not in (None, "OT", "NT"):
        raise SearchQueryError("Testament must be OT or NT.")
    if not 0 <= context <= 5:
        raise SearchQueryError("Context must be between 0 and 5 verses.")

    terms = parse_query(query, mode)
    expr = fts_expression(terms, mode)
    lo, hi = _scope(book, testament)
    order = "bm25(verses_fts), rowid" if sort == "relevance" else "rowid"
    try:
        (total,) = pack.conn.execute(
            "SELECT count(*) FROM verses_fts WHERE verses_fts MATCH ? AND rowid BETWEEN ? AND ?",
            (expr, lo, hi),
        ).fetchone()
        ids = [r[0] for r in pack.conn.execute(
            f"SELECT rowid FROM verses_fts WHERE verses_fts MATCH ? AND rowid BETWEEN ? AND ? "
            f"ORDER BY {order} LIMIT ? OFFSET ?",
            (expr, lo, hi, limit, offset),
        )]
    except sqlite3.OperationalError as e:  # should not happen: tokens are sanitised
        raise SearchQueryError(f"The search could not be run: {e}") from None

    verses = pack.verses_by_ids(ids)
    rx = highlight_regex(terms)
    hits = []
    for i in ids:
        v = verses[i]
        hit = Hit(v, segments(v.text, rx))
        if context:
            near = pack.verses_by_ids([i + d for d in range(-context, context + 1) if d])
            hit.context_before = [near[i + d] for d in range(-context, 0) if i + d in near]
            hit.context_after = [near[i + d] for d in range(1, context + 1) if i + d in near]
        hits.append(hit)
    return SearchResult(query, mode, sort, terms, total, offset, limit, hits)
