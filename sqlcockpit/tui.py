"""Full-screen TUI (curses) with a dependency-free fallback menu.

On Unix/macOS the stock ``curses`` module provides the full cockpit UI.
On Windows (where ``curses`` is not part of the standard library) SQLCockpit
automatically degrades to a numbered menu so the zero-dependency promise
holds on every platform.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from .db import Database, DatabaseError
from .doctor import render_report, run_checks
from .erdiagram import build_model, render_model
from .formatters import render_table, to_format
from .importer import import_file
from .utils import configure_streams, quote_ident

TABLES, SQL, RESULTS = 0, 1, 2


def run_tui(db_path: str) -> int:
    """Launch the TUI, falling back to a menu when curses is unavailable."""
    configure_streams()
    try:
        import curses  # noqa: F401
    except ImportError:
        return _run_fallback(db_path)
    import curses

    return curses.wrapper(_curses_main, db_path)


# ---------------------------------------------------------------------------
# curses implementation
# ---------------------------------------------------------------------------
def _curses_main(stdscr: Any, db_path: str) -> int:
    import curses

    curses.curs_set(1)
    curses.use_default_colors()
    try:
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        title_attr = curses.color_pair(1) | curses.A_BOLD
        focus_attr = curses.A_REVERSE
    except curses.error:
        title_attr = curses.A_BOLD
        focus_attr = curses.A_REVERSE

    with Database(db_path) as db:
        tables = db.tables()
        state = {
            "focus": TABLES,
            "selected": 0,
            "scroll": 0,
            "sql": "",
            "results": "Run SQL with F2. TAB switches panes.",
            "status": "connected: %s" % db_path,
        }

        def _safe_add(win: Any, y: int, x: int, text: str, attr: int = 0) -> None:
            try:
                win.addnstr(y, x, text, max(0, win.getmaxyx()[1] - x - 1), attr)
            except curses.error:
                pass

        def _draw() -> None:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            left_w = max(20, min(36, width // 3))
            mid_x = left_w + 1
            right_w = width - mid_x - 1
            split_y = max(4, height // 2)

            _safe_add(stdscr, 0, 0, " SQLCockpit ".center(width, "=")[: width - 1], title_attr)
            _safe_add(stdscr, 1, 0, " TAB: switch pane | F2: run SQL | F5: schema | q: quit ", title_attr)

            # left pane: tables
            _safe_add(stdscr, 2, 0, "[tables]", title_attr if state["focus"] == TABLES else 0)
            visible = max(1, height - 5)
            if state["selected"] < state["scroll"]:
                state["scroll"] = state["selected"]
            elif state["selected"] >= state["scroll"] + visible:
                state["scroll"] = state["selected"] - visible + 1
            for i in range(visible):
                idx = state["scroll"] + i
                if idx >= len(tables):
                    break
                name = tables[idx]
                attr = focus_attr if (state["focus"] == TABLES and idx == state["selected"]) else 0
                _safe_add(stdscr, 3 + i, 0, " %-*s" % (left_w - 2, name[: left_w - 3]), attr)

            # right top: SQL editor
            _safe_add(stdscr, 2, mid_x, "[sql]", title_attr if state["focus"] == SQL else 0)
            sql_lines = state["sql"].split("\n")
            for i in range(max(1, split_y - 4)):
                if i < len(sql_lines):
                    _safe_add(
                        stdscr, 3 + i, mid_x, " %s" % sql_lines[i][: right_w - 2],
                        focus_attr if state["focus"] == SQL else 0,
                    )

            # right bottom: results
            _safe_add(stdscr, split_y - 1, mid_x, "[results]", title_attr if state["focus"] == RESULTS else 0)
            res_lines = state["results"].split("\n")
            for i in range(max(1, height - split_y - 1)):
                if i < len(res_lines):
                    _safe_add(stdscr, split_y + i, mid_x, " %s" % res_lines[i][: right_w - 2])

            _safe_add(stdscr, height - 1, 0, " %s" % state["status"][: width - 2])
            stdscr.refresh()

        def _show_schema() -> None:
            if not tables:
                return
            name = tables[state["selected"]]
            try:
                cols = db.columns(name)
                state["results"] = render_table(
                    ["column", "type", "key", "default"],
                    [
                        [
                            c["name"],
                            c["type"] or "-",
                            "PK" if c["pk"] else "",
                            "" if c["default"] is None else str(c["default"]),
                        ]
                        for c in cols
                    ],
                )
                state["status"] = "schema of %s (F5)" % name
            except DatabaseError as exc:
                state["results"] = "error: %s" % exc

        def _run_sql() -> None:
            sql = state["sql"].strip()
            if not sql:
                state["results"] = "(empty SQL)"
                return
            try:
                columns, rows = db.query(sql, limit=500)
            except DatabaseError as exc:
                state["results"] = "error: %s" % exc
                return
            state["results"] = to_format("table", columns, rows)

        while True:
            _draw()
            try:
                key = stdscr.get_wch()
            except KeyboardInterrupt:
                break
            if isinstance(key, str):
                if key == "q":
                    break
                if key == "\t":
                    state["focus"] = (state["focus"] + 1) % 3
                elif key == "\n":
                    if state["focus"] == SQL:
                        state["sql"] += "\n"
                    elif state["focus"] == TABLES:
                        _show_schema()
                elif key == "\x7f" or key == "\x08":
                    if state["focus"] == SQL and state["sql"]:
                        state["sql"] = state["sql"][:-1]
                elif state["focus"] == SQL and key.isprintable():
                    state["sql"] += key
            else:
                if key == curses.KEY_UP and state["focus"] == TABLES:
                    state["selected"] = max(0, state["selected"] - 1)
                elif key == curses.KEY_DOWN and state["focus"] == TABLES:
                    state["selected"] = min(len(tables) - 1, state["selected"] + 1)
                elif key == curses.KEY_F2:
                    _run_sql()
                elif key == curses.KEY_F5:
                    _show_schema()
    return 0


# ---------------------------------------------------------------------------
# fallback menu (no curses available, e.g. Windows without windows-curses)
# ---------------------------------------------------------------------------
def _run_fallback(db_path: str) -> int:
    print("SQLCockpit TUI - fallback menu mode (curses unavailable)")
    with Database(db_path) as db:
        while True:
            print("")
            print("1) List tables & row counts")
            print("2) Show table schema")
            print("3) Run SQL query")
            print("4) Export table to CSV")
            print("5) Import CSV/JSON into table")
            print("6) ER diagram (mermaid)")
            print("7) Database doctor")
            print("8) Quit")
            try:
                choice = input("select> ").strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                print("")
                break
            if choice == "1":
                rows = [[t, db.row_count(t)] for t in db.tables()]
                print(render_table(["table", "rows"], rows))
            elif choice == "2":
                name = input("table> ").strip()
                if name in db.tables():
                    cols = db.columns(name)
                    print(
                        render_table(
                            ["column", "type", "key"],
                            [
                                [c["name"], c["type"] or "-", "PK" if c["pk"] else ""]
                                for c in cols
                            ],
                        )
                    )
                else:
                    print("no such table: %s" % name)
            elif choice == "3":
                sql = input("sql> ").strip()
                try:
                    columns, rows = db.query(sql, limit=200)
                    print(to_format("table", columns, rows))
                except DatabaseError as exc:
                    print("error: %s" % exc)
            elif choice == "4":
                table = input("table> ").strip()
                path = input("file> ").strip()
                try:
                    columns, rows = db.query("SELECT * FROM %s" % quote_ident(table))
                except DatabaseError as exc:
                    print("error: %s" % exc)
                    continue
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(to_format("csv", columns, rows) + "\n")
                print("exported %d rows to %s" % (len(rows), path))
            elif choice == "5":
                table = input("table> ").strip()
                path = input("file> ").strip()
                try:
                    report = import_file(db, table, path, if_exists="append")
                except (DatabaseError, OSError) as exc:
                    print("error: %s" % exc)
                    continue
                print("imported %d rows" % report["inserted"])
            elif choice == "6":
                print(render_model(build_model(db), "mermaid"))
            elif choice == "7":
                print(render_report(run_checks(db)))
            elif choice in ("8", "q", "quit", "exit"):
                break
            else:
                print("unknown option: %s" % choice)
    return 0
