"""Build the Unity Catalog governance statements from docs/data_dictionary.csv.

The data dictionary is the single source of truth for table tags, column
descriptions and column tags. Table descriptions live in the pipeline
definition itself (COMMENT clause) because Lakeflow pipelines own them.

Pure Python, no Spark: the logic is unit tested locally.
"""
from __future__ import annotations

import csv


def read_dictionary(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_tags(raw: str) -> list[tuple[str, str]]:
    """'pii=true;sensitivity=personal' -> [('pii', 'true'), ('sensitivity', 'personal')]"""
    pairs = []
    for part in (raw or "").split(";"):
        part = part.strip()
        if part:
            key, _, value = part.partition("=")
            pairs.append((key.strip(), value.strip()))
    return pairs


def _tag_clause(tags: list[tuple[str, str]]) -> str:
    return ", ".join(f"'{k}' = '{v}'" for k, v in tags)


def build_statements(rows: list[dict], catalog: str) -> list[dict]:
    """Return statements as dicts: {sql, fallback_sql, kind, target}.

    Silver and gold objects are materialized views, so ALTER MATERIALIZED VIEW
    is tried first. ``fallback_sql`` is the ALTER TABLE equivalent.
    """
    out = []
    for row in rows:
        table = f"{catalog}.{row['table_name']}"
        column = row["column_name"].strip()
        tags = parse_tags(row["tags"])
        if not column:
            if tags:
                clause = _tag_clause(tags)
                out.append({
                    "kind": "table_tags", "target": table,
                    "sql": f"ALTER MATERIALIZED VIEW {table} SET TAGS ({clause})",
                    "fallback_sql": f"ALTER TABLE {table} SET TAGS ({clause})",
                })
            continue
        description = row["description"].strip()
        out.append({
            "kind": "column_comment", "target": f"{table}.{column}",
            "sql": f"ALTER MATERIALIZED VIEW {table} ALTER COLUMN {column} COMMENT '{description}'",
            "fallback_sql": f"ALTER TABLE {table} ALTER COLUMN {column} COMMENT '{description}'",
        })
        if tags:
            clause = _tag_clause(tags)
            out.append({
                "kind": "column_tags", "target": f"{table}.{column}",
                "sql": f"ALTER MATERIALIZED VIEW {table} ALTER COLUMN {column} SET TAGS ({clause})",
                "fallback_sql": f"ALTER TABLE {table} ALTER COLUMN {column} SET TAGS ({clause})",
            })
    return out
