-- AC-13 (US-06): every foreign key in the gold facts resolves to a gold dimension row. Rule: BR-17.
WITH orphans AS (
  SELECT 'fact_order.customer_id' AS fk, count(*) AS n
  FROM gold.fact_order f LEFT JOIN gold.dim_customer d ON d.customer_id = f.customer_id WHERE d.customer_id IS NULL
  UNION ALL SELECT 'fact_order.warehouse_code', count(*)
  FROM gold.fact_order f LEFT JOIN gold.dim_warehouse d ON d.warehouse_code = f.warehouse_code WHERE d.warehouse_code IS NULL
  UNION ALL SELECT 'fact_order.order_date_key', count(*)
  FROM gold.fact_order f LEFT JOIN gold.dim_date d ON d.date_key = f.order_date_key WHERE d.date_key IS NULL
  UNION ALL SELECT 'fact_order.first_delivered_date_key', count(*)
  FROM gold.fact_order f LEFT JOIN gold.dim_date d ON d.date_key = f.first_delivered_date_key
  WHERE f.first_delivered_date_key IS NOT NULL AND d.date_key IS NULL
  UNION ALL SELECT 'fact_order_line.product_key', count(*)
  FROM gold.fact_order_line f LEFT JOIN gold.dim_product d ON d.product_key = f.product_key WHERE d.product_key IS NULL
  UNION ALL SELECT 'fact_order_line.order_id', count(*)
  FROM gold.fact_order_line f LEFT JOIN gold.fact_order d ON d.order_id = f.order_id WHERE d.order_id IS NULL
  UNION ALL SELECT 'fact_shipment_line.product_key', count(*)
  FROM gold.fact_shipment_line f LEFT JOIN gold.dim_product d ON d.product_key = f.product_key WHERE d.product_key IS NULL
  UNION ALL SELECT 'fact_shipment_line.ship_date_key', count(*)
  FROM gold.fact_shipment_line f LEFT JOIN gold.dim_date d ON d.date_key = f.ship_date_key
  WHERE f.ship_date_key IS NOT NULL AND d.date_key IS NULL
  UNION ALL SELECT 'fact_inventory_lot.product_key', count(*)
  FROM gold.fact_inventory_lot f LEFT JOIN gold.dim_product d ON d.product_key = f.product_key WHERE d.product_key IS NULL
  UNION ALL SELECT 'fact_inventory_lot.warehouse_code', count(*)
  FROM gold.fact_inventory_lot f LEFT JOIN gold.dim_warehouse d ON d.warehouse_code = f.warehouse_code WHERE d.warehouse_code IS NULL
)
SELECT
  'AC-13' AS ac_id,
  concat('orphan foreign keys: ', fk) AS check_name,
  CAST(0 AS DOUBLE) AS expected,
  CAST(n AS DOUBLE) AS actual,
  n = 0 AS passed
FROM orphans
