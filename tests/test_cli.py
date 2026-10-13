import json
import os
import subprocess
import sys
import unittest

from qbible import __version__

from .helpers import ROOT, IsolatedEnv, require_kjv, run_cli


class CLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_kjv()

    def setUp(self):
        self.env = IsolatedEnv().__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)

    def test_help_and_version(self):
        code, out, _ = run_cli("--version")
        self.assertEqual(code, 0)
        code, out, _ = run_cli()
        self.assertEqual(code, 0)
        self.assertIn("usage: qbible", out)
        self.assertIn("search", out)

    def test_version_subprocess(self):
        r = subprocess.run([sys.executable, "-m", "qbible", "--version"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), f"qbible {__version__}")
        r = subprocess.run([sys.executable, "-m", "qbible", "read", "--help"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("--no-numbers", r.stdout)

    def test_read_verse(self):
        code, out, err = run_cli("read", "John", "3:16")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], "John 3:16 (KJV)")
        self.assertIn("16 For God so loved the world", out)
        self.assertNotIn("¶", out)

    def test_read_range_and_chapter(self):
        code, out, _ = run_cli("read", "John 3:16-21")
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines()[2:] if l]
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith("16 ") and lines[-1].startswith("21 "))
        code, out, _ = run_cli("read", "Psalm", "23")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Psalm 23 (KJV)"))
        self.assertEqual(len(out.strip().splitlines()), 2 + 6)
        code, out, _ = run_cli("chapter", "Romans", "8")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 2 + 39)

    def test_read_examples_from_spec(self):
        for ref, first in [("Genesis 1:1-10", "Genesis 1:1-10"), ("Romans 8", "Romans 8"),
                           ("1 John 4:8", "1 John 4:8"), ("Rev 21:1-4", "Revelation 21:1-4")]:
            with self.subTest(ref=ref):
                code, out, _ = run_cli("read", *ref.split())
                self.assertEqual(code, 0)
                self.assertEqual(out.splitlines()[0], f"{first} (KJV)")

    def test_cross_chapter_range_has_chapter_headings(self):
        code, out, _ = run_cli("read", "Gen 1:31-2:2")
        self.assertEqual(code, 0)
        self.assertIn("Genesis 1\n31 ", out)
        self.assertIn("Genesis 2\n 1 ", out)  # numbers right-aligned to the widest (31)

    def test_pipe_friendly_plain_output(self):
        code, out, _ = run_cli("read", "Psalm 23:1", "--colour", "always")
        self.assertIn("\033[", out)
        code, out, _ = run_cli("--plain", "read", "Psalm 23:1")
        self.assertNotIn("\033[", out)
        code, out, _ = run_cli("read", "Psalm 23:1")  # StringIO is not a TTY
        self.assertNotIn("\033[", out)
        self.assertIn("The LORD is my shepherd", out)
        code, out, _ = run_cli("read", "Psalm 23:1", "--no-numbers", "--no-heading", "--supplied", "brackets")
        self.assertEqual(out, "A Psalm of David. The LORD [is] my shepherd; I shall not want.\n")

    def test_no_color_env_respected(self):
        os.environ["NO_COLOR"] = "1"
        r = subprocess.run([sys.executable, "-m", "qbible", "read", "John 11:35"], cwd=ROOT,
                           capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("\033[", r.stdout)

    def test_json_output(self):
        code, out, _ = run_cli("read", "John 11:35", "--json")
        data = json.loads(out)
        self.assertEqual(data["reference"]["key"], "JHN.11.35")
        self.assertEqual(data["chapters"][0]["verses"][0]["text"], "Jesus wept.")

    def test_invalid_references_exit_3(self):
        for args, msg in [(("read", "John", "22"), "no chapter 22"),
                          (("read", "John 3:37"), "no verse 37"),
                          (("read", "Hezekiah 1"), "Unknown book"),
                          (("read", "3:16"), "does not look like")]:
            with self.subTest(args=args):
                code, out, err = run_cli(*args)
                self.assertEqual(code, 3)
                self.assertEqual(out, "")
                self.assertIn(msg, err)

    def test_usage_errors_exit_2(self):
        self.assertEqual(run_cli("frobnicate")[0], 2)
        self.assertEqual(run_cli("read")[0], 2)
        self.assertEqual(run_cli("search", "love", "--limit", "0")[0], 2)
        self.assertEqual(run_cli("chapter", "John", "3:16")[0], 2)

    def test_missing_translation_exit_4(self):
        code, _, err = run_cli("-t", "nope", "read", "John 1:1")
        self.assertEqual(code, 4)
        self.assertIn("not installed", err)

    def test_search_word_and_phrase(self):
        code, out, err = run_cli("search", "faith without works")  # one argument with spaces = phrase
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "James 2:20  But wilt thou know, O vain man, that faith without works is dead?",
            "James 2:26  For as the body without the spirit is dead, so faith without works is dead also.",
        ])
        self.assertIn("2 verses match", err)
        code, out, _ = run_cli("search", "faith", "without", "works")  # separate words
        self.assertGreater(len(out.splitlines()), 2)
        code, out, _ = run_cli("search", "Jesus wept")
        self.assertEqual(out.strip(), "John 11:35  Jesus wept.")

    def test_search_limit_page_count(self):
        code, out, err = run_cli("search", "love", "--limit", "5")
        self.assertEqual(len(out.splitlines()), 5)
        self.assertIn("--page 2", err)
        code, out2, _ = run_cli("search", "love", "--limit", "5", "--page", "2")
        self.assertEqual(len(out2.splitlines()), 5)
        self.assertNotEqual(out, out2)
        code, out, _ = run_cli("search", "love", "--count")
        self.assertTrue(out.strip().isdigit())
        self.assertEqual(code, 0)

    def test_search_no_results_exit_1(self):
        code, out, err = run_cli("search", "xylophone")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("No verses match", err)
        self.assertEqual(run_cli("search", "!!!")[0], 2)

    def test_search_context(self):
        code, out, _ = run_cli("search", "fear not", "--context", "--limit", "1")
        self.assertIn("Genesis 15:1", out)
        self.assertIn("  Genesis 15:2", out)

    def test_ref_command(self):
        code, out, _ = run_cli("ref", "1jn", "4.8")
        self.assertEqual(out.strip(), "1 John 4:8\t1JN.4.8")

    def test_books(self):
        code, out, _ = run_cli("books")
        self.assertIn("Genesis", out)
        self.assertIn("Revelation", out)
        code, out, _ = run_cli("books", "--json")
        self.assertEqual(len(json.loads(out)), 66)

    def test_next_previous_use_stored_position(self):
        code, _, err = run_cli("next")
        self.assertEqual(code, 1)
        self.assertIn("No reading position", err)
        run_cli("read", "Malachi 4")
        code, out, err = run_cli("next")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Matthew 1 (KJV)"))
        self.assertIn("Last position: Malachi 4", err)
        code, out, _ = run_cli("previous")
        self.assertTrue(out.startswith("Malachi 4 (KJV)"))
        code, out, _ = run_cli("next", "--from", "Revelation", "22")
        self.assertEqual(code, 1)
        code, out, _ = run_cli("prev", "--from", "Genesis 1")
        self.assertEqual(code, 1)

    def test_random(self):
        code, out, _ = run_cli("random", "--testament", "NT", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["reference"]["book"]["testament"], "NT")

    def test_bookmarks_and_history(self):
        self.assertEqual(run_cli("bookmark", "add", "Rom", "8:28", "--label", "All things")[0], 0)
        code, _, err = run_cli("bookmark", "add", "Romans 8:28")
        self.assertIn("already bookmarked", err)
        code, out, _ = run_cli("bookmarks")
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn("Romans 8:28 (KJV)  All things", out)
        bid = out.split()[0]
        code, out, _ = run_cli("bookmark", "open", bid)
        self.assertTrue(out.startswith("Romans 8:28"))
        self.assertEqual(run_cli("bookmark", "remove", bid)[0], 0)
        self.assertEqual(run_cli("bookmark", "remove", bid)[0], 3)
        self.assertEqual(run_cli("bookmark", "add", "John 99:1")[0], 3)

        run_cli("read", "John 1")
        run_cli("read", "John 2")
        code, out, _ = run_cli("history", "--json")
        self.assertEqual([h["reference"] for h in json.loads(out)][:3], ["John 2", "John 1", "Romans 8:28"])
        run_cli("history", "clear")
        self.assertEqual(json.loads(run_cli("history", "--json")[1]), [])
        run_cli("read", "John 3", "--no-history")
        self.assertEqual(json.loads(run_cli("history", "--json")[1]), [])

    def test_config(self):
        self.assertEqual(run_cli("config", "set", "reading.verse_numbers", "false")[0], 0)
        code, out, _ = run_cli("read", "John 11:35")
        self.assertEqual(out.splitlines()[-1], "Jesus wept.")
        self.assertEqual(run_cli("config", "get", "reading.verse_numbers")[1].strip(), "false")
        self.assertEqual(run_cli("config", "set", "reading.verse_numbers", "maybe")[0], 2)
        self.assertEqual(run_cli("config", "set", "no.such", "x")[0], 2)
        run_cli("config", "unset", "reading.verse_numbers")
        self.assertIn("35 Jesus wept.", run_cli("read", "John 11:35")[1])

    def test_paths_and_completion(self):
        code, out, _ = run_cli("paths", "--json")
        data = json.loads(out)
        self.assertTrue(data["user_db"].startswith(str(self.env.tmp)))
        code, out, _ = run_cli("completion")
        self.assertIn("complete -F _qbible qbible", out)

    def test_validate_command(self):
        code, out, _ = run_cli("validate")
        self.assertEqual(code, 0)
        self.assertIn("RESULT: VALID", out)

    def test_broken_pipe_is_quiet(self):
        r = subprocess.run(f"'{sys.executable}' -m qbible read Psalm 119 | head -n 1", shell=True, cwd=ROOT,
                           capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(r.stdout, "Psalm 119 (KJV)\n")
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
