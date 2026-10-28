-- AC-03 (US-02): overall and per-warehouse on-time delivery percentage equal the reference values. Rule: BR-08.
WITH actual AS (
  SELECT 'all' AS dimension, 'all' AS dim_value, sum(on_time_orders) / sum(otd_eligible_orders) AS actual
  FROM gold.kpi_order_performance
  UNION ALL
  SELECT 'warehouse', warehouse_code, sum(on_time_orders) / sum(otd_eligible_orders)
  FROM gold.kpi_order_performance
  GROUP BY warehouse_code
)
SELECT
  'AC-03' AS ac_id,
  concat('otd_pct ', e.dimension, ' ', e.dim_value) AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(a.actual AS DOUBLE) AS actual,
  coalesce(abs(a.actual - e.expected_value) <= 0.000001, false) AS passed
FROM qa.expected_kpis e
LEFT JOIN actual a ON a.dimension = e.dimension AND a.dim_value = e.dim_value
WHERE e.metric = 'otd_pct'
