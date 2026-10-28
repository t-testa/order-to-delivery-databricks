"""The data dictionary covers every silver and gold column and drives the governance statements."""
import os

import emulator
from statements import build_statements, parse_tags, read_dictionary

DICTIONARY = os.path.join(emulator.REPO_ROOT, "docs", "data_dictionary.csv")


def _warehouse_columns(run):
    out = set()
    for schema in ("silver", "gold"):
        for table, column in run.con.execute(
                f"SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = '{schema}'").fetchall():
            out.add((f"{schema}.{table}", column))
    return out


def test_dictionary_covers_every_silver_and_gold_column_exactly(run):
    rows = read_dictionary(DICTIONARY)
    documented = {(r["table_name"], r["column_name"]) for r in rows if r["column_name"]}
    assert documented == _warehouse_columns(run)


def test_every_description_is_filled_in_and_quote_safe(run):
    for r in read_dictionary(DICTIONARY):
        assert r["description"].strip(), r
        assert "'" not in r["description"], f"apostrophe would break the ALTER statement: {r}"


def test_table_descriptions_match_the_pipeline_comments(run):
    rows = {r["table_name"]: r["description"] for r in read_dictionary(DICTIONARY) if not r["column_name"]}
    for name, ds in run.datasets.items():
        assert rows[name] == ds.comment, name


def test_only_the_personal_data_columns_are_tagged_pii():
    rows = read_dictionary(DICTIONARY)
    pii = [(r["table_name"], r["column_name"]) for r in rows if ("pii", "true") in parse_tags(r["tags"])]
    assert sorted(pii) == [("silver.customers", "email"), ("silver.customers", "phone")]


def test_statements_are_generated_for_comments_and_tags():
    rows = read_dictionary(DICTIONARY)
    statements = build_statements(rows, "o2d")
    kinds = [s["kind"] for s in statements]
    assert kinds.count("column_comment") == sum(1 for r in rows if r["column_name"])
    assert kinds.count("table_tags") == sum(1 for r in rows if not r["column_name"])
    pii = [s for s in statements if s["kind"] == "column_tags" and "'pii' = 'true'" in s["sql"]]
    assert {s["target"] for s in pii} == {"o2d.silver.customers.email", "o2d.silver.customers.phone"}
    sample = next(s for s in statements if s["target"] == "o2d.gold.kpi_order_performance.fill_rate"
                  and s["kind"] == "column_comment")
    assert sample["sql"].startswith("ALTER MATERIALIZED VIEW o2d.gold.kpi_order_performance ALTER COLUMN fill_rate COMMENT '")
    assert sample["fallback_sql"].startswith("ALTER TABLE o2d.gold.kpi_order_performance ALTER COLUMN fill_rate")
