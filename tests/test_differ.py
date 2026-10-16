from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from sqlcockpit.db import Database
from sqlcockpit.differ import diff_databases, diff_snapshots, diff_table_data

from helpers import build_fixture_db


def _modified_db(path: str) -> str:
    """Fixture db plus one extra table, a changed column and one extra row."""
    build_fixture_db(path)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tags (id INTEGER PRIMARY KEY, label TEXT);
        INSERT INTO tags (label) VALUES ('x');
        CREATE INDEX idx_users_age ON users(age);
        INSERT INTO posts (user_id, title, body, views) VALUES (3, 'New', 'Body', 1);
        """
    )
    conn.commit()
    conn.close()
    return path


class TestDiffer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.left_path = os.path.join(self.tmp.name, "left.db")
        self.right_path = os.path.join(self.tmp.name, "right.db")
        build_fixture_db(self.left_path)
        _modified_db(self.right_path)

    def test_schema_diff(self) -> None:
        with Database(self.left_path, readonly=True) as left, Database(
            self.right_path, readonly=True
        ) as right:
            changes = diff_snapshots(left.schema_snapshot(), right.schema_snapshot())
        kinds = {(c["kind"], c.get("object")) for c in changes}
        self.assertIn(("table_added", "tags"), kinds)
        self.assertIn(("index_added", "users"), kinds)

    def test_data_diff(self) -> None:
        with Database(self.left_path, readonly=True) as left, Database(
            self.right_path, readonly=True
        ) as right:
            entry = diff_table_data(left, right, "posts")
        self.assertEqual(entry["strategy"], "primary_key")
        self.assertEqual(entry["only_in_right"], 1)
        self.assertEqual(entry["only_in_left"], 0)
        self.assertEqual(entry["changed"], 0)

    def test_full_diff_databases(self) -> None:
        with Database(self.left_path, readonly=True) as left, Database(
            self.right_path, readonly=True
        ) as right:
            result = diff_databases(left, right, with_data=True)
        self.assertTrue(result["schema_changed"])
        self.assertIn("posts", result["data_changes"])
        self.assertFalse(result["identical"])

    def test_identical_databases(self) -> None:
        clone = os.path.join(self.tmp.name, "clone.db")
        build_fixture_db(clone)
        with Database(self.left_path, readonly=True) as left, Database(
            clone, readonly=True
        ) as right:
            result = diff_databases(left, right, with_data=True)
        self.assertTrue(result["identical"])
        self.assertEqual(result["schema_changes"], [])


if __name__ == "__main__":
    unittest.main()
