from __future__ import annotations

import unittest

from sqlcockpit.db import Database
from sqlcockpit.erdiagram import build_model, render_model, to_dot, to_mermaid

from helpers import fixture_db


class TestErDiagram(unittest.TestCase):
    def test_model(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                model = build_model(db)
        self.assertIn("users", model["entities"])
        self.assertIn("posts", model["entities"])
        self.assertTrue(
            any(r["from_table"] == "posts" and r["to_table"] == "users" for r in model["relations"])
        )

    def test_mermaid(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                out = to_mermaid(build_model(db))
        self.assertIn("erDiagram", out)
        self.assertIn("users {", out)
        self.assertIn("INTEGER id PK", out)
        self.assertIn("||--o{", out)

    def test_dot(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                out = to_dot(build_model(db))
        self.assertIn("digraph ER {", out)
        self.assertIn("rankdir=LR;", out)
        self.assertIn("->", out)

    def test_render_dispatch(self) -> None:
        with fixture_db() as path:
            with Database(path) as db:
                model = build_model(db)
        self.assertIn("erDiagram", render_model(model, "mermaid"))
        self.assertIn("digraph", render_model(model, "dot"))
        with self.assertRaises(ValueError):
            render_model(model, "nope")


if __name__ == "__main__":
    unittest.main()
