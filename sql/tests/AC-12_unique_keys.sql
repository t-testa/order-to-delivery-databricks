-- AC-12 (US-06): keys are unique at the declared grain in every silver and gold table. Rule: BR-05.
WITH dupes AS (
  SELECT 'silver.customers' AS table_name, count(*) AS n FROM (SELECT customer_id FROM silver.customers GROUP BY customer_id HAVING count(*) > 1) t
  UNION ALL SELECT 'silver.products', count(*) FROM (SELECT product_key FROM silver.products GROUP BY product_key HAVING count(*) > 1) t
  UNION ALL SELECT 'silver.orders', count(*) FROM (SELECT order_key FROM silver.orders GROUP BY order_key HAVING count(*) > 1) t
  UNION ALL SELECT 'silver.order_lines', count(*) FROM (SELECT order_key, line_no FROM silver.order_lines GROUP BY order_key, line_no HAVING count(*) > 1) t
  UNION ALL SELECT 'silver.shipments', count(*) FROM (SELECT shipment_id FROM silver.shipments GROUP BY shipment_id HAVING count(*) > 1) t
  UNION ALL SELECT 'silver.shipment_lines', count(*) FROM (SELECT shipment_id, line_no FROM silver.shipment_lines GROUP BY shipment_id, line_no HAVING count(*) > 1) t
  UNION ALL SELECT 'silver.lots', count(*) FROM (SELECT lot_id FROM silver.lots GROUP BY lot_id HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.dim_date', count(*) FROM (SELECT date_key FROM gold.dim_date GROUP BY date_key HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.dim_customer', count(*) FROM (SELECT customer_id FROM gold.dim_customer GROUP BY customer_id HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.dim_product', count(*) FROM (SELECT product_key FROM gold.dim_product GROUP BY product_key HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.dim_warehouse', count(*) FROM (SELECT warehouse_code FROM gold.dim_warehouse GROUP BY warehouse_code HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.fact_order', count(*) FROM (SELECT order_id FROM gold.fact_order GROUP BY order_id HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.fact_order_line', count(*) FROM (SELECT order_id, line_no FROM gold.fact_order_line GROUP BY order_id, line_no HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.fact_shipment_line', count(*) FROM (SELECT shipment_id, line_no FROM gold.fact_shipment_line GROUP BY shipment_id, line_no HAVING count(*) > 1) t
  UNION ALL SELECT 'gold.fact_inventory_lot', count(*) FROM (SELECT lot_id FROM gold.fact_inventory_lot GROUP BY lot_id HAVING count(*) > 1) t
)
SELECT
  'AC-12' AS ac_id,
  concat('duplicate keys in ', table_name) AS check_name,
  CAST(0 AS DOUBLE) AS expected,
  CAST(n AS DOUBLE) AS actual,
  n = 0 AS passed
FROM dupes
