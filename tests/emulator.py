"""Local emulation of the Databricks pipeline with DuckDB and sqlglot.

The emulator reads the SAME SQL files that Databricks runs (src/pipelines/*.sql),
applies the declared expectations (DROP ROW removes rows, the rest are counted),
transpiles the Databricks SQL to DuckDB and executes it. It exists so the
transformation logic and the acceptance tests can be verified in CI without a
Databricks workspace. It is a test aid, not a Databricks replacement: engine
specific behaviour (Auto Loader, Unity Catalog, materialized view refresh) is
only exercised on Databricks.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field

import duckdb
import sqlglot
from sqlglot import exp

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_DIR = os.path.join(REPO_ROOT, "src", "pipelines")
TESTS_SQL_DIR = os.path.join(REPO_ROOT, "sql", "tests")


# --------------------------------------------------------------------------
# Parsing of the pipeline files
# --------------------------------------------------------------------------
@dataclass
class Expectation:
    name: str
    expr: str
    action: str          # "DROP" or "WARN" or "FAIL"


@dataclass
class Dataset:
    kind: str            # "MATERIALIZED VIEW" or "STREAMING TABLE"
    name: str
    expectations: list = field(default_factory=list)
    comment: str | None = None
    query: str = ""


def strip_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


def split_statements(sql: str) -> list[str]:
    out, buf, in_str = [], [], False
    for ch in sql:
        if ch == "'":
            in_str = not in_str
        if ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _balanced(text: str, start: int) -> int:
    """Index just after the parenthesis block that opens at text[start] (string aware)."""
    depth, in_str = 0, False
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "'":
            in_str = not in_str
        if in_str:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("unbalanced parentheses")


def _split_top_level(text: str) -> list[str]:
    parts, depth, in_str, cur = [], 0, False, []
    for ch in text:
        if ch == "'":
            in_str = not in_str
        if not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
                continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def parse_dataset(stmt: str) -> Dataset:
    m = re.match(r"\s*CREATE OR REFRESH (MATERIALIZED VIEW|STREAMING TABLE)\s+([\w.]+)\s*", stmt, re.S)
    if not m:
        raise ValueError(f"unsupported statement: {stmt[:80]}")
    ds = Dataset(kind=m.group(1), name=m.group(2))
    rest = stmt[m.end():]
    if rest.startswith("("):
        end = _balanced(rest, 0)
        for part in _split_top_level(rest[1:end - 1]):
            cm = re.match(r"CONSTRAINT\s+(\w+)\s+EXPECT\s*", part, re.S)
            if not cm:
                raise ValueError(f"cannot parse constraint: {part[:80]}")
            e_start = cm.end()
            e_end = _balanced(part, e_start)
            tail = part[e_end:].upper()
            action = "WARN"
            if "DROP ROW" in tail:
                action = "DROP"
            elif "FAIL UPDATE" in tail:
                action = "FAIL"
            ds.expectations.append(Expectation(cm.group(1), part[e_start + 1:e_end - 1].strip(), action))
        rest = rest[end:].lstrip()
    cm = re.match(r"COMMENT\s+'((?:[^']|'')*)'\s*", rest, re.S)
    if cm:
        ds.comment = cm.group(1)
        rest = rest[cm.end():]
    am = re.match(r"AS\s+", rest, re.S)
    if not am:
        raise ValueError(f"missing AS in {ds.name}")
    ds.query = rest[am.end():].strip()
    return ds


def parse_pipeline_file(path: str) -> list[Dataset]:
    with open(path, encoding="utf-8") as fh:
        text = strip_comments(fh.read())
    return [parse_dataset(s) for s in split_statements(text)]


def bronze_sources(path: str) -> dict:
    """For each bronze table: the landing sub folder and the declared columns."""
    with open(path, encoding="utf-8") as fh:
        text = strip_comments(fh.read())
    out = {}
    for stmt in split_statements(text):
        ds = parse_dataset_header_only(stmt)
        folder = re.search(r"\$\{landing_path\}/([\w/]+)/'", stmt).group(1)
        schema = re.search(r"schema => '([^']+)'", stmt).group(1)
        cols = [c.strip().split()[0] for c in schema.split(",")]
        out[ds] = {"folder": folder, "columns": cols}
    return out


def parse_dataset_header_only(stmt: str) -> str:
    return re.match(r"\s*CREATE OR REFRESH STREAMING TABLE\s+([\w.]+)", stmt).group(1)


# --------------------------------------------------------------------------
# Databricks SQL to DuckDB
# --------------------------------------------------------------------------
_JAVA_TO_STRFTIME = [("yyyy", "%Y"), ("MM", "%m"), ("dd", "%d"), ("HH", "%H"), ("mm", "%M")]


def _java_format(fmt: str) -> str:
    for java, c in _JAVA_TO_STRFTIME:
        fmt = fmt.replace(java, c)
    return fmt


def _rewrite_try_to_timestamp(node):
    """Databricks try_to_timestamp(s, fmt) has no DuckDB twin: rewrite to try_strptime."""
    if isinstance(node, exp.Anonymous) and str(node.this).lower() == "try_to_timestamp":
        args = node.expressions
        if len(args) == 2 and isinstance(args[1], exp.Literal):
            return exp.Anonymous(this="try_strptime",
                                 expressions=[args[0], exp.Literal.string(_java_format(args[1].name))])
        return exp.TryCast(this=args[0], to=exp.DataType.build("timestamp"))
    return node


def to_duckdb(sql: str) -> str:
    tree = sqlglot.parse_one(sql, read="databricks")
    tree = tree.transform(_rewrite_try_to_timestamp)
    return tree.sql(dialect="duckdb").replace("TIMESTAMPTZ", "TIMESTAMP")


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone='UTC'")
    for schema in ("bronze", "silver", "gold", "qa"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    return con


def run_sql(con, databricks_sql: str):
    """Run one Databricks SQL statement locally and return the result as a list of tuples."""
    return con.execute(to_duckdb(databricks_sql)).fetchall()


# --------------------------------------------------------------------------
# The pipeline run
# --------------------------------------------------------------------------
@dataclass
class PipelineRun:
    con: duckdb.DuckDBPyConnection
    datasets: dict
    warn_counts: dict          # constraint name -> violating rows kept
    drop_counts: dict          # constraint name -> rows dropped (evaluated one rule at a time)


def load_bronze(con, landing_dir: str, bronze_sql: str) -> dict:
    sources = bronze_sources(bronze_sql)
    for table, info in sources.items():
        pattern = os.path.join(landing_dir, info["folder"], "*.csv")
        files = glob.glob(pattern)
        assert files, f"no landing file for {table}: {pattern}"
        con.execute(f"""
            CREATE OR REPLACE TABLE {table} AS
            SELECT * EXCLUDE (filename), current_timestamp AS _ingested_at, filename AS _source_file
            FROM read_csv('{pattern}', header = true, all_varchar = true, filename = true)
        """)
        actual = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()
                  if r[0] not in ("_ingested_at", "_source_file")]
        assert actual == info["columns"], f"{table}: file header {actual} != declared schema {info['columns']}"
    return sources


def run_pipeline(landing_dir: str, expected_rows: list[tuple] | None = None) -> PipelineRun:
    con = connect()
    load_bronze(con, landing_dir, os.path.join(PIPELINE_DIR, "bronze.sql"))
    datasets, warn_counts, drop_counts = {}, {}, {}
    for fname in ("silver.sql", "gold.sql"):
        for ds in parse_pipeline_file(os.path.join(PIPELINE_DIR, fname)):
            drops = [e for e in ds.expectations if e.action == "DROP"]
            warns = [e for e in ds.expectations if e.action != "DROP"]
            query = ds.query
            if drops:
                cond = " AND ".join(f"coalesce(({e.expr}), false)" for e in drops)
                query = f"SELECT * FROM ({query}) AS q WHERE {cond}"
            con.execute(f"CREATE OR REPLACE TABLE {ds.name} AS {to_duckdb(query)}")
            for e in drops:   # how many rows each rule rejects on its own
                n = con.execute(
                    f"SELECT count(*) FROM ({to_duckdb(ds.query)}) AS q WHERE NOT coalesce(({to_duckdb_expr(e.expr)}), false)"
                ).fetchone()[0]
                drop_counts[e.name] = n
            for e in warns:
                n = con.execute(
                    f"SELECT count(*) FROM {ds.name} WHERE NOT coalesce(({to_duckdb_expr(e.expr)}), false)"
                ).fetchone()[0]
                warn_counts[e.name] = n
            datasets[ds.name] = ds
    if expected_rows is not None:
        load_expected(con, expected_rows)
    return PipelineRun(con, datasets, warn_counts, drop_counts)


def to_duckdb_expr(expr: str) -> str:
    return to_duckdb(f"SELECT {expr}")[len("SELECT "):]


def load_expected(con, rows: list[tuple]) -> None:
    con.execute("CREATE OR REPLACE TABLE qa.expected_kpis (metric VARCHAR, dimension VARCHAR, dim_value VARCHAR, expected_value DOUBLE)")
    con.executemany("INSERT INTO qa.expected_kpis VALUES (?, ?, ?, ?)", rows)
