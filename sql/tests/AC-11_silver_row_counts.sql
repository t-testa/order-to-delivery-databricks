-- AC-11 (US-06): silver row counts, after the data quality rules, equal the reference counts. Rules: DQ-01 to DQ-22.
WITH actual AS (
  SELECT 'customers' AS dim_value, count(*) AS n FROM silver.customers
  UNION ALL SELECT 'products', count(*) FROM silver.products
  UNION ALL SELECT 'orders', count(*) FROM silver.orders
  UNION ALL SELECT 'order_lines', count(*) FROM silver.order_lines
  UNION ALL SELECT 'shipments', count(*) FROM silver.shipments
  UNION ALL SELECT 'shipment_lines', count(*) FROM silver.shipment_lines
  UNION ALL SELECT 'lots', count(*) FROM silver.lots
)
SELECT
  'AC-11' AS ac_id,
  concat('silver row count ', e.dim_value) AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(a.n AS DOUBLE) AS actual,
  coalesce(a.n = e.expected_value, false) AS passed
FROM qa.expected_kpis e
LEFT JOIN actual a ON a.dim_value = e.dim_value
WHERE e.metric = 'silver_rows'
