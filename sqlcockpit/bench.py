"""Query benchmarking utilities."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .db import Database, DatabaseError
from .formatters import render_table
from .utils import Timer

_WRITE_PREFIXES = (
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "vacuum",
    "analyze",
    "begin",
    "commit",
    "replace",
    "attach",
    "detach",
    "pragma",
    "reindex",
)


def is_read_only_sql(sql: str) -> bool:
    stripped = sql.strip().lstrip("(").lstrip().lower()
    first = stripped.split(None, 1)[0] if stripped.split() else ""
    if first in ("with", "select", "explain"):
        return True
    return first not in _WRITE_PREFIXES and not any(
        stripped.startswith(p) for p in _WRITE_PREFIXES
    )


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = pct / 100.0 * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


def benchmark(db: Database, sql: str, runs: int = 5) -> Dict[str, Any]:
    """Time ``sql`` over ``runs`` executions (read-only queries only)."""
    if not is_read_only_sql(sql):
        raise DatabaseError("benchmark supports read-only queries (SELECT/EXPLAIN/WITH)")
    runs = max(1, int(runs))
    times: List[float] = []
    rows = 0
    for _ in range(runs):
        with Timer() as timer:
            cur = db.execute(sql)
            data = cur.fetchall()
            rows = len(data)
        times.append(timer.elapsed)
    ordered = sorted(times)
    avg = sum(times) / len(times)
    return {
        "sql": sql.strip(),
        "runs": runs,
        "rows": rows,
        "min_ms": round(ordered[0] * 1000, 3),
        "max_ms": round(ordered[-1] * 1000, 3),
        "avg_ms": round(avg * 1000, 3),
        "p95_ms": round(_percentile(ordered, 95) * 1000, 3),
        "total_ms": round(sum(times) * 1000, 3),
        "rows_per_sec": round(rows / avg, 1) if avg > 0 else 0.0,
    }


def render_bench(result: Dict[str, Any], fmt: str = "table") -> str:
    """Render a benchmark result as a table or JSON document."""
    if fmt == "json":
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    rows = [
        ["runs", result["runs"]],
        ["rows", result["rows"]],
        ["min", "%.3f ms" % result["min_ms"]],
        ["max", "%.3f ms" % result["max_ms"]],
        ["avg", "%.3f ms" % result["avg_ms"]],
        ["p95", "%.3f ms" % result["p95_ms"]],
        ["total", "%.3f ms" % result["total_ms"]],
        ["throughput", "%.1f rows/s" % result["rows_per_sec"]],
    ]
    return render_table(["metric", "value"], rows)
