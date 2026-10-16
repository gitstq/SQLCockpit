"""Shared helpers used across SQLCockpit."""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional


def now_iso() -> str:
    """Return the current local time as an ISO-8601 string (second precision)."""
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def human_bytes(num: Optional[float]) -> str:
    """Format a byte count as a human readable string."""
    if num is None:
        return "-"
    n = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0 or unit == "TB":
            if unit == "B":
                return "%d %s" % (int(n), unit)
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


def truncate(text: Any, width: int) -> str:
    """Truncate ``text`` to ``width`` display cells, appending an ellipsis."""
    s = "" if text is None else str(text)
    for ch in ("\n", "\r", "\t"):
        s = s.replace(ch, " ")
    if width <= 0:
        return ""
    if len(s) <= width:
        return s
    if width == 1:
        return "…"
    return s[: width - 1] + "…"


def quote_ident(name: str) -> str:
    """Quote a SQLite identifier safely."""
    return '"' + str(name).replace('"', '""') + '"'


def quote_value(value: Any) -> str:
    """Render a Python value as a SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


class Timer:
    """Context manager measuring elapsed wall time in seconds."""

    def __enter__(self) -> "Timer":
        self._start = _dt.datetime.now()
        self.elapsed = 0.0
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.elapsed = (_dt.datetime.now() - self._start).total_seconds()


def configure_streams() -> None:
    """Make stdout/stderr UTF-8 safe so Unicode box drawing renders everywhere.

    On Windows the default console codec (cp1252) cannot encode the Unicode
    box-drawing characters used by the table renderer and would raise a
    ``charmap`` ``UnicodeEncodeError``. Reconfiguring to UTF-8 with a
    ``replace`` fallback keeps the CLI crash-free on legacy terminals.
    """
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
