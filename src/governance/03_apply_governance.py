# Databricks notebook source
# MAGIC %md
# MAGIC # Apply Unity Catalog governance
# MAGIC Applies column descriptions and tags from `docs/data_dictionary.csv` to the silver and gold tables.
# MAGIC Table descriptions are defined in the pipeline itself. This step runs after every pipeline update because
# MAGIC pipeline-managed tables can lose metadata that is not part of their definition when they are refreshed.

# COMMAND ----------

import os
import sys

dbutils.widgets.text("catalog", "o2d")
catalog = dbutils.widgets.get("catalog")

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
notebook_dir = os.path.dirname("/Workspace" + notebook_path)
sys.path.insert(0, notebook_dir)
repo_root = os.path.dirname(os.path.dirname(notebook_dir))

from statements import build_statements, read_dictionary  # noqa: E402

rows = read_dictionary(os.path.join(repo_root, "docs", "data_dictionary.csv"))
statements = build_statements(rows, catalog)
print(f"{len(rows)} dictionary rows -> {len(statements)} statements for catalog {catalog}")

# COMMAND ----------

applied, fallback_used, failed = 0, 0, []
for st in statements:
    try:
        spark.sql(st["sql"])
        applied += 1
    except Exception as first_error:
        try:
            spark.sql(st["fallback_sql"])
            applied += 1
            fallback_used += 1
        except Exception as second_error:
            failed.append((st["kind"], st["target"], str(first_error)[:200], str(second_error)[:200]))

print(f"applied: {applied} (ALTER TABLE fallback used {fallback_used} times), failed: {len(failed)}")
for f in failed[:10]:
    print(f)
if failed:
    raise RuntimeError(f"{len(failed)} governance statements failed. First error: {failed[0]}")
