"""Command line interface for SQLCockpit."""
from __future__ import annotations

import argparse
import sys
from typing import Any, List, Optional

from . import __version__
from .utils import configure_streams
from .bench import benchmark, render_bench
from .db import Database, DatabaseError
from .differ import diff_databases, render_diff
from .doctor import apply_maintenance, render_report, run_checks
from .erdiagram import build_model, render_model
from .formatters import FORMATS, to_format
from .importer import IF_EXISTS_CHOICES, import_file
from .utils import human_bytes


def emit(text: str, output: Optional[str] = None) -> None:
    """Print ``text`` or write it to ``output`` when given."""
    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    else:
        print(text)


def _open_db(args: argparse.Namespace, readonly: bool = True) -> Database:
    return Database(args.database, readonly=readonly, must_exist=True)


def cmd_open(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=True) as db:
        tables = db.tables()
        views = db.views()
        triggers = db.triggers()
        indexes = [i for t in tables for i in db.index_list(t)]
        print("Database : %s" % db.path)
        print("Size     : %s" % human_bytes(db.size_bytes()))
        print("Engine   : SQLite %s" % db.scalar("SELECT sqlite_version()"))
        print(
            "Storage  : page_size=%s pages=%s freelist=%s journal=%s user_version=%s"
            % (
                db.scalar("PRAGMA page_size"),
                db.scalar("PRAGMA page_count"),
                db.scalar("PRAGMA freelist_count"),
                db.scalar("PRAGMA journal_mode"),
                db.scalar("PRAGMA user_version"),
            )
        )
        print(
            "Objects  : %d tables, %d views, %d indexes, %d triggers"
            % (len(tables), len(views), len(indexes), len(triggers))
        )
        if tables:
            rows = [[t, db.row_count(t), len(db.columns(t))] for t in tables]
            print(to_format("table", ["table", "rows", "columns"], rows))
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=True) as db:
        names = [args.table] if args.table else db.tables()
        rows = []
        for table in names:
            if table not in db.tables():
                raise DatabaseError("no such table: %s" % table)
            for col in db.columns(table):
                rows.append(
                    [
                        table,
                        col["name"],
                        col["type"] or "-",
                        "PK" if col["pk"] else "",
                        "NOT NULL" if col["notnull"] else "",
                        "" if col["default"] is None else str(col["default"]),
                    ]
                )
        emit(to_format(args.format, ["table", "column", "type", "key", "constraint", "default"], rows), args.output)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=False) as db:
        sql = " ".join(args.sql).strip()
        if not sql:
            raise DatabaseError("empty SQL statement")
        columns, rows = db.query(sql, limit=args.limit)
        if not columns:
            db.conn.commit()
            print("OK")
            return 0
        emit(to_format(args.format, columns, rows), args.output)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=True) as db:
        if args.table not in db.tables() and args.table not in db.views():
            raise DatabaseError("no such table or view: %s" % args.table)
        sql = "SELECT * FROM %s" % ('"' + args.table.replace('"', '""') + '"')
        if args.where:
            sql += " WHERE %s" % args.where
        columns, rows = db.query(sql, limit=args.limit)
        emit(to_format(args.format, columns, rows), args.output)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    with Database(args.database, readonly=False, must_exist=False) as db:
        report = import_file(
            db,
            args.table,
            args.file,
            fmt=args.format,
            if_exists=args.if_exists,
            create=not args.no_create,
            delimiter=args.delimiter,
        )
        print(
            "imported %d rows into %s (created=%s, source=%s)"
            % (report["inserted"], report["table"], report["created"], report["source"])
        )
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=True) as left, Database(
        args.other, readonly=True, must_exist=True
    ) as right:
        result = diff_databases(left, right, with_data=args.data)
        emit(render_diff(result, args.format), args.output)
    return 0


def cmd_er(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=True) as db:
        emit(render_model(build_model(db), args.format), args.output)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=False) as db:
        report = run_checks(db)
        actions = apply_maintenance(db, vacuum=args.vacuum, analyze=args.analyze)
        if actions:
            report = run_checks(db)
        emit(render_report(report, args.format), args.output)
        for action in actions:
            print(action)
    return 0 if report["healthy"] else 1


def cmd_bench(args: argparse.Namespace) -> int:
    with _open_db(args, readonly=True) as db:
        sql = " ".join(args.sql).strip()
        result = benchmark(db, sql, runs=args.runs)
        emit(render_bench(result, args.format), args.output)
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    from .shell import run_shell

    return run_shell(args.database)


def cmd_tui(args: argparse.Namespace) -> int:
    from .tui import run_tui

    return run_tui(args.database)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sqlcockpit",
        description="SQLCockpit - zero-dependency terminal SQLite workbench",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("open", help="show a database overview")
    p.add_argument("database")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("schema", help="inspect table schemas")
    p.add_argument("database")
    p.add_argument("--table", help="limit output to one table")
    p.add_argument("--format", choices=FORMATS, default="table")
    p.add_argument("--output", help="write to file instead of stdout")
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("query", help="run a SQL statement")
    p.add_argument("database")
    p.add_argument("sql", nargs="+", help="SQL statement")
    p.add_argument("--format", choices=FORMATS, default="table")
    p.add_argument("--limit", type=int, default=200, help="row limit (0 = unlimited)")
    p.add_argument("--output", help="write to file instead of stdout")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("export", help="export a table or view")
    p.add_argument("database")
    p.add_argument("--table", required=True)
    p.add_argument("--where", help="optional WHERE clause")
    p.add_argument("--format", choices=FORMATS, default="csv")
    p.add_argument("--limit", type=int, default=0, help="row limit (0 = unlimited)")
    p.add_argument("--output", help="write to file instead of stdout")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import", help="import CSV/JSON into a table")
    p.add_argument("database")
    p.add_argument("--table", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--format", choices=("csv", "json"), default=None, help="input format (default: by extension)")
    p.add_argument("--if-exists", choices=IF_EXISTS_CHOICES, default="fail")
    p.add_argument("--no-create", action="store_true", help="do not auto-create the table")
    p.add_argument("--delimiter", help="CSV delimiter override")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("diff", help="compare two databases")
    p.add_argument("database")
    p.add_argument("other", help="the other database file")
    p.add_argument("--data", action="store_true", help="also compare table data")
    p.add_argument("--format", choices=("table", "json"), default="table")
    p.add_argument("--output", help="write to file instead of stdout")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("er", help="generate an ER diagram")
    p.add_argument("database")
    p.add_argument("--format", choices=("mermaid", "dot"), default="mermaid")
    p.add_argument("--output", help="write to file instead of stdout")
    p.set_defaults(func=cmd_er)

    p = sub.add_parser("doctor", help="run health checks")
    p.add_argument("database")
    p.add_argument("--format", choices=("table", "json"), default="table")
    p.add_argument("--output", help="write to file instead of stdout")
    p.add_argument("--vacuum", action="store_true", help="run VACUUM after checks")
    p.add_argument("--analyze", action="store_true", help="run ANALYZE after checks")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("bench", help="benchmark a read-only query")
    p.add_argument("database")
    p.add_argument("sql", nargs="+", help="SQL statement")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--format", choices=("table", "json"), default="table")
    p.add_argument("--output", help="write to file instead of stdout")
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("shell", help="start the interactive SQL shell")
    p.add_argument("database")
    p.set_defaults(func=cmd_shell)

    p = sub.add_parser("tui", help="start the full-screen TUI (auto-fallback on Windows)")
    p.add_argument("database")
    p.set_defaults(func=cmd_tui)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    configure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args) or 0
    except DatabaseError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
