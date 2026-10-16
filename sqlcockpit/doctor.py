"""Database health doctor: integrity checks, pragmas and maintenance advice."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .db import Database
from .formatters import render_table
from .utils import human_bytes


def run_checks(db: Database) -> Dict[str, Any]:
    """Run integrity checks and collect statistics for one database."""
    integrity = [r[0] for r in db.execute("PRAGMA integrity_check").fetchall()]
    fk_violations = [tuple(r) for r in db.execute("PRAGMA foreign_key_check").fetchall()]
    quick = [r[0] for r in db.execute("PRAGMA quick_check").fetchall()]
    pragmas: Dict[str, Any] = {}
    for name in (
        "page_size",
        "page_count",
        "freelist_count",
        "journal_mode",
        "user_version",
        "application_id",
        "encoding",
        "auto_vacuum",
    ):
        pragmas[name] = db.scalar("PRAGMA %s" % name)

    tables: List[Dict[str, Any]] = []
    for table in db.tables():
        cols = db.columns(table)
        tables.append(
            {
                "table": table,
                "rows": db.row_count(table),
                "columns": len(cols),
                "indexes": len(db.index_list(table)),
                "has_pk": bool(db.primary_key(table)),
                "fks": len(db.foreign_keys(table)),
            }
        )
    views = db.views()
    triggers = db.triggers()

    suggestions: List[Dict[str, str]] = []
    if integrity != ["ok"]:
        suggestions.append(
            {
                "level": "critical",
                "message": "integrity_check reported problems: %s" % "; ".join(integrity[:5]),
            }
        )
    if fk_violations:
        suggestions.append(
            {
                "level": "critical",
                "message": "%d foreign key violation(s) detected" % len(fk_violations),
            }
        )
    if quick != ["ok"]:
        suggestions.append({"level": "warning", "message": "quick_check is not clean"})
    freelist = pragmas.get("freelist_count") or 0
    page_size = pragmas.get("page_size") or 0
    if freelist > 0:
        suggestions.append(
            {
                "level": "info",
                "message": "%d free pages (~%s) reclaimable, consider VACUUM"
                % (freelist, human_bytes(freelist * page_size)),
            }
        )
    for entry in tables:
        if not entry["has_pk"]:
            suggestions.append(
                {"level": "info", "message": "table %s has no primary key" % entry["table"]}
            )
        if entry["rows"] == 0:
            suggestions.append(
                {"level": "info", "message": "table %s is empty" % entry["table"]}
            )
    if str(pragmas.get("journal_mode", "")).lower() == "delete":
        suggestions.append(
            {"level": "info", "message": "journal_mode=delete, consider WAL for concurrency"}
        )
    if not pragmas.get("user_version"):
        suggestions.append(
            {"level": "info", "message": "user_version is 0, set it to track schema versions"}
        )

    return {
        "database": db.path,
        "size_bytes": db.size_bytes(),
        "integrity_check": integrity,
        "quick_check": quick,
        "foreign_key_violations": len(fk_violations),
        "pragmas": pragmas,
        "objects": {
            "tables": len(tables),
            "views": len(views),
            "triggers": len(triggers),
        },
        "tables": tables,
        "suggestions": suggestions,
        "healthy": not any(s["level"] == "critical" for s in suggestions),
    }


def apply_maintenance(db: Database, vacuum: bool = False, analyze: bool = False) -> List[str]:
    """Run opt-in maintenance statements and return log lines."""
    actions: List[str] = []
    if vacuum:
        db.execute("VACUUM")
        actions.append("VACUUM completed")
    if analyze:
        db.execute("ANALYZE")
        actions.append("ANALYZE completed")
    return actions


def render_report(report: Dict[str, Any], fmt: str = "table") -> str:
    """Render the doctor report as a table or JSON document."""
    if fmt == "json":
        return json.dumps(report, indent=2, ensure_ascii=False, default=str)
    lines = []
    status = "HEALTHY" if report["healthy"] else "NEEDS ATTENTION"
    lines.append("Database : %s (%s)" % (report["database"], human_bytes(report["size_bytes"])))
    lines.append("Status   : %s" % status)
    lines.append("Integrity: %s" % ", ".join(report["integrity_check"]))
    lines.append("FK check : %d violation(s)" % report["foreign_key_violations"])
    lines.append(
        "Objects  : %d tables, %d views, %d triggers"
        % (
            report["objects"]["tables"],
            report["objects"]["views"],
            report["objects"]["triggers"],
        )
    )
    pragmas = report["pragmas"]
    lines.append(
        "Storage  : page_size=%s pages=%s freelist=%s journal=%s user_version=%s"
        % (
            pragmas.get("page_size"),
            pragmas.get("page_count"),
            pragmas.get("freelist_count"),
            pragmas.get("journal_mode"),
            pragmas.get("user_version"),
        )
    )
    lines.append("")
    lines.append(
        render_table(
            ["table", "rows", "columns", "indexes", "fks", "has_pk"],
            [
                [
                    t["table"],
                    t["rows"],
                    t["columns"],
                    t["indexes"],
                    t["fks"],
                    "yes" if t["has_pk"] else "NO",
                ]
                for t in report["tables"]
            ],
        )
    )
    if report["suggestions"]:
        lines.append("")
        lines.append("Suggestions:")
        for s in report["suggestions"]:
            lines.append("  [%s] %s" % (s["level"], s["message"]))
    else:
        lines.append("")
        lines.append("No suggestions - database looks great.")
    return "\n".join(lines)
