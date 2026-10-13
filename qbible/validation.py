"""Validation of translation packs.

Checks performed (each reported as pass / warn / fail):

* SQLite integrity and pack metadata (format, schema, attribution fields);
* canon: which of the 66 books are present;
* versification: chapters per book and verses per chapter compared with a
  reference table. For packs declaring that versification (the KJV) any
  difference is a failure; for others it is a warning, because legitimate
  versification differences exist between translations;
* sequential verse numbering with no gaps inside each chapter;
* no empty verses; stored chapter/verse tables agree with the verse rows;
* full-text index row count equals the number of verses;
* stored text digest matches the verse text (detects later modification);
* representative checkpoint verses, first and last verse (where a checkpoint
  file exists for the translation);
* special characters (’, æ, —, ¶) are still present (Unicode preserved).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .books import RESOURCES, catalogue, reference_versification
from .importer import text_digest
from .repository import open_readonly
from .schema import PACK_FORMAT, PACK_SCHEMA_VERSION


@dataclass
class Check:
    name: str
    status: str  # pass | warn | fail
    detail: str = ""


@dataclass
class Report:
    path: str
    translation: str = ""
    checks: list[Check] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(name, status, detail))

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "translation": self.translation,
            "ok": self.ok,
            "stats": self.stats,
            "checks": [c.__dict__ for c in self.checks],
        }

    def to_text(self) -> str:
        lines = [
            "qbible validation report",
            f"{'Pack:':<17}{self.path}",
            f"{'Translation:':<17}{self.translation}",
        ]
        for k, v in self.stats.items():
            lines.append(f"{k.replace('_', ' ').capitalize() + ':':<17}{v}")
        lines.append("")
        for c in self.checks:
            mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[c.status]
            lines.append(f"[{mark}] {c.name}" + (f": {c.detail}" if c.detail else ""))
        lines.append("")
        lines.append("RESULT: " + ("VALID" if self.ok else "INVALID"))
        return "\n".join(lines) + "\n"


def _checkpoints(translation: str) -> dict | None:
    p = RESOURCES / "checkpoints" / f"{translation}.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def validate_pack(path: Path, max_details: int = 20) -> Report:
    path = Path(path)
    report = Report(str(path))
    try:
        conn = open_readonly(path)
    except sqlite3.Error as e:
        report.add("open database", "fail", str(e))
        return report
    try:
        _validate(conn, report, max_details)
    except sqlite3.Error as e:
        report.add("read database", "fail", str(e))
    finally:
        conn.close()
    return report


def _validate(conn: sqlite3.Connection, report: Report, max_details: int) -> None:
    cat = catalogue()

    # Integrity and metadata ----------------------------------------------------
    res = conn.execute("PRAGMA integrity_check").fetchone()[0]
    report.add("SQLite integrity check", "pass" if res == "ok" else "fail", "" if res == "ok" else res)
    meta = dict(conn.execute("SELECT key, value FROM meta"))
    report.translation = meta.get("id", "?")
    fmt_ok = meta.get("format") == PACK_FORMAT and meta.get("schema_version") == str(PACK_SCHEMA_VERSION)
    report.add("pack format and schema version", "pass" if fmt_ok else "fail",
               f"{meta.get('format')} v{meta.get('schema_version')}")
    missing_meta = [k for k in ("id", "name", "licence") if not meta.get(k)]
    report.add("translation metadata and licence", "fail" if missing_meta else "pass",
               ("missing: " + ", ".join(missing_meta)) if missing_meta else
               f"{meta.get('name')}; licence: {meta.get('licence')}")
    missing_src = [k for k in ("source_url", "source_sha256", "retrieved") if not meta.get(k)]
    report.add("source provenance recorded", "warn" if missing_src else "pass",
               ("missing: " + ", ".join(missing_src)) if missing_src else meta.get("source_url", ""))

    # Canon ---------------------------------------------------------------------
    # Packs that declare the reference versification (the KJV) are held to it
    # strictly; other translations may legitimately differ or be partial.
    ref_name = "kjv"
    strict = meta.get("versification", "").lower() == ref_name
    present = {bid for (bid,) in conn.execute("SELECT id FROM books")}
    missing_books = [b.name for b in cat if b.id not in present]
    report.stats["books"] = len(present)
    report.add("all 66 canonical books present",
               "pass" if not missing_books else ("fail" if strict or not present else "warn"),
               ("missing: " + ", ".join(missing_books[:max_details])) if missing_books else "")
    bad_order = conn.execute(
        "SELECT count(*) FROM books WHERE ord NOT BETWEEN 1 AND 66"
    ).fetchone()[0]
    report.add("canonical book order", "fail" if bad_order else "pass")

    # Verse rows -----------------------------------------------------------------
    actual: dict[str, dict[int, list[int]]] = {}
    empty = []
    rows = conn.execute("SELECT book_id, chapter, verse, text FROM verses ORDER BY id").fetchall()
    for b, c, v, t in rows:
        actual.setdefault(b, {}).setdefault(c, []).append(v)
        if not t.strip():
            empty.append(f"{b} {c}:{v}")
    report.stats["chapters"] = sum(len(ch) for ch in actual.values())
    report.stats["verses"] = len(rows)
    report.add("no empty verses", "fail" if empty else "pass", ", ".join(empty[:max_details]))

    gaps = []
    for b, chs in actual.items():
        nums = sorted(chs)
        if nums != list(range(1, len(nums) + 1)):
            gaps.append(f"{b}: chapters {nums[:5]}…")
        for c, vs in chs.items():
            if vs != list(range(1, len(vs) + 1)):
                gaps.append(f"{b} {c}")
    report.add("sequential chapter and verse numbering", "fail" if gaps else "pass",
               ("not sequential: " + ", ".join(gaps[:max_details])) if gaps else "")

    stored = {}
    for b, c, n in conn.execute("SELECT book_id, chapter, verses FROM chapters"):
        stored[(b, c)] = n
    derived = {(b, c): len(vs) for b, chs in actual.items() for c, vs in chs.items()}
    book_ch = dict(conn.execute("SELECT id, chapters FROM books"))
    consistent = stored == derived and all(book_ch.get(b) == len(chs) for b, chs in actual.items())
    report.add("chapter tables agree with verse rows", "pass" if consistent else "fail")

    # Versification against reference ------------------------------------------------
    expected = reference_versification(ref_name)
    diffs = []
    for b in cat:
        if b.id not in actual:
            continue
        exp = expected.get(b.id, [])
        got = actual[b.id]
        if len(got) != len(exp):
            diffs.append(f"{b.name}: {len(got)} chapters, expected {len(exp)}")
        for c in range(1, max(len(exp), len(got)) + 1):
            e = exp[c - 1] if c <= len(exp) else 0
            g = len(got.get(c, []))
            if e != g:
                diffs.append(f"{b.name} {c}: {g} verses, expected {e}")
    total_expected = sum(sum(v) for v in expected.values())
    report.stats["expected_verses"] = total_expected
    detail = f"compared with the {ref_name.upper()} versification table"
    if diffs:
        detail = f"{len(diffs)} difference(s): " + "; ".join(diffs[:max_details])
    report.add(
        f"chapter and verse counts match {ref_name.upper()} versification",
        "pass" if not diffs else ("fail" if strict else "warn"),
        detail,
    )

    # Search index and digest ------------------------------------------------------
    (fts_rows,) = conn.execute("SELECT count(*) FROM verses_fts_docsize").fetchone()
    report.add("full-text index covers every verse", "pass" if fts_rows == len(rows) else "fail",
               f"{fts_rows} indexed / {len(rows)} verses")
    digest = text_digest(rows)
    report.add("verse text digest matches import", "pass" if digest == meta.get("text_sha256") else "fail",
               digest[:16] + "…")
    report.add("verse count matches metadata",
               "pass" if str(len(rows)) == meta.get("verse_count") else "fail")

    # Checkpoints --------------------------------------------------------------------
    cp = _checkpoints(report.translation)
    if cp:
        lookup = {f"{b} {c}:{v}": t for b, c, v, t in rows}
        wrong = [k for k, t in cp["verses"].items() if lookup.get(k) != t]
        report.add(f"{len(cp['verses'])} checkpoint verses match exactly", "fail" if wrong else "pass",
                   ("mismatch: " + ", ".join(wrong)) if wrong else "")
        first = f"{rows[0][0]} {rows[0][1]}:{rows[0][2]}" if rows else ""
        last = f"{rows[-1][0]} {rows[-1][1]}:{rows[-1][2]}" if rows else ""
        report.add("first verse is " + cp["first"], "pass" if first == cp["first"] else "fail", first)
        report.add("last verse is " + cp["last"], "pass" if last == cp["last"] else "fail", last)
    else:
        report.add("checkpoint verses", "warn", "no checkpoint file for this translation")

    if report.translation == "kjv":
        text = "".join(r[3] for r in rows)
        chars = {"’": "apostrophe", "æ": "ligature", "—": "em dash", "¶": "pilcrow"}
        lost = [name for ch, name in chars.items() if ch not in text]
        report.add("special characters preserved (’ æ — ¶)", "fail" if lost else "pass",
                   ("missing: " + ", ".join(lost)) if lost else "")
