# Databricks notebook source
# MAGIC %md
# MAGIC # PySpark checks on the order-to-delivery tables
# MAGIC
# MAGIC The pipeline itself is declarative SQL. This notebook uses PySpark (the Python API of Spark) to
# MAGIC double check three claims the README makes, each one computed a second way:
# MAGIC
# MAGIC | Part | Claim being checked | PySpark ideas it shows |
# MAGIC |---|---|---|
# MAGIC | 1 | The silver layer keeps only the latest version of each WMS shipment line (BR-05) and rejects negative quantities (DQ-17) | `select`, `Window`, `row_number`, `filter`, `exceptAll` |
# MAGIC | 2 | OTIF is 60.8% because the failures overlap only partly | `when`, `groupBy`, `agg` |
# MAGIC | 3 | Pharmacy has the worst OTIF | `join`, broadcast, `explain` (shuffle vs broadcast) |
# MAGIC
# MAGIC Run it after the `o2d-end-to-end` job has succeeded. It only reads tables, it never changes them.
# MAGIC The last cell fails loudly if any of the three checks disagrees with the pipeline.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

dbutils.widgets.text("catalog", "o2d")
catalog = dbutils.widgets.get("catalog")


def table(name):
    """Read a table such as 'silver.shipment_lines' from the chosen catalog."""
    return spark.table(f"{catalog}.{name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Part 1. Rebuild the shipment line cleaning in PySpark and compare it with silver
# MAGIC
# MAGIC **Why this matters.** The WMS re-sends lines and sends corrections, so bronze holds several versions of the
# MAGIC same line. Business rule BR-05 says the latest version wins. Silver does this in SQL with
# MAGIC `row_number() OVER (PARTITION BY shipment_id, line_no ORDER BY updated_at DESC)`.
# MAGIC Here the same rule is written a second way, then the two results are compared row by row.
# MAGIC
# MAGIC **How it works, step by step.**
# MAGIC 1. `select` with expressions turns the raw text columns of bronze into clean typed columns, like `silver.sql` does.
# MAGIC 2. A `Window` groups rows by `(shipment_id, line_no)` and sorts them newest first.
# MAGIC `row_number()` gives each row its rank inside its group, and rank 1 is the latest version.
# MAGIC 3. Only after keeping rank 1 do we drop negative quantities and missing product keys, because the
# MAGIC expectations in `silver.sql` run on the output of the query.
# MAGIC 4. `exceptAll` returns the rows that are in one table and not in the other, duplicates included.
# MAGIC Zero rows both ways means the two tables are identical.
# MAGIC
# MAGIC **Why `F.expr("try_cast(...)")`.** Databricks runs Spark in ANSI mode, where a normal cast fails the whole
# MAGIC query on text that is not a number. `try_cast` returns NULL instead, the same choice `silver.sql` makes.

# COMMAND ----------

bronze = table("bronze.wms_shipment_lines")
silver = table("silver.shipment_lines")

parsed = bronze.select(
    F.nullif(F.trim("shipment_id"), F.lit("")).alias("shipment_id"),
    F.expr("try_cast(line_no AS INT)").alias("line_no"),
    # Order numbers appear as SO100001, so100001 or "SO100001 ": keep letters and digits, upper case (BR-02)
    F.nullif(F.upper(F.regexp_replace(F.trim("order_ref"), "[^A-Za-z0-9]", "")), F.lit("")).alias("order_key"),
    # SKU 42, 00042 and SKU-00042 all become the 5 digit key 00042 (BR-02)
    F.lpad(F.nullif(F.regexp_extract("sku", "([0-9]+)", 1), F.lit("")), 5, "0").alias("product_key"),
    F.expr("try_cast(shipped_qty_each AS INT)").alias("shipped_qty_each"),
    F.nullif(F.trim("lot_id"), F.lit("")).alias("lot_id"),
    F.expr("try_cast(updated_at AS TIMESTAMP)").alias("updated_at"),
)

# Latest version wins (BR-05)
newest_first = Window.partitionBy("shipment_id", "line_no").orderBy(F.col("updated_at").desc())
latest = (
    parsed
    .withColumn("rank_in_line", F.row_number().over(newest_first))
    .filter(F.col("rank_in_line") == 1)
    .drop("rank_in_line")
)

# Reject negative quantities (DQ-17) and missing product keys (DQ-18)
rebuilt = latest.filter((F.col("shipped_qty_each") >= 0) & F.col("product_key").isNotNull())

n_bronze = bronze.count()
n_latest = latest.count()
n_rebuilt = rebuilt.count()
n_silver = silver.count()

# Compare the two tables in both directions. select(*rebuilt.columns) forces the same column order.
only_in_rebuilt = rebuilt.exceptAll(silver.select(*rebuilt.columns)).count()
only_in_silver = silver.select(*rebuilt.columns).exceptAll(rebuilt).count()

print(f"bronze rows                          : {n_bronze:,}")
print(f"removed as duplicate or old version  : {n_bronze - n_latest:,}")
print(f"rejected for negative quantity       : {n_latest - n_rebuilt:,}")
print(f"PySpark rebuild                      : {n_rebuilt:,}")
print(f"silver.shipment_lines                : {n_silver:,}")
print(f"rows only in the rebuild             : {only_in_rebuilt:,}")
print(f"rows only in silver                  : {only_in_silver:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Part 2. How do the OTIF failures overlap?
# MAGIC
# MAGIC **Why this matters.** The README says on-time delivery looks healthy (89.6%) while OTIF is 60.8%, and that the
# MAGIC two failures "overlap only partly". The README never shows the split. This cell does.
# MAGIC
# MAGIC **Definitions from `gold.fact_order`.** `is_otif` means every line was fully delivered by the promised date.
# MAGIC `is_in_full` means the warehouse eventually shipped everything ordered. `is_on_time` means the first delivery
# MAGIC arrived by the promised date. Orders without a promised date are excluded, as in BR-08.
# MAGIC
# MAGIC **How it works.** `F.when(...).when(...).otherwise(...)` is a CASE expression. The first condition that is true
# MAGIC gives the order its label, so the four labels never overlap. `groupBy("outcome").agg(F.count("*"))` counts orders
# MAGIC per label. The percentage uses the total computed once, so each row is a share of the same denominator.

# COMMAND ----------

orders = table("gold.fact_order").filter("is_kpi_scope AND is_on_time IS NOT NULL")

labelled = orders.withColumn(
    "outcome",
    F.when(F.col("is_otif"), "1. OTIF")
    .when(F.col("is_in_full"), "2. Complete, but part of it arrived after the promise")
    .when(F.col("is_on_time"), "3. Short, first delivery on time")
    .otherwise("4. Short and late"),
)

total_orders = labelled.count()
outcomes = (
    labelled.groupBy("outcome")
    .agg(F.count("*").alias("orders"))
    .withColumn("share_pct", F.round(F.col("orders") * 100 / F.lit(total_orders), 1))
    .orderBy("outcome")
)
display(outcomes)

# Cross check against the pipeline's own KPI table (a different computation path to the same number)
kpi = table("gold.kpi_order_performance").agg(
    F.sum("otif_orders").alias("otif"), F.sum("otd_eligible_orders").alias("eligible")
).first()
otif_from_kpi_table = kpi["otif"] / kpi["eligible"]
otif_from_fact_order = labelled.filter(F.col("outcome") == "1. OTIF").count() / total_orders
print(f"OTIF from gold.kpi_order_performance : {otif_from_kpi_table:.4f}")
print(f"OTIF from PySpark on gold.fact_order : {otif_from_fact_order:.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Part 3. OTIF by customer segment, and how Spark executes the join
# MAGIC
# MAGIC **Why this matters.** The README says pharmacy customers have the worst OTIF. Here the segment comes from
# MAGIC `gold.dim_customer`, so the result needs a join between a big table (orders) and a small one (customers).
# MAGIC
# MAGIC **What to learn.** Spark splits tables into partitions spread over machines. A join normally needs a **shuffle**:
# MAGIC rows with the same key are moved to the same machine, which is the expensive part of most Spark jobs.
# MAGIC When one side is small, Spark can instead copy it to every machine (a **broadcast**) and skip the shuffle.
# MAGIC `F.broadcast(dim_customer)` asks for that. `explain()` prints the physical plan. In the output, look for the word
# MAGIC `Broadcast` on the join and for `Exchange` or `Shuffle`, which marks where data moves between machines.
# MAGIC The final `groupBy` still needs one shuffle, which is normal.
# MAGIC
# MAGIC Plan names differ slightly on serverless compute (Photon adds its own prefix). The words to look for stay the same.

# COMMAND ----------

dim_customer = table("gold.dim_customer").select("customer_id", "segment")

by_segment = (
    orders.join(F.broadcast(dim_customer), on="customer_id", how="inner")
    .groupBy("segment")
    .agg(
        F.count("*").alias("orders"),
        F.sum(F.col("is_otif").cast("int")).alias("otif_orders"),
    )
    .withColumn("otif_pct", F.round(F.col("otif_orders") * 100 / F.col("orders"), 1))
    .orderBy("otif_pct")
)
display(by_segment)
by_segment.explain()

# Same numbers from the KPI table, grouped the other way round
kpi_by_segment = (
    table("gold.kpi_order_performance")
    .groupBy("segment")
    .agg(F.sum("otif_orders").alias("kpi_otif"), F.sum("otd_eligible_orders").alias("kpi_eligible"))
)
segment_check = (
    by_segment.join(kpi_by_segment, "segment")
    .withColumn("same_orders", F.col("orders") == F.col("kpi_eligible"))
    .withColumn("same_otif", F.col("otif_orders") == F.col("kpi_otif"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verdict
# MAGIC
# MAGIC Each check prints PASS or FAIL. The cell raises an error if any check fails, so a green run means all three agree.

# COMMAND ----------

checks = {
    "Part 1: PySpark rebuild equals silver.shipment_lines": n_rebuilt == n_silver and only_in_rebuilt == 0 and only_in_silver == 0,
    "Part 2: OTIF from fact_order equals the KPI table": abs(otif_from_kpi_table - otif_from_fact_order) < 1e-9,
    "Part 3: every segment matches the KPI table": segment_check.filter(~(F.col("same_orders") & F.col("same_otif"))).count() == 0,
}
for name, ok in checks.items():
    print("PASS" if ok else "FAIL", name)
assert all(checks.values()), "At least one PySpark check disagrees with the pipeline"
