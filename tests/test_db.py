from __future__ import annotations

import unittest

from sqlcockpit.db import Database, DatabaseError

from helpers import build_fixture_db, fixture_db


class TestDatabase(unittest.TestCase):
    def test_lists_objects(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                self.assertEqual(db.tables(), ["posts", "users"])
                self.assertEqual(db.views(), ["user_post_counts"])
                self.assertEqual(db.triggers(), ["trg_users_touch"])

    def test_columns_and_pk(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                cols = {c["name"]: c for c in db.columns("users")}
                self.assertEqual(cols["id"]["pk"], 1)
                self.assertEqual(cols["name"]["type"], "TEXT")
                self.assertTrue(cols["name"]["notnull"])
                self.assertEqual(db.primary_key("users"), ["id"])

    def test_foreign_keys(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                fks = db.foreign_keys("posts")
                self.assertEqual(len(fks), 1)
                self.assertEqual(fks[0]["table"], "users")
                self.assertEqual(fks[0]["from"], "user_id")

    def test_row_count(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                self.assertEqual(db.row_count("users"), 3)
                self.assertEqual(db.row_count("posts"), 3)

    def test_query_limit(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                columns, rows = db.query("SELECT id FROM users", limit=2)
                self.assertEqual(columns, ["id"])
                self.assertEqual(len(rows), 2)

    def test_snapshot_shape(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                snap = db.schema_snapshot()
                self.assertIn("users", snap["tables"])
                self.assertIn("user_post_counts", snap["views"])
                self.assertIn("trg_users_touch", snap["triggers"])
                self.assertIn("idx_posts_user_id", snap["indexes"])
                self.assertIn("sql", snap["tables"]["users"])

    def test_missing_database_raises(self) -> None:
        with self.assertRaises(DatabaseError):
            Database("/nonexistent/path/nope.db", readonly=True)

    def test_readonly_blocks_write(self) -> None:
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ro.db")
            build_fixture_db(path)
            with Database(path, readonly=True) as db:
                with self.assertRaises(DatabaseError):
                    db.execute("INSERT INTO users (name) VALUES ('x')")


if __name__ == "__main__":
    unittest.main()
