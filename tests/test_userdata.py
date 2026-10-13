import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from qbible.errors import NotFoundError, UserDataError
from qbible.reference import parse
from qbible.userdata import LATEST_VERSION, MAX_HISTORY, UserStore, migrate, schema_version


class UserStoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "sub" / "user.sqlite"
        self.store = UserStore(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def test_created_private_with_latest_schema(self):
        self.store.bookmarks()
        self.assertTrue(self.path.exists())
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        conn = sqlite3.connect(self.path)
        self.assertEqual(schema_version(conn), LATEST_VERSION)

    def test_bookmark_lifecycle_and_deduplication(self):
        bm, created = self.store.add_bookmark("kjv", parse("John 3:16"), "Love")
        self.assertTrue(created)
        again, created = self.store.add_bookmark("kjv", parse("Jn 3:16"))
        self.assertFalse(created)
        self.assertEqual(again.id, bm.id)
        self.assertEqual(again.label, "Love")  # empty label does not erase
        relabel, _ = self.store.add_bookmark("kjv", parse("John 3:16"), "New")
        self.assertEqual(relabel.label, "New")
        self.store.add_bookmark("kjv", parse("Psalm 23"))
        self.assertEqual([b.reference.display() for b in self.store.bookmarks()], ["Psalm 23", "John 3:16"])
        self.assertEqual(self.store.update_bookmark_label(bm.id, "x").label, "x")
        self.store.remove_bookmark(bm.id)
        with self.assertRaises(NotFoundError):
            self.store.remove_bookmark(bm.id)
        with self.assertRaises(UserDataError):
            self.store.add_bookmark("kjv", parse("John 1"), "x" * 500)

    def test_history_moves_repeats_to_top_and_is_capped(self):
        for r in ["John 1", "John 2", "John 1"]:
            self.store.record("kjv", parse(r))
        self.assertEqual([h.reference.display() for h in self.store.history()], ["John 1", "John 2"])
        for c in range(1, 151):
            self.store.record("kjv", parse(f"Psalm {c}"))
        for c in range(1, 80):
            self.store.record("kjv", parse(f"Isaiah {min(c, 66)}"))
        self.assertLessEqual(len(self.store.history(1000)), MAX_HISTORY)
        self.assertEqual(self.store.last_position().reference.display(), "Isaiah 66")
        self.assertGreater(self.store.clear_history(), 0)
        self.assertIsNone(self.store.last_position())

    def test_stores_references_not_text(self):
        self.store.add_bookmark("kjv", parse("John 11:35"))
        conn = sqlite3.connect(self.path)
        row = conn.execute("SELECT ref_key FROM bookmarks").fetchone()
        self.assertEqual(row[0], "JHN.11.35")

    def test_migrations_are_idempotent_and_recorded(self):
        conn = sqlite3.connect(":memory:", isolation_level=None)
        self.assertEqual(schema_version(conn), 0)
        self.assertEqual(migrate(conn), [1])
        self.assertEqual(migrate(conn), [])
        rows = conn.execute("SELECT version, description FROM schema_migrations").fetchall()
        self.assertEqual(rows[0][0], 1)

    def test_newer_schema_refused(self):
        self.store.bookmarks()
        conn = sqlite3.connect(self.path)
        conn.execute("INSERT INTO schema_migrations VALUES (99, 'future', 'now')")
        conn.commit()
        conn.close()
        with self.assertRaises(UserDataError):
            self.store.bookmarks()

    def test_unwritable_location_reports_error(self):
        if os.geteuid() == 0:
            self.skipTest("root can write anywhere")
        ro = Path(self.dir.name) / "ro"
        ro.mkdir()
        os.chmod(ro, 0o500)
        try:
            with self.assertRaises(UserDataError):
                UserStore(ro / "x" / "user.sqlite").bookmarks()
        finally:
            os.chmod(ro, 0o700)


if __name__ == "__main__":
    unittest.main()
