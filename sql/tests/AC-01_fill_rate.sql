-- AC-01 (US-01): overall and per-segment fill rate equal the reference values. Rule: BR-07.
WITH actual AS (
  SELECT 'all' AS dimension, 'all' AS dim_value, sum(filled_cases) / sum(ordered_cases) AS actual
  FROM gold.kpi_order_performance
  UNION ALL
  SELECT 'segment', segment, sum(filled_cases) / sum(ordered_cases)
  FROM gold.kpi_order_performance
  GROUP BY segment
)
SELECT
  'AC-01' AS ac_id,
  concat('fill_rate ', e.dimension, ' ', e.dim_value) AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(a.actual AS DOUBLE) AS actual,
  coalesce(abs(a.actual - e.expected_value) <= 0.000001, false) AS passed
FROM qa.expected_kpis e
LEFT JOIN actual a ON a.dimension = e.dimension AND a.dim_value = e.dim_value
WHERE e.metric = 'fill_rate'
