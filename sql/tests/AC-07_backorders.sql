-- AC-07 (US-04): backorder line count and backorder cases equal the reference values. Rule: BR-11.
WITH actual AS (
  SELECT sum(backorder_lines) AS backorder_lines, sum(backorder_cases) AS backorder_cases
  FROM gold.kpi_order_performance
)
SELECT
  'AC-07' AS ac_id,
  e.metric AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(CASE e.metric WHEN 'backorder_lines' THEN a.backorder_lines ELSE a.backorder_cases END AS DOUBLE) AS actual,
  coalesce(abs(CASE e.metric WHEN 'backorder_lines' THEN a.backorder_lines ELSE a.backorder_cases END
               - e.expected_value) <= 0.0001, false) AS passed
FROM qa.expected_kpis e
CROSS JOIN actual a
WHERE e.metric IN ('backorder_lines', 'backorder_cases')
