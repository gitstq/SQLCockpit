from __future__ import annotations

import os
import tempfile
import unittest

from sqlcockpit.db import Database, DatabaseError
from sqlcockpit.importer import (
    detect_format,
    import_file,
    import_rows,
    infer_column_type,
)

from helpers import write_csv, write_text


class TestImporter(unittest.TestCase):
    def test_infer_types(self) -> None:
        self.assertEqual(infer_column_type(["1", "2", "3"]), "INTEGER")
        self.assertEqual(infer_column_type(["1.5", "2"]), "REAL")
        self.assertEqual(infer_column_type(["1", "abc"]), "TEXT")
        self.assertEqual(infer_column_type([None, None]), "TEXT")

    def test_detect_format(self) -> None:
        self.assertEqual(detect_format("a.csv"), "csv")
        self.assertEqual(detect_format("a.JSON"), "json")
        self.assertEqual(detect_format("a.txt"), "csv")

    def test_import_csv_creates_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            csv_path = write_csv(
                os.path.join(tmp, "data.csv"),
                "id,name,score\n1,Alice,9.5\n2,Bob,7\n",
            )
            with Database(db_path, must_exist=False) as db:
                report = import_file(db, "scores", csv_path)
                self.assertEqual(report["inserted"], 2)
                self.assertTrue(report["created"])
                self.assertEqual(db.row_count("scores"), 2)
                cols = {c["name"]: c["type"] for c in db.columns("scores")}
                self.assertEqual(cols["id"], "INTEGER")
                self.assertEqual(cols["name"], "TEXT")
                self.assertEqual(cols["score"], "REAL")

    def test_import_fail_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            csv_path = write_csv(os.path.join(tmp, "d.csv"), "a\n1\n")
            with Database(db_path, must_exist=False) as db:
                import_rows(db, "t", [{"a": "1"}])
                with self.assertRaises(DatabaseError):
                    import_file(db, "t", csv_path, if_exists="fail")

    def test_import_replace_and_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            csv_path = write_csv(os.path.join(tmp, "d.csv"), "a\n1\n2\n")
            with Database(db_path, must_exist=False) as db:
                import_file(db, "t", csv_path, if_exists="replace")
                self.assertEqual(db.row_count("t"), 2)
                import_file(db, "t", csv_path, if_exists="append")
                self.assertEqual(db.row_count("t"), 4)

    def test_import_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            json_path = write_text(
                os.path.join(tmp, "d.json"),
                '[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]',
            )
            with Database(db_path, must_exist=False) as db:
                report = import_file(db, "people", json_path)
                self.assertEqual(report["inserted"], 2)
                self.assertEqual(db.row_count("people"), 2)

    def test_no_create_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            csv_path = write_csv(os.path.join(tmp, "d.csv"), "a\n1\n")
            with Database(db_path, must_exist=False) as db:
                with self.assertRaises(DatabaseError):
                    import_file(db, "missing_table", csv_path, create=False)


if __name__ == "__main__":
    unittest.main()
