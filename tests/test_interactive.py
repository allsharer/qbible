import os
import subprocess
import sys
import unittest

from .helpers import ROOT, IsolatedEnv, require_kjv


class InteractiveShellTests(unittest.TestCase):
    def test_session(self):
        require_kjv()
        script = "\n".join([
            "John 3:16",
            "n",            # next chapter from John 3 -> John 4
            "p",            # back to John 3
            "5",            # chapter 5 of the current book
            's "Jesus wept"',
            "bookmark Healing",
            "bookmarks",
            "Hezekiah 1",   # error is reported, session continues
            "Numbers 6:24",  # the book, not the 'numbers' toggle
            "where",
            "q",
        ]) + "\n"
        with IsolatedEnv():
            r = subprocess.run([sys.executable, "-m", "qbible", "--plain", "shell"], input=script, cwd=ROOT,
                               capture_output=True, text=True, env=os.environ.copy(), timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("John 3:16 (KJV)", out)
        self.assertIn("John 4 (KJV)", out)
        self.assertIn("John 5 (KJV)", out)
        self.assertIn("John 11:35  Jesus wept.", out)
        self.assertIn("Bookmarked John 5", out)
        self.assertIn("Unknown book: 'Hezekiah'", out)
        self.assertIn("Numbers 6:24 (KJV)", out)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
