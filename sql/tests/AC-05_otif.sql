-- AC-05 (US-03): overall and per-month OTIF percentage equal the reference values. Rule: BR-10.
WITH actual AS (
  SELECT 'all' AS dimension, 'all' AS dim_value, sum(otif_orders) / sum(otd_eligible_orders) AS actual
  FROM gold.kpi_order_performance
  UNION ALL
  SELECT 'year_month', year_month, sum(otif_orders) / sum(otd_eligible_orders)
  FROM gold.kpi_order_performance
  GROUP BY year_month
)
SELECT
  'AC-05' AS ac_id,
  concat('otif_pct ', e.dimension, ' ', e.dim_value) AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(a.actual AS DOUBLE) AS actual,
  coalesce(abs(a.actual - e.expected_value) <= 0.000001, false) AS passed
FROM qa.expected_kpis e
LEFT JOIN actual a ON a.dimension = e.dimension AND a.dim_value = e.dim_value
WHERE e.metric = 'otif_pct'
UNION ALL
SELECT
  'AC-05',
  'in_full_pct all all',
  CAST(e.expected_value AS DOUBLE),
  CAST(sum(k.in_full_orders) / sum(k.orders) AS DOUBLE),
  coalesce(abs(sum(k.in_full_orders) / sum(k.orders) - e.expected_value) <= 0.000001, false)
FROM qa.expected_kpis e
CROSS JOIN gold.kpi_order_performance k
WHERE e.metric = 'in_full_pct'
GROUP BY e.expected_value
