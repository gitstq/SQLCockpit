from __future__ import annotations

import csv
import io
import json
import unittest

from sqlcockpit.formatters import to_format

COLUMNS = ["id", "name", "score"]
ROWS = [
    (1, "Alice", 9.5),
    (2, "Bob", None),
    (3, "Carol", 7.25),
]


class TestFormatters(unittest.TestCase):
    def test_table(self) -> None:
        out = to_format("table", COLUMNS, ROWS)
        self.assertIn("┌", out)
        self.assertIn("Alice", out)
        self.assertIn("Carol", out)
        self.assertIn("│", out)

    def test_vertical(self) -> None:
        out = to_format("vertical", COLUMNS, ROWS)
        self.assertIn("1. row", out)
        self.assertIn("2. row", out)
        self.assertIn("Alice", out)

    def test_csv_roundtrip(self) -> None:
        out = to_format("csv", COLUMNS, ROWS)
        parsed = list(csv.reader(io.StringIO(out)))
        self.assertEqual(parsed[0], COLUMNS)
        self.assertEqual(parsed[1], ["1", "Alice", "9.5"])
        self.assertEqual(parsed[2], ["2", "Bob", ""])

    def test_json(self) -> None:
        data = json.loads(to_format("json", COLUMNS, ROWS))
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0], {"id": 1, "name": "Alice", "score": 9.5})
        self.assertIsNone(data[1]["score"])

    def test_jsonl(self) -> None:
        lines = to_format("jsonl", COLUMNS, ROWS).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[2])["name"], "Carol")

    def test_markdown(self) -> None:
        out = to_format("markdown", COLUMNS, ROWS)
        self.assertIn("| id | name | score |", out)
        self.assertIn("| --- | --- | --- |", out)
        self.assertIn("| 1 | Alice | 9.5 |", out)

    def test_unknown_format(self) -> None:
        with self.assertRaises(ValueError):
            to_format("nope", COLUMNS, ROWS)


if __name__ == "__main__":
    unittest.main()
