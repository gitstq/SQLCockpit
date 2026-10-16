from __future__ import annotations

import io
import json
import os
import tempfile
import unittest

from sqlcockpit.db import Database
from sqlcockpit.shell import DeckShell

from helpers import build_fixture_db


class TestShell(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "fixture.db")
        build_fixture_db(self.db_path)
        self.db = Database(self.db_path)
        self.addCleanup(self.db.close)
        self.buf = io.StringIO()
        self.shell = DeckShell(self.db, stdout=self.buf)

    def _run(self, line: str):
        return self.shell.onecmd(line)

    def _out(self) -> str:
        return self.buf.getvalue()

    def test_meta_tables(self) -> None:
        self._run(".tables")
        out = self._out()
        self.assertIn("users", out)
        self.assertIn("posts", out)

    def test_meta_schema(self) -> None:
        self._run(".schema users")
        self.assertIn("email", self._out())

    def test_meta_count(self) -> None:
        self._run(".count users")
        self.assertIn("users: 3 rows", self._out())

    def test_meta_format_switch(self) -> None:
        self._run(".format json")
        self.assertIn("output format: json", self._out())
        self.buf.truncate(0)
        self.buf.seek(0)
        self._run("select name from users order by id limit 1;")
        data = json.loads(self._out())
        self.assertEqual(data[0]["name"], "Alice")

    def test_sql_execution(self) -> None:
        self._run("select 1;")
        self.assertIn("1", self._out())

    def test_sql_error_handling(self) -> None:
        self._run("select * from missing_table;")
        self.assertIn("error", self._out())

    def test_meta_limit(self) -> None:
        self._run(".limit abc")
        self.assertIn("usage", self._out())

    def test_meta_er(self) -> None:
        self._run(".er")
        self.assertIn("erDiagram", self._out())

    def test_meta_doctor(self) -> None:
        self._run(".doctor")
        self.assertIn("HEALTHY", self._out())

    def test_meta_quit(self) -> None:
        self.assertTrue(self._run(".quit"))

    def test_unknown_meta(self) -> None:
        self._run(".nope")
        self.assertIn("unknown meta command", self._out())

    def test_multiline_buffer(self) -> None:
        self._run("select")
        self.assertNotIn("error", self._out())
        self._run("1;")
        self.assertIn("1", self._out())


if __name__ == "__main__":
    unittest.main()
