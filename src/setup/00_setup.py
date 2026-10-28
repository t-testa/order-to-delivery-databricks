# Databricks notebook source
# MAGIC %md
# MAGIC # Setup: catalog, schemas and landing volume
# MAGIC Creates the Unity Catalog objects the project needs. Safe to run repeatedly.

# COMMAND ----------

dbutils.widgets.text("catalog", "o2d")
catalog = dbutils.widgets.get("catalog")

existing = {r[0] for r in spark.sql("SHOW CATALOGS").collect()}
if catalog not in existing:
    try:
        spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog} COMMENT 'Order-to-delivery analytics project (synthetic data)'")
    except Exception as error:
        raise RuntimeError(
            f"Could not create catalog '{catalog}': {error}\n"
            "Fix: redeploy the bundle with an existing catalog, for example --var catalog=workspace."
        )
print(f"Using catalog: {catalog}")

# COMMAND ----------

schemas = {
    "bronze": "Raw landing layer: source extracts exactly as received.",
    "silver": "Cleaned and conformed layer with data quality rules.",
    "gold": "Star schema and KPIs for analytics and Genie.",
    "qa": "Acceptance test inputs (expected values) and results.",
}
for name, comment in schemas.items():
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{name} COMMENT '{comment}'")

spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.bronze.landing COMMENT 'Landing zone for the ERP and WMS CSV extracts'")
print("Schemas and landing volume are ready.")
