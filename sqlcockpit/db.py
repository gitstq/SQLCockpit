"""SQLite connection handling and schema introspection."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import quote_ident


class DatabaseError(Exception):
    """User-facing database error."""


class Database:
    """Thin wrapper around a :mod:`sqlite3` connection with introspection.

    The wrapper is deliberately dependency-free: everything is built on the
    Python standard library so SQLCockpit runs on any stock Python install.
    """

    def __init__(self, path: str, readonly: bool = False, must_exist: bool = True) -> None:
        self.path = str(path)
        self.readonly = readonly
        exists = os.path.exists(self.path)
        if not exists and (must_exist or readonly):
            raise DatabaseError("database file not found: %s" % self.path)
        try:
            if readonly:
                uri = Path(self.path).resolve().as_uri() + "?mode=ro"
                self.conn = sqlite3.connect(uri, uri=True)
            else:
                self.conn = sqlite3.connect(self.path)
        except sqlite3.Error as exc:
            raise DatabaseError("cannot open database: %s" % exc) from exc
        self.conn.row_factory = sqlite3.Row

    # -- lifecycle ------------------------------------------------------
    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- low level ------------------------------------------------------
    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        try:
            return self.conn.execute(sql, params)
        except sqlite3.Error as exc:
            raise DatabaseError("sql error: %s" % exc) from exc

    def query(
        self, sql: str, params: Tuple[Any, ...] = (), limit: Optional[int] = None
    ) -> Tuple[List[str], List[Tuple[Any, ...]]]:
        """Execute ``sql`` and return ``(columns, rows)``."""
        cur = self.execute(sql, params)
        if cur.description is None:
            return [], []
        columns = [d[0] for d in cur.description]
        if limit and limit > 0:
            rows = cur.fetchmany(limit)
        else:
            rows = cur.fetchall()
        return columns, [tuple(r) for r in rows]

    def scalar(self, sql: str, params: Tuple[Any, ...] = ()) -> Any:
        row = self.execute(sql, params).fetchone()
        return None if row is None else row[0]

    # -- introspection --------------------------------------------------
    def tables(self) -> List[str]:
        return self._names("table")

    def views(self) -> List[str]:
        return self._names("view")

    def triggers(self) -> List[str]:
        return self._names("trigger")

    def _names(self, kind: str) -> List[str]:
        rows = self.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%' ORDER BY name",
            (kind,),
        ).fetchall()
        return [r[0] for r in rows]

    def object_sql(self, kind: str, name: str) -> Optional[str]:
        return self.scalar(
            "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?", (kind, name)
        )

    def table_sql(self, name: str) -> Optional[str]:
        return self.object_sql("table", name)

    def columns(self, table: str) -> List[Dict[str, Any]]:
        rows = self.execute("PRAGMA table_info(%s)" % quote_ident(table)).fetchall()
        return [
            {
                "name": r[1],
                "type": (r[2] or "").upper(),
                "notnull": bool(r[3]),
                "default": r[4],
                "pk": int(r[5]),
            }
            for r in rows
        ]

    def primary_key(self, table: str) -> List[str]:
        cols = self.columns(table)
        pk = [c for c in cols if c["pk"] > 0]
        pk.sort(key=lambda c: c["pk"])
        return [c["name"] for c in pk]

    def foreign_keys(self, table: str) -> List[Dict[str, Any]]:
        rows = self.execute("PRAGMA foreign_key_list(%s)" % quote_ident(table)).fetchall()
        return [
            {
                "id": r[0],
                "seq": r[1],
                "table": r[2],
                "from": r[3],
                "to": r[4],
                "on_update": r[5],
                "on_delete": r[6],
                "match": r[7],
            }
            for r in rows
        ]

    def index_list(self, table: str) -> List[Dict[str, Any]]:
        rows = self.execute("PRAGMA index_list(%s)" % quote_ident(table)).fetchall()
        return [
            {"name": r[1], "unique": bool(r[2]), "origin": r[3], "partial": bool(r[4])}
            for r in rows
        ]

    def row_count(self, table: str) -> int:
        return int(self.scalar("SELECT COUNT(*) FROM %s" % quote_ident(table)))

    def size_bytes(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def schema_snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot of the whole schema."""
        snap: Dict[str, Any] = {"tables": {}, "views": {}, "indexes": {}, "triggers": {}}
        for name in self.tables():
            snap["tables"][name] = {
                "columns": self.columns(name),
                "foreign_keys": self.foreign_keys(name),
                "indexes": self.index_list(name),
                "sql": self.table_sql(name),
            }
        for name in self.views():
            snap["views"][name] = {"sql": self.object_sql("view", name)}
        for name in self.triggers():
            snap["triggers"][name] = {
                "sql": self.object_sql("trigger", name),
                "table": self.scalar(
                    "SELECT tbl_name FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                    (name,),
                ),
            }
        rows = self.execute(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
        ).fetchall()
        for r in rows:
            snap["indexes"][r[0]] = {"table": r[1], "sql": r[2]}
        return snap
