"""Schema and data diffing between two SQLite databases."""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .db import Database
from .utils import quote_ident


def _column_signature(col: Dict[str, Any]) -> Tuple:
    return (
        col.get("type", ""),
        bool(col.get("notnull")),
        col.get("default"),
        int(col.get("pk", 0)),
    )


def diff_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compare two schema snapshots and return a list of change records."""
    changes: List[Dict[str, Any]] = []

    tables_before = set(before.get("tables", {}))
    tables_after = set(after.get("tables", {}))
    for name in sorted(tables_after - tables_before):
        changes.append({"kind": "table_added", "object": name})
    for name in sorted(tables_before - tables_after):
        changes.append({"kind": "table_removed", "object": name})

    for name in sorted(tables_before & tables_after):
        cols_before = {c["name"]: c for c in before["tables"][name].get("columns", [])}
        cols_after = {c["name"]: c for c in after["tables"][name].get("columns", [])}
        for col in sorted(set(cols_after) - set(cols_before)):
            changes.append({"kind": "column_added", "object": name, "column": col})
        for col in sorted(set(cols_before) - set(cols_after)):
            changes.append({"kind": "column_removed", "object": name, "column": col})
        for col in sorted(set(cols_before) & set(cols_after)):
            if _column_signature(cols_before[col]) != _column_signature(cols_after[col]):
                changes.append(
                    {
                        "kind": "column_changed",
                        "object": name,
                        "column": col,
                        "from": _column_signature(cols_before[col]),
                        "to": _column_signature(cols_after[col]),
                    }
                )
        idx_before = {i["name"] for i in before["tables"][name].get("indexes", [])}
        idx_after = {i["name"] for i in after["tables"][name].get("indexes", [])}
        for idx in sorted(idx_after - idx_before):
            changes.append({"kind": "index_added", "object": name, "index": idx})
        for idx in sorted(idx_before - idx_after):
            changes.append({"kind": "index_removed", "object": name, "index": idx})

    for section, kind_singular in (
        ("views", "view"),
        ("triggers", "trigger"),
        ("indexes", "index"),
    ):
        objs_before = set(before.get(section, {}))
        objs_after = set(after.get(section, {}))
        for name in sorted(objs_after - objs_before):
            changes.append({"kind": "%s_added" % kind_singular, "object": name})
        for name in sorted(objs_before - objs_after):
            changes.append({"kind": "%s_removed" % kind_singular, "object": name})
        for name in sorted(objs_before & objs_after):
            sql_before = before[section][name].get("sql")
            sql_after = after[section][name].get("sql")
            if (sql_before or "").strip() != (sql_after or "").strip():
                changes.append({"kind": "%s_changed" % kind_singular, "object": name})
    return changes


def _row_hash(row: Tuple[Any, ...]) -> str:
    return hashlib.md5(repr(row).encode("utf-8")).hexdigest()


def _fetch_rows(db: Database, table: str, limit: int) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    return db.query("SELECT * FROM %s" % quote_ident(table), limit=limit)


def diff_table_data(
    left: Database,
    right: Database,
    table: str,
    key_columns: Optional[List[str]] = None,
    sample: int = 5,
    max_rows: int = 50000,
) -> Dict[str, Any]:
    """Diff the rows of one table between two databases."""
    left_cols, left_rows = _fetch_rows(left, table, max_rows)
    right_cols, right_rows = _fetch_rows(right, table, max_rows)
    keys = key_columns or left.primary_key(table)

    result: Dict[str, Any] = {
        "table": table,
        "strategy": "primary_key" if keys else "row_hash",
        "left_rows": len(left_rows),
        "right_rows": len(right_rows),
        "only_in_left": 0,
        "only_in_right": 0,
        "changed": 0,
        "samples": [],
    }
    if keys:
        key_idx = [left_cols.index(k) for k in keys]
        left_map = {tuple(r[i] for i in key_idx): r for r in left_rows}
        right_map = {tuple(r[i] for i in key_idx): r for r in right_rows}
        for key, row in left_map.items():
            if key not in right_map:
                result["only_in_left"] += 1
                if len(result["samples"]) < sample:
                    result["samples"].append({"side": "left", "key": list(key), "row": list(row)})
        for key, row in right_map.items():
            if key not in left_map:
                result["only_in_right"] += 1
                if len(result["samples"]) < sample:
                    result["samples"].append({"side": "right", "key": list(key), "row": list(row)})
            elif _row_hash(row) != _row_hash(left_map[key]):
                result["changed"] += 1
                if len(result["samples"]) < sample:
                    result["samples"].append({"side": "changed", "key": list(key), "row": list(row)})
    else:
        left_hashes = Counter(_row_hash(r) for r in left_rows)
        right_hashes = Counter(_row_hash(r) for r in right_rows)
        result["only_in_left"] = sum((left_hashes - right_hashes).values())
        result["only_in_right"] = sum((right_hashes - left_hashes).values())
    return result


def diff_databases(
    left: Database,
    right: Database,
    with_data: bool = False,
    sample: int = 5,
) -> Dict[str, Any]:
    """Full diff: schema changes plus (optionally) per-table data changes."""
    before = left.schema_snapshot()
    after = right.schema_snapshot()
    schema_changes = diff_snapshots(before, after)
    result: Dict[str, Any] = {
        "schema_changes": schema_changes,
        "schema_changed": bool(schema_changes),
        "data_changes": {},
        "identical": not schema_changes and not with_data,
    }
    if with_data:
        shared = sorted(set(before.get("tables", {})) & set(after.get("tables", {})))
        for table in shared:
            entry = diff_table_data(left, right, table, sample=sample)
            if entry["only_in_left"] or entry["only_in_right"] or entry["changed"]:
                result["data_changes"][table] = entry
        result["data_changed"] = bool(result["data_changes"])
        result["identical"] = not schema_changes and not result["data_changes"]
    return result


def render_diff(result: Dict[str, Any], fmt: str = "table") -> str:
    """Render a diff result as a table or JSON document."""
    import json

    from .formatters import render_table

    if fmt == "json":
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    lines = []
    lines.append("== Schema changes ==")
    if result["schema_changes"]:
        rows = [[c["kind"], c.get("object", ""), c.get("column") or c.get("index") or ""] for c in result["schema_changes"]]
        lines.append(render_table(["kind", "object", "detail"], rows))
    else:
        lines.append("(no schema differences)")
    if "data_changes" in result:
        lines.append("")
        lines.append("== Data changes ==")
        if result["data_changes"]:
            rows = [
                [
                    t,
                    d["left_rows"],
                    d["right_rows"],
                    d["only_in_left"],
                    d["only_in_right"],
                    d["changed"],
                ]
                for t, d in result["data_changes"].items()
            ]
            lines.append(
                render_table(
                    ["table", "left", "right", "only_left", "only_right", "changed"], rows
                )
            )
        else:
            lines.append("(no data differences)")
    lines.append("")
    lines.append("identical: %s" % ("yes" if result["identical"] else "no"))
    return "\n".join(lines)
