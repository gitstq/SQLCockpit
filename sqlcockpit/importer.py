"""CSV / JSON import with automatic type inference."""
from __future__ import annotations

import csv
import json
import re
from typing import Any, Dict, List, Optional

from .db import Database, DatabaseError
from .utils import quote_ident

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")

IF_EXISTS_CHOICES = ("fail", "replace", "append")


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text != "" else None


def infer_column_type(values: List[Optional[str]]) -> str:
    """Infer a SQLite column type from sampled string values."""
    seen = [v for v in values if v is not None]
    if not seen:
        return "TEXT"
    if all(_INT_RE.match(v) for v in seen):
        return "INTEGER"
    if all(_FLOAT_RE.match(v) for v in seen):
        return "REAL"
    return "TEXT"


def _coerce(value: Optional[str], decl_type: str) -> Any:
    if value is None:
        return None
    if decl_type == "INTEGER":
        try:
            return int(value)
        except ValueError:
            return value
    if decl_type == "REAL":
        try:
            return float(value)
        except ValueError:
            return value
    return value


def read_csv(path: str, delimiter: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
    """Read a CSV file into a list of row dicts."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        if delimiter is None:
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ","
        reader = csv.DictReader(fh, delimiter=delimiter)
        return [{k: _clean(v) for k, v in row.items() if k is not None} for row in reader]


def read_json(path: str) -> List[Dict[str, Optional[str]]]:
    """Read a JSON file (array of objects, or object-per-line) into row dicts."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        data = rows
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise DatabaseError("JSON import expects an array of objects")
    out = []
    for item in data:
        if not isinstance(item, dict):
            raise DatabaseError("JSON import expects an array of objects")
        out.append({k: _clean(v) for k, v in item.items()})
    return out


def _create_table(db: Database, table: str, headers: List[str], rows: List[Dict[str, Optional[str]]]) -> None:
    types = {h: infer_column_type([r.get(h) for r in rows]) for h in headers}
    cols = ", ".join("%s %s" % (quote_ident(h), types[h]) for h in headers)
    db.execute("CREATE TABLE %s (%s)" % (quote_ident(table), cols))


def _insert(db: Database, table: str, rows: List[Dict[str, Optional[str]]]) -> int:
    if not rows:
        return 0
    headers: List[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    existing = {c["name"] for c in db.columns(table)}
    headers = [h for h in headers if h in existing] if existing else headers
    if not headers:
        raise DatabaseError("no matching columns to insert into %s" % table)
    placeholders = ", ".join("?" for _ in headers)
    col_sql = ", ".join(quote_ident(h) for h in headers)
    payload = [tuple(row.get(h) for h in headers) for row in rows]
    db.conn.executemany(
        "INSERT INTO %s (%s) VALUES (%s)" % (quote_ident(table), col_sql, placeholders), payload
    )
    db.conn.commit()
    return len(payload)


def import_rows(
    db: Database,
    table: str,
    rows: List[Dict[str, Optional[str]]],
    if_exists: str = "fail",
    create: bool = True,
) -> Dict[str, Any]:
    """Import row dicts into ``table``, returning a report dict."""
    if if_exists not in IF_EXISTS_CHOICES:
        raise DatabaseError("--if-exists must be one of: %s" % ", ".join(IF_EXISTS_CHOICES))
    headers: List[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    if not headers:
        raise DatabaseError("no columns found in input data")

    exists = table in db.tables()
    created = False
    if exists:
        if if_exists == "fail":
            raise DatabaseError(
                "table %s already exists (use --if-exists replace|append)" % table
            )
        if if_exists == "replace":
            db.execute("DROP TABLE %s" % quote_ident(table))
            _create_table(db, table, headers, rows)
            created = True
    else:
        if not create:
            raise DatabaseError("table %s does not exist (drop --no-create to auto-create)" % table)
        _create_table(db, table, headers, rows)
        created = True

    inserted = _insert(db, table, rows)
    return {
        "table": table,
        "created": created,
        "inserted": inserted,
        "columns": headers,
    }


def detect_format(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".json") or lower.endswith(".jsonl"):
        return "json"
    return "csv"


def import_file(
    db: Database,
    table: str,
    path: str,
    fmt: Optional[str] = None,
    if_exists: str = "fail",
    create: bool = True,
    delimiter: Optional[str] = None,
) -> Dict[str, Any]:
    """Import a CSV/JSON file into ``table``."""
    fmt = (fmt or detect_format(path)).lower()
    if fmt == "csv":
        rows = read_csv(path, delimiter=delimiter)
    elif fmt == "json":
        rows = read_json(path)
    else:
        raise DatabaseError("unknown import format: %s (csv|json)" % fmt)
    report = import_rows(db, table, rows, if_exists=if_exists, create=create)
    report["format"] = fmt
    report["source"] = path
    return report
