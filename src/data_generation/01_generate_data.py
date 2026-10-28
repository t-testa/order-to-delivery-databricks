# Databricks notebook source
# MAGIC %md
# MAGIC # Generate the synthetic ERP and WMS extracts
# MAGIC Writes the CSV files to the landing volume and stores the reference KPI values (computed independently
# MAGIC with pandas) in `qa.expected_kpis`. Deterministic: the same seed always gives the same data.

# COMMAND ----------

import os
import shutil
import sys
import tempfile

dbutils.widgets.text("catalog", "o2d")
dbutils.widgets.text("seed", "42")
dbutils.widgets.text("orders", "15000")
catalog = dbutils.widgets.get("catalog")
seed = int(dbutils.widgets.get("seed"))
n_orders = int(dbutils.widgets.get("orders"))

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
sys.path.insert(0, os.path.dirname("/Workspace" + notebook_path))

import generate  # noqa: E402
import reference  # noqa: E402

# COMMAND ----------

work_dir = tempfile.mkdtemp()
manifest = generate.generate(work_dir, seed=seed, n_orders=n_orders)
print(manifest["row_counts"])

landing = f"/Volumes/{catalog}/bronze/landing"
for source in ("erp", "wms"):
    target = os.path.join(landing, source)
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.copytree(os.path.join(work_dir, source), target)
shutil.copyfile(os.path.join(work_dir, "manifest.json"), os.path.join(landing, "manifest.json"))
print(f"Landing files written to {landing}")

# COMMAND ----------

expected = reference.expected_metrics(work_dir)
spark.createDataFrame(
    [(m, d, v, float(x)) for m, d, v, x in expected],
    schema="metric STRING, dimension STRING, dim_value STRING, expected_value DOUBLE",
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{catalog}.qa.expected_kpis")

genie = reference.genie_reference(work_dir)
spark.createDataFrame(
    genie, schema="question_id STRING, question STRING, expected_answer STRING"
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{catalog}.qa.genie_reference")
print(f"Stored {len(expected)} expected KPI values and {len(genie)} Genie reference answers.")
