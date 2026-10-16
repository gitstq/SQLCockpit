"""Result set formatters: table, vertical, csv, json, jsonl and markdown."""
from __future__ import annotations

import csv
import io
import json
from typing import Any, List, Sequence, Tuple

from .utils import truncate

FORMATS = ("table", "vertical", "csv", "json", "jsonl", "markdown")


def _cells(rows: Sequence[Sequence[Any]]) -> List[List[str]]:
    return [["" if v is None else str(v) for v in row] for row in rows]


def _numeric_column(values: Sequence[str]) -> bool:
    seen = False
    for v in values:
        if v == "":
            continue
        try:
            float(v)
        except ValueError:
            return False
        seen = True
    return seen


def render_table(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    max_col_width: int = 36,
) -> str:
    """Render a box-drawing table with automatic column sizing."""
    data = _cells(rows)
    widths = [len(str(c)) for c in columns]
    for row in data:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))
    widths = [min(w, max(4, max_col_width)) for w in widths]
    data = [[truncate(cell, widths[i]) for i, cell in enumerate(row)] for row in data]
    numeric = [_numeric_column([row[i] for row in data]) for i in range(len(columns))]

    def line(left: str, mid: str, right: str, fill: str = "─") -> str:
        parts = [fill * (w + 2) for w in widths]
        return left + mid.join(parts) + right

    def fmt_row(values: Sequence[str]) -> str:
        cells = []
        for i, value in enumerate(values):
            cells.append(" " + value.rjust(widths[i]) if numeric[i] else " " + value.ljust(widths[i]) + " ")
        return "│" + "│".join(cells) + "│"

    out = [line("┌", "┬", "┐"), fmt_row(columns), line("├", "┼", "┤")]
    for row in data:
        out.append(fmt_row(row))
    out.append(line("└", "┴", "┘"))
    return "\n".join(out)


def render_vertical(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render one record per block, similar to MySQL's \\G output."""
    width = max([len(str(c)) for c in columns] + [1])
    blocks = []
    for idx, row in enumerate(rows, start=1):
        header = "%d. row" % idx
        blocks.append("*" * 22 + " " + header + " " + "*" * 22)
        for col, value in zip(columns, row):
            blocks.append("%s : %s" % (str(col).rjust(width), "" if value is None else value))
        blocks.append("")
    return "\n".join(blocks).rstrip()


def render_csv(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().rstrip("\n")


def _row_dicts(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[dict]:
    return [dict(zip(columns, row)) for row in rows]


def render_json(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    return json.dumps(_row_dicts(columns, rows), indent=2, ensure_ascii=False, default=str)


def render_jsonl(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        json.dumps(d, ensure_ascii=False, default=str, separators=(",", ":"))
        for d in _row_dicts(columns, rows)
    ]
    return "\n".join(lines)


def render_markdown(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    header = "| " + " | ".join(str(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        cells = [("" if v is None else str(v)).replace("|", "\\|").replace("\n", " ") for v in row]
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + body)


_RENDERERS = {
    "table": render_table,
    "vertical": render_vertical,
    "csv": render_csv,
    "json": render_json,
    "jsonl": render_jsonl,
    "markdown": render_markdown,
}


def to_format(fmt: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Dispatch to the renderer for ``fmt``."""
    key = (fmt or "table").lower()
    if key not in _RENDERERS:
        raise ValueError("unknown format: %s (choose from %s)" % (fmt, ", ".join(FORMATS)))
    return _RENDERERS[key](columns, rows)
