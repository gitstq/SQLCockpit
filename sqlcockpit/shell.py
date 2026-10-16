"""Interactive SQL shell built on :mod:`cmd`."""
from __future__ import annotations

import cmd as _cmd
import shlex
import sys
from typing import Any, List, Optional

from . import __version__
from .bench import benchmark, render_bench
from .db import Database, DatabaseError
from .differ import diff_databases, render_diff
from .doctor import render_report, run_checks
from .erdiagram import build_model, render_model
from .formatters import FORMATS, render_table, to_format
from .importer import import_file
from .utils import quote_ident

BANNER = (
    "\n"
    "   ____   _____ __\n"
    "  / ___| / ___// /  ___  ____ _   ____\n"
    "  \\___ \\| |   / /  / _ \\/ __ \\ | / / _ \\\n"
    "  ___) | |___/ /__/  __/ / / / |/ /  __/\n"
    " |____/ \\____/_____/\\___/_/ /_/|___/\\___/   v%s\n"
    " SQLCockpit - zero-dependency terminal SQLite workbench\n"
    " Type .help for meta commands; SQL statements end with ';'\n"
) % __version__


class DeckShell(_cmd.Cmd):
    """Interactive shell: raw SQL plus ``.`` meta commands."""

    intro = BANNER
    prompt = "sqlcockpit> "

    def __init__(self, db: Database, stdout: Any = None) -> None:
        super().__init__(completekey="tab")
        self.stdout = stdout if stdout is not None else sys.stdout
        self.db = db
        self.fmt = "table"
        self.limit = 200
        self._buffer: List[str] = []

    # -- helpers --------------------------------------------------------
    def _out(self, text: str = "") -> None:
        self.stdout.write(text + "\n")

    def _table_or_json(self, fmt: str) -> str:
        return fmt if fmt in ("table", "json") else "table"

    # -- dispatch -------------------------------------------------------
    def onecmd(self, line: str) -> Optional[bool]:
        """Route ``.meta`` commands; everything else falls through to cmd.Cmd."""
        stripped = line.strip()
        if stripped.startswith("."):
            parts = stripped.split(None, 1)
            name = parts[0][1:]
            arg = parts[1] if len(parts) > 1 else ""
            func = getattr(self, "do_" + name, None)
            if func is None:
                self._out("unknown meta command: .%s (try .help)" % name)
                return None
            self.lastcmd = stripped
            return func(arg)
        return super().onecmd(line)

    def emptyline(self) -> bool:
        return False

    # -- SQL execution --------------------------------------------------
    def _run_sql(self, sql: str) -> None:
        try:
            columns, rows = self.db.query(sql, limit=self.limit)
        except DatabaseError as exc:
            self._out("error: %s" % exc)
            return
        if not columns:
            self.db.conn.commit()
            self._out("OK")
            return
        self._out(to_format(self.fmt, columns, rows))
        if self.limit and len(rows) == self.limit:
            self._out("(%d rows shown - use .limit N to adjust)" % self.limit)

    def default(self, line: str) -> None:
        statement = line.strip()
        if not statement:
            return
        self._buffer.append(statement)
        joined = " ".join(self._buffer)
        if joined.rstrip().endswith(";"):
            self._buffer = []
            self._run_sql(joined)
        # otherwise keep buffering for multi-line statements

    # -- meta commands --------------------------------------------------
    def do_tables(self, arg: str) -> None:
        rows = [[t, "table", self.db.row_count(t)] for t in self.db.tables()]
        rows += [[v, "view", "-"] for v in self.db.views()]
        self._out(to_format("table", ["name", "type", "rows"], rows))

    def do_schema(self, arg: str) -> None:
        table = arg.strip() or None
        names = [table] if table else self.db.tables()
        for name in names:
            if name not in self.db.tables():
                self._out("error: no such table: %s" % name)
                continue
            rows = [
                [
                    c["name"],
                    c["type"] or "-",
                    "PK" if c["pk"] else "",
                    "NOT NULL" if c["notnull"] else "",
                    "" if c["default"] is None else str(c["default"]),
                ]
                for c in self.db.columns(name)
            ]
            self._out(render_table(["column", "type", "key", "constraint", "default"], rows))

    def do_indexes(self, arg: str) -> None:
        table = arg.strip() or None
        names = [table] if table else self.db.tables()
        rows = []
        for name in names:
            for idx in self.db.index_list(name):
                rows.append(
                    [name, idx["name"], "unique" if idx["unique"] else "", idx["origin"]]
                )
        self._out(render_table(["table", "index", "kind", "origin"], rows))

    def do_count(self, arg: str) -> None:
        table = arg.strip()
        if not table:
            self._out("usage: .count TABLE")
            return
        try:
            self._out("%s: %d rows" % (table, self.db.row_count(table)))
        except DatabaseError as exc:
            self._out("error: %s" % exc)

    def do_format(self, arg: str) -> None:
        fmt = arg.strip().lower()
        if fmt not in FORMATS:
            self._out("usage: .format %s" % "|".join(FORMATS))
            return
        self.fmt = fmt
        self._out("output format: %s" % fmt)

    def do_limit(self, arg: str) -> None:
        try:
            value = int(arg.strip())
        except ValueError:
            self._out("usage: .limit N (0 = unlimited)")
            return
        self.limit = max(0, value)
        self._out("row limit: %s" % ("unlimited" if value == 0 else value))

    def do_export(self, arg: str) -> None:
        parts = shlex.split(arg)
        if not parts:
            self._out("usage: .export TABLE [FILE]")
            return
        table = parts[0]
        path = parts[1] if len(parts) > 1 else None
        try:
            columns, rows = self.db.query("SELECT * FROM %s" % quote_ident(table))
        except DatabaseError as exc:
            self._out("error: %s" % exc)
            return
        text = to_format(self.fmt, columns, rows)
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
            self._out("exported %d rows to %s" % (len(rows), path))
        else:
            self._out(text)

    def do_import(self, arg: str) -> None:
        parts = shlex.split(arg)
        if len(parts) < 2:
            self._out("usage: .import TABLE FILE [--if-exists fail|replace|append]")
            return
        table, path = parts[0], parts[1]
        if_exists = "fail"
        if "--if-exists" in parts:
            idx = parts.index("--if-exists")
            if idx + 1 < len(parts):
                if_exists = parts[idx + 1]
        try:
            report = import_file(self.db, table, path, if_exists=if_exists)
        except (DatabaseError, OSError) as exc:
            self._out("error: %s" % exc)
            return
        self._out(
            "imported %d rows into %s (created=%s)"
            % (report["inserted"], report["table"], report["created"])
        )

    def do_er(self, arg: str) -> None:
        fmt = arg.strip() or "mermaid"
        try:
            self._out(render_model(build_model(self.db), fmt))
        except ValueError as exc:
            self._out("error: %s" % exc)

    def do_doctor(self, arg: str) -> None:
        self._out(render_report(run_checks(self.db), self._table_or_json(self.fmt)))

    def do_diff(self, arg: str) -> None:
        path = arg.strip()
        if not path:
            self._out("usage: .diff OTHER_DB_PATH")
            return
        try:
            with Database(path, readonly=True) as other:
                result = diff_databases(self.db, other, with_data=True)
        except DatabaseError as exc:
            self._out("error: %s" % exc)
            return
        self._out(render_diff(result, self._table_or_json(self.fmt)))

    def do_bench(self, arg: str) -> None:
        sql = arg.strip().rstrip(";")
        if not sql:
            self._out("usage: .bench SQL")
            return
        try:
            result = benchmark(self.db, sql, runs=5)
        except DatabaseError as exc:
            self._out("error: %s" % exc)
            return
        self._out(render_bench(result, self._table_or_json(self.fmt)))

    def do_quit(self, arg: str) -> bool:
        self._out("bye")
        return True

    def do_exit(self, arg: str) -> bool:
        return self.do_quit(arg)

    def do_EOF(self, arg: str) -> bool:
        self._out("")
        return True


def _load_readline_history() -> Optional[str]:
    try:
        import os

        import readline
    except ImportError:
        return None
    path = os.path.join(os.path.expanduser("~"), ".sqlcockpit_history")
    try:
        readline.read_history_file(path)
    except (OSError, FileNotFoundError):
        pass
    return path


def _save_readline_history() -> None:
    try:
        import os

        import readline
    except ImportError:
        return
    path = os.path.join(os.path.expanduser("~"), ".sqlcockpit_history")
    try:
        readline.write_history_file(path)
    except OSError:
        pass


def run_shell(db_path: str) -> int:
    """Open ``db_path`` and run the interactive shell."""
    _load_readline_history()
    with Database(db_path) as db:
        shell = DeckShell(db)
        try:
            shell.cmdloop()
        except KeyboardInterrupt:
            shell._out("bye")
        finally:
            _save_readline_history()
    return 0
