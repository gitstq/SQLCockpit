from __future__ import annotations

import json
import unittest

from sqlcockpit.db import Database
from sqlcockpit.doctor import render_report, run_checks

from helpers import fixture_db


class TestDoctor(unittest.TestCase):
    def test_checks(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                report = run_checks(db)
        self.assertEqual(report["integrity_check"], ["ok"])
        self.assertEqual(report["foreign_key_violations"], 0)
        self.assertTrue(report["healthy"])
        self.assertEqual(report["objects"]["tables"], 2)
        self.assertEqual(report["objects"]["views"], 1)
        self.assertEqual(report["objects"]["triggers"], 1)
        self.assertEqual(len(report["tables"]), 2)

    def test_render_json(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                report = run_checks(db)
        data = json.loads(render_report(report, "json"))
        self.assertEqual(data["integrity_check"], ["ok"])

    def test_render_table(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                report = run_checks(db)
        text = render_report(report, "table")
        self.assertIn("Status", text)
        self.assertIn("users", text)


if __name__ == "__main__":
    unittest.main()
