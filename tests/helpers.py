"""Shared test fixtures."""
from __future__ import annotations

import contextlib
import os
import sqlite3
import tempfile
from typing import Any, Iterator

SCHEMA_SQL = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    age INTEGER,
    created_at TEXT
);
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    body TEXT,
    views INTEGER DEFAULT 0
);
CREATE INDEX idx_posts_user_id ON posts(user_id);
CREATE VIEW user_post_counts AS
    SELECT u.name AS name, COUNT(p.id) AS posts
    FROM users u LEFT JOIN posts p ON p.user_id = u.id
    GROUP BY u.id;
CREATE TRIGGER trg_users_touch AFTER INSERT ON users BEGIN
    UPDATE users SET created_at = '2026-01-01' WHERE id = NEW.id;
END;
"""

USERS = [
    ("Alice", "alice@example.com", 30, "2026-01-01"),
    ("Bob", "bob@example.com", 25, "2026-01-02"),
    ("Carol", "carol@example.com", 41, "2026-01-03"),
]

POSTS = [
    (1, "Hello World", "First post body", 10),
    (1, "Second Post", "Another body", 5),
    (2, "Bob writes", "Text here", 3),
]


def build_fixture_db(path: str) -> str:
    """Create the standard fixture database at ``path``."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executemany(
            "INSERT INTO users (name, email, age, created_at) VALUES (?, ?, ?, ?)", USERS
        )
        conn.executemany(
            "INSERT INTO posts (user_id, title, body, views) VALUES (?, ?, ?, ?)", POSTS
        )
        conn.commit()
    finally:
        conn.close()
    return path


@contextlib.contextmanager
def fixture_db() -> Iterator[str]:
    """Yield a temporary directory path holding a fixture database."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "fixture.db")
        build_fixture_db(db_path)
        yield db_path


def write_csv(path: str, text: str) -> str:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def write_text(path: str, text: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def run_main(argv: list) -> Any:
    """Run cli.main capturing stdout/stderr; returns (code, out, err)."""
    import contextlib
    import io

    from sqlcockpit.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()
