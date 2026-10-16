from __future__ import annotations

import json
import os
import tempfile
import unittest

from helpers import build_fixture_db, run_main, write_csv


class TestCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "fixture.db")
        build_fixture_db(self.db)
        self.other = os.path.join(self.tmp.name, "other.db")
        build_fixture_db(self.other)
        conn = __import__("sqlite3").connect(self.other)
        conn.executescript(
            "CREATE TABLE tags (id INTEGER PRIMARY KEY, label TEXT);"
            "INSERT INTO tags (label) VALUES ('x');"
        )
        conn.commit()
        conn.close()

    def test_version(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            run_main(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_open(self) -> None:
        code, out, _ = run_main(["open", self.db])
        self.assertEqual(code, 0)
        self.assertIn("Database", out)
        self.assertIn("users", out)

    def test_schema(self) -> None:
        code, out, _ = run_main(["schema", self.db])
        self.assertEqual(code, 0)
        self.assertIn("users", out)
        self.assertIn("email", out)

    def test_query_table(self) -> None:
        code, out, _ = run_main(["query", self.db, "select", "name", "from", "users"])
        self.assertEqual(code, 0)
        self.assertIn("Alice", out)

    def test_query_json(self) -> None:
        code, out, _ = run_main(
            ["query", self.db, "select", "id", "from", "users", "order", "by", "id", "--format", "json"]
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual([r["id"] for r in data], [1, 2, 3])

    def test_query_limit(self) -> None:
        code, out, _ = run_main(
            ["query", self.db, "select", "id", "from", "users", "--limit", "1", "--format", "json"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 1)

    def test_query_missing_db(self) -> None:
        code, _, err = run_main(["query", "/nonexistent/nope.db", "select", "1"])
        self.assertEqual(code, 1)
        self.assertIn("error", err)

    def test_export_json(self) -> None:
        code, out, _ = run_main(["export", self.db, "--table", "users", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 3)

    def test_export_to_file(self) -> None:
        target = os.path.join(self.tmp.name, "users.csv")
        code, _, _ = run_main(["export", self.db, "--table", "users", "--output", target])
        self.assertEqual(code, 0)
        with open(target, encoding="utf-8") as fh:
            self.assertIn("Alice", fh.read())

    def test_import(self) -> None:
        csv_path = write_csv(os.path.join(self.tmp.name, "s.csv"), "id,name\n1,x\n2,y\n")
        code, out, _ = run_main(["import", self.db, "--table", "scores", "--file", csv_path])
        self.assertEqual(code, 0)
        self.assertIn("imported 2 rows", out)
        code, out, _ = run_main(["query", self.db, "select", "count(*)", "as", "n", "from", "scores", "--format", "json"])
        self.assertEqual(json.loads(out)[0]["n"], 2)

    def test_diff(self) -> None:
        code, out, _ = run_main(["diff", self.db, self.other])
        self.assertEqual(code, 0)
        self.assertIn("tags", out)
        self.assertIn("identical: no", out)

    def test_diff_data(self) -> None:
        code, out, _ = run_main(["diff", self.db, self.other, "--data"])
        self.assertEqual(code, 0)
        self.assertIn("Data changes", out)

    def test_er_mermaid(self) -> None:
        code, out, _ = run_main(["er", self.db])
        self.assertEqual(code, 0)
        self.assertIn("erDiagram", out)
        self.assertIn("||--o{", out)

    def test_doctor(self) -> None:
        code, out, _ = run_main(["doctor", self.db])
        self.assertEqual(code, 0)
        self.assertIn("HEALTHY", out)

    def test_bench(self) -> None:
        code, out, _ = run_main(["bench", self.db, "select", "*", "from", "users"])
        self.assertEqual(code, 0)
        self.assertIn("avg", out)

    def test_bench_rejects_writes(self) -> None:
        code, _, err = run_main(["bench", self.db, "delete", "from", "users"])
        self.assertEqual(code, 1)
        self.assertIn("read-only", err)


if __name__ == "__main__":
    unittest.main()
