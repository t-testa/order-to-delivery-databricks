"""Local verification of the pipeline logic (no Databricks needed).

The SQL files that Databricks runs are executed through DuckDB and graded
against the independent pandas reference. If these pass, the transformation
logic is right; what remains to verify on Databricks is the platform itself.
"""
import glob
import os

import pytest

import emulator

SQL_FILES = sorted(glob.glob(os.path.join(emulator.TESTS_SQL_DIR, "*.sql")))


def _is_databricks_only(path):
    with open(path, encoding="utf-8") as fh:
        return fh.readline().strip().lower() == "-- requires: databricks"


LOCAL_FILES = [p for p in SQL_FILES if not _is_databricks_only(p)]


def test_there_is_one_test_file_per_acceptance_criterion():
    ids = {os.path.basename(p).split("_")[0][:5] for p in SQL_FILES}
    assert ids == {f"AC-{n:02d}" for n in range(1, 17)}


@pytest.mark.parametrize("path", LOCAL_FILES, ids=[os.path.basename(p) for p in LOCAL_FILES])
def test_acceptance_sql_passes_locally(run, path):
    with open(path, encoding="utf-8") as fh:
        sql = fh.read().strip().rstrip(";")
    rows = emulator.run_sql(run.con, sql)
    assert rows, f"{os.path.basename(path)} returned no rows"
    failures = [r for r in rows if not r[4]]
    assert not failures, f"failed checks: {failures[:5]}"


def test_silver_drops_match_the_injected_defects(run, landing_dir):
    """The rules reject what the generator injected, and nothing else."""
    import json
    manifest = json.load(open(os.path.join(landing_dir, "manifest.json")))["injected_defects"]
    assert run.drop_counts["dq06_customer_id_not_null"] == manifest["null_customer_orders"]
    assert run.drop_counts["dq11_ordered_qty_positive"] > 0
    # negative shipment quantities: dedupe happens first, so the count is at most the injected number
    assert 0 < run.drop_counts["dq17_shipped_qty_not_negative"] <= manifest["negative_shipment_qty"]
    assert run.warn_counts["dq02_email_valid"] == manifest["invalid_emails"]
    assert run.warn_counts["dq09_promised_date_present"] > 0


def test_kpi_values_are_in_a_plausible_range(run):
    fill, otd, otif = run.con.execute("""
        SELECT sum(filled_cases) / sum(ordered_cases),
               sum(on_time_orders) / sum(otd_eligible_orders),
               sum(otif_orders) / sum(otd_eligible_orders)
        FROM gold.kpi_order_performance""").fetchone()
    assert 0.90 < fill < 1.0
    assert 0.80 < otd < 1.0
    assert 0.40 < otif < otd


def test_no_pii_columns_in_gold(run):
    cols = run.con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'gold'").fetchall()
    assert not [c for (c,) in cols if c.lower() in {"email", "phone"}]
