"""Importing additional translations (and not breaking the KJV)."""

import tempfile
import unittest
from pathlib import Path

from qbible.errors import DataError
from qbible.importer import TranslationInfo, import_file
from qbible.repository import Repository
from qbible.search import search
from qbible.validation import validate_pack

from .helpers import KJV_PACK, IsolatedEnv, require_kjv, run_cli

SAMPLE_TSV = """# book\tchapter\tverse\ttext — a tiny test translation (not scripture text)
JHN\t1\t1\tAlpha one.
John\t1\t2\tAlpha two, with an apostrophe’s test.
JHN\t1\t3\tAlpha three.
Jude\t1\t1\tBeta one.
"""


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.src = self.dir / "sample.tsv"
        self.src.write_text(SAMPLE_TSV, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def info(self, **kw):
        return TranslationInfo(id="test", name="Test Translation", licence="Test only", source_url="local",
                               retrieved="2026-10-13", **kw)

    def test_tsv_import_and_validation(self):
        out = self.dir / "packs" / "test.sqlite"
        r = import_file(self.src, "tsv", self.info(), out)
        self.assertEqual((r.verse_count, r.book_count), (4, 2))
        report = validate_pack(out)
        self.assertTrue(report.ok, report.to_text())
        statuses = {c.name: c.status for c in report.checks}
        self.assertEqual(statuses["all 66 canonical books present"], "warn")  # partial: warning only

    def test_strict_versification_fails_partial_text(self):
        out = self.dir / "strict.sqlite"
        import_file(self.src, "tsv", self.info(versification="kjv"), out)
        self.assertFalse(validate_pack(out).ok)

    def test_rejects_bad_input(self):
        cases = {
            "dup": "JHN\t1\t1\ta\nJHN\t1\t1\tb\n",
            "cols": "JHN\t1\t1\n",
            "book": "XYZ\t1\t1\ta\n",
            "num": "JHN\tone\t1\ta\n",
            "empty": "JHN\t1\t1\t \n",
            "zero": "JHN\t0\t1\ta\n",
        }
        for name, content in cases.items():
            with self.subTest(name):
                p = self.dir / f"{name}.tsv"
                p.write_text(content, encoding="utf-8")
                out = self.dir / f"{name}.sqlite"
                with self.assertRaises(DataError):
                    import_file(p, "tsv", self.info(), out)
                self.assertFalse(out.exists(), "no partial pack is left behind")
                self.assertEqual(list(self.dir.glob(".*.tmp")), [])

    def test_invalid_ids_and_overwrite(self):
        with self.assertRaises(DataError):
            import_file(self.src, "tsv", TranslationInfo(id="../evil", name="x"), self.dir / "x.sqlite")
        out = self.dir / "t.sqlite"
        import_file(self.src, "tsv", self.info(), out)
        with self.assertRaises(DataError):
            import_file(self.src, "tsv", self.info(), out)
        import_file(self.src, "tsv", self.info(), out, overwrite=True)

    def test_adding_a_translation_does_not_break_kjv(self):
        require_kjv()
        extra = self.dir / "extra"
        import_file(self.src, "tsv", self.info(), extra / "test.sqlite")
        repo = Repository([extra, KJV_PACK.parent])
        self.assertEqual(sorted(repo.ids()), ["kjv", "test"])
        kjv = repo.get("kjv")
        from qbible.reference import parse
        p = kjv.resolve(parse("John 3:16"))
        self.assertIn("For God so loved", kjv.passage_verses(p)[0].text)
        self.assertEqual(search(kjv, '"Jesus wept"').total, 1)
        test = repo.get("test")
        self.assertEqual(search(test, "alpha").total, 3)
        with self.assertRaises(Exception):
            test.resolve(parse("Genesis 1"))  # not in the test translation
        self.assertEqual(test.adjacent_chapter(test.books[0], 1, 1).book.id, "JUD")

    def test_cli_import_and_remove(self):
        require_kjv()
        with IsolatedEnv():
            code, out, err = run_cli("import", str(self.src), "--id", "test", "--name", "Test", "--licence", "Test only")
            self.assertEqual(code, 0, err)
            code, out, _ = run_cli("translations", "--json")
            self.assertEqual(sorted(t["id"] for t in __import__("json").loads(out)), ["kjv", "test"])
            code, out, _ = run_cli("-t", "test", "read", "John 1:1-3")
            self.assertEqual(code, 0)
            self.assertIn("Alpha three.", out)
            self.assertIn("For God so loved", run_cli("read", "John 3:16")[1])
            # cannot shadow or remove the bundled KJV
            self.assertEqual(run_cli("import", str(self.src), "--id", "kjv", "--name", "x", "--licence", "x")[0], 4)
            self.assertEqual(run_cli("remove-translation", "kjv")[0], 4)
            self.assertEqual(run_cli("remove-translation", "test")[0], 0)
            self.assertEqual(run_cli("-t", "test", "read", "John 1:1")[0], 4)

    def test_vpl_reader_excludes_apocrypha(self):
        vpl = self.dir / "x_vpl.txt"
        vpl.write_text("GEN 1:1 First.\nTOB 1:1 Tobit text.\nJOH 3:16 Mapped.\n", encoding="utf-8")
        r = import_file(vpl, "vpl", self.info(), self.dir / "v.sqlite")
        self.assertEqual(r.verse_count, 2)
        self.assertEqual(r.excluded, {"TOB": 1})


if __name__ == "__main__":
    unittest.main()
