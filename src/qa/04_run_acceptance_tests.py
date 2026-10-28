# Databricks notebook source
# MAGIC %md
# MAGIC # Run the SQL acceptance tests
# MAGIC Runs every file in `sql/tests/` (one or more checks per acceptance criterion), stores the results in
# MAGIC `qa.acceptance_results` and fails the job if any check fails.

# COMMAND ----------

import glob
import os

dbutils.widgets.text("catalog", "o2d")
catalog = dbutils.widgets.get("catalog")

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
repo_root = os.path.dirname(os.path.dirname(os.path.dirname("/Workspace" + notebook_path)))
spark.sql(f"USE CATALOG {catalog}")

# COMMAND ----------

from pyspark.sql import functions as F

frames = []
for path in sorted(glob.glob(os.path.join(repo_root, "sql", "tests", "*.sql"))):
    with open(path, encoding="utf-8") as fh:
        sql = fh.read().strip().rstrip(";")
    frames.append(spark.sql(sql).withColumn("test_file", F.lit(os.path.basename(path))))

results = frames[0]
for frame in frames[1:]:
    results = results.unionByName(frame)
results = results.withColumn("run_at", F.current_timestamp())
results.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{catalog}.qa.acceptance_results")

# COMMAND ----------

summary = spark.table(f"{catalog}.qa.acceptance_results").orderBy("ac_id", "check_name")
display(summary)
total = summary.count()
failed = summary.filter("NOT passed").collect()
print(f"{total - len(failed)} of {total} checks passed")
if failed:
    for row in failed:
        print("FAILED:", row["ac_id"], row["check_name"], "expected", row["expected"], "actual", row["actual"])
    raise AssertionError(f"{len(failed)} acceptance checks failed")
