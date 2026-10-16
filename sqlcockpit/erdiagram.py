"""ER diagram generation (Mermaid erDiagram + Graphviz DOT)."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .db import Database

_MERMAID_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _mermaid_name(name: str) -> str:
    safe = _MERMAID_SAFE.sub("_", name)
    if not safe or safe[0].isdigit():
        safe = "t_" + safe
    return safe


def _dot_name(name: str) -> str:
    return '"' + name.replace('"', '\\"') + '"'


def build_model(db: Database) -> Dict[str, Any]:
    """Build an entity-relationship model from the live schema."""
    model: Dict[str, Any] = {"entities": {}, "relations": []}
    for table in db.tables():
        cols = db.columns(table)
        pk = {c["name"] for c in cols if c["pk"]}
        fks = db.foreign_keys(table)
        fk_cols = {fk["from"] for fk in fks}
        model["entities"][table] = {
            "columns": [
                {
                    "name": c["name"],
                    "type": c["type"] or "TEXT",
                    "pk": c["name"] in pk,
                    "fk": c["name"] in fk_cols,
                    "notnull": bool(c["notnull"]),
                }
                for c in cols
            ],
            "foreign_keys": fks,
        }
        for fk in fks:
            model["relations"].append(
                {
                    "from_table": table,
                    "from_column": fk["from"],
                    "to_table": fk["table"],
                    "to_column": fk["to"],
                }
            )
    return model


def to_mermaid(model: Dict[str, Any]) -> str:
    """Render the model as a Mermaid ``erDiagram``."""
    lines = ["erDiagram"]
    for table, entity in sorted(model["entities"].items()):
        lines.append("    %s {" % _mermaid_name(table))
        for col in entity["columns"]:
            keys = ""
            if col["pk"]:
                keys = " PK"
            elif col["fk"]:
                keys = " FK"
            comment = ' "%s"' % col["name"] if _MERMAID_SAFE.search(col["name"]) else ""
            lines.append("        %s %s%s%s" % (col["type"], _mermaid_name(col["name"]), keys, comment))
        lines.append("    }")
    for rel in model["relations"]:
        lines.append(
            '    %s ||--o{ %s : "%s"'
            % (
                _mermaid_name(rel["from_table"]),
                _mermaid_name(rel["to_table"]),
                rel["from_column"],
            )
        )
    return "\n".join(lines)


def to_dot(model: Dict[str, Any]) -> str:
    """Render the model as a Graphviz DOT digraph."""
    lines = [
        "digraph ER {",
        "    rankdir=LR;",
        '    graph [fontname="Helvetica"];',
        '    node [shape=record, fontname="Helvetica", fontsize=10];',
        '    edge [fontname="Helvetica", fontsize=9];',
    ]
    for table, entity in sorted(model["entities"].items()):
        attrs = []
        for col in entity["columns"]:
            key = ""
            if col["pk"]:
                key = " 🔑"
            elif col["fk"]:
                key = " 🔗"
            attrs.append("%s : %s%s" % (col["name"], col["type"], key))
        label = "{%s|%s\\l}" % (table, "\\l".join(a + "\\l" for a in attrs))
        lines.append("    %s [label=\"%s\"];" % (_dot_name(table), label))
    for rel in model["relations"]:
        lines.append(
            "    %s -> %s [label=\"%s\"];"
            % (_dot_name(rel["from_table"]), _dot_name(rel["to_table"]), rel["from_column"])
        )
    lines.append("}")
    return "\n".join(lines)


def render_model(model: Dict[str, Any], fmt: str = "mermaid") -> str:
    key = (fmt or "mermaid").lower()
    if key == "mermaid":
        return to_mermaid(model)
    if key in ("dot", "graphviz"):
        return to_dot(model)
    raise ValueError("unknown ER format: %s (mermaid|dot)" % fmt)
