"""Static checks on the SQL files and the bronze contract."""
import glob
import os
import re

import pytest
import sqlglot

import emulator

ALL_SQL = sorted(glob.glob(os.path.join(emulator.REPO_ROOT, "sql", "tests", "*.sql")))


@pytest.mark.parametrize("path", ALL_SQL, ids=[os.path.basename(p) for p in ALL_SQL])
def test_acceptance_sql_parses_as_databricks_sql(path):
    sql = open(path, encoding="utf-8").read().strip().rstrip(";")
    sqlglot.parse_one(sql, read="databricks")


def test_every_acceptance_check_returns_the_agreed_columns():
    for path in ALL_SQL:
        sql = open(path, encoding="utf-8").read().strip().rstrip(";")
        names = sqlglot.parse_one(sql, read="databricks").named_selects
        assert names == ["ac_id", "check_name", "expected", "actual", "passed"], (os.path.basename(path), names)


def test_pipeline_files_declare_every_silver_and_gold_dataset_once(run):
    names = list(run.datasets)
    assert len(names) == len(set(names)) == 7 + 12


def test_every_dq_rule_in_the_spec_exists_in_the_pipeline(run):
    spec = open(os.path.join(emulator.REPO_ROOT, "docs", "02_business_rules.md"), encoding="utf-8").read()
    spec_rules = set(re.findall(r"\| (DQ-\d\d) \|", spec))
    pipeline_rules = {re.match(r"(dq\d\d)", e.name).group(1).upper().replace("DQ", "DQ-")
                      for ds in run.datasets.values() for e in ds.expectations}
    assert spec_rules == pipeline_rules


def test_bronze_declares_every_landing_folder_the_generator_writes(landing_dir):
    sources = emulator.bronze_sources(os.path.join(emulator.PIPELINE_DIR, "bronze.sql"))
    folders = {info["folder"] for info in sources.values()}
    written = {os.path.relpath(os.path.dirname(p), landing_dir)
               for p in glob.glob(os.path.join(landing_dir, "*", "*", "*.csv"))}
    assert folders == written
