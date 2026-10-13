"""Bible data tests against the built KJV translation pack."""

import json
import sqlite3
import unittest

from qbible.books import RESOURCES, catalogue, reference_versification
from qbible.importer import sha256_file
from qbible.repository import TranslationPack
from qbible.validation import validate_pack

from .helpers import KJV_PACK, ROOT, require_kjv


class KJVDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_kjv()
        cls.pack = TranslationPack(KJV_PACK)
        cls.conn = cls.pack.conn

    def test_all_66_books_present_in_order(self):
        rows = self.conn.execute("SELECT id, ord, testament FROM books ORDER BY ord").fetchall()
        self.assertEqual(len(rows), 66)
        self.assertEqual([r[0] for r in rows], [b.id for b in catalogue()])
        self.assertEqual(rows[0][0], "GEN")
        self.assertEqual(rows[-1][0], "REV")

    def test_totals(self):
        (verses,) = self.conn.execute("SELECT count(*) FROM verses").fetchone()
        (chapters,) = self.conn.execute("SELECT count(*) FROM chapters").fetchone()
        self.assertEqual(verses, 31102)
        self.assertEqual(chapters, 1189)

    def test_chapter_and_verse_counts_match_independent_versification(self):
        expected = reference_versification("kjv")
        self.assertEqual(self.pack.verse_counts, expected)

    def test_verse_numbering_sequential(self):
        rows = self.conn.execute("SELECT book_id, chapter, verse FROM verses ORDER BY id").fetchall()
        last = None
        for b, c, v in rows:
            if last and last[0] == b and last[1] == c:
                self.assertEqual(v, last[2] + 1, f"{b} {c}:{v}")
            else:
                self.assertEqual(v, 1, f"{b} {c}:{v} should start a chapter")
            last = (b, c, v)

    def test_checkpoint_verses(self):
        cp = json.loads((RESOURCES / "checkpoints" / "kjv.json").read_text(encoding="utf-8"))
        cat = catalogue()
        for key, text in cp["verses"].items():
            book, cv = key.split()
            c, v = map(int, cv.split(":"))
            with self.subTest(key):
                self.assertEqual(self.pack.verse(cat.get(book), c, v).text, text)

    def test_first_and_last_passages(self):
        first = self.conn.execute("SELECT book_id, chapter, verse, text FROM verses ORDER BY id LIMIT 1").fetchone()
        last = self.conn.execute("SELECT book_id, chapter, verse, text FROM verses ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(first, ("GEN", 1, 1, "In the beginning God created the heaven and the earth."))
        self.assertEqual(last, ("REV", 22, 21, "The grace of our Lord Jesus Christ [be] with you all. Amen."))

    def test_unicode_preserved(self):
        text = "".join(t for (t,) in self.conn.execute("SELECT text FROM verses"))
        for ch in "’æÆ—¶":
            self.assertIn(ch, text)
        self.assertNotIn("�", text)  # no replacement characters from bad decoding

    def test_no_empty_or_whitespace_padded_verses(self):
        (n,) = self.conn.execute(
            "SELECT count(*) FROM verses WHERE trim(text) = '' OR text != trim(text)").fetchone()
        self.assertEqual(n, 0)

    def test_database_integrity(self):
        self.assertEqual(self.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_validation_report_passes(self):
        report = validate_pack(KJV_PACK)
        failures = [c for c in report.checks if c.status != "pass"]
        self.assertTrue(report.ok, failures)
        self.assertEqual(failures, [])

    def test_metadata_and_attribution(self):
        info = self.pack.info()
        self.assertEqual(info["id"], "kjv")
        self.assertEqual(info["name"], "King James Version")
        self.assertIn("Public Domain", info["licence"])
        self.assertIn("CrossWire", info["attribution"])
        self.assertEqual(info["source_url"], "https://ebible.org/Scriptures/eng-kjv_vpl.zip")
        self.assertEqual(info["verse_count"], 31102)
        sources = json.loads((ROOT / "data" / "sources" / "SOURCES.json").read_text())
        self.assertEqual(self.pack.meta["source_sha256"], sources["kjv"]["sha256"])

    def test_vendored_source_checksum(self):
        sources = json.loads((ROOT / "data" / "sources" / "SOURCES.json").read_text())
        self.assertEqual(sha256_file(ROOT / "data" / "sources" / sources["kjv"]["file"]), sources["kjv"]["sha256"])

    def test_pack_is_opened_read_only(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.conn.execute("UPDATE verses SET text = 'x' WHERE id = 1001001")

    def test_tamper_detection(self):
        import shutil
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "kjv.sqlite"
            shutil.copy(KJV_PACK, copy)
            c = sqlite3.connect(copy)
            c.execute("UPDATE verses SET text = 'Jesus laughed.' WHERE book_id='JHN' AND chapter=11 AND verse=35")
            c.commit()
            c.close()
            report = validate_pack(copy)
            self.assertFalse(report.ok)
            failed = {c.name for c in report.checks if c.status == "fail"}
            self.assertIn("verse text digest matches import", failed)


if __name__ == "__main__":
    unittest.main()
