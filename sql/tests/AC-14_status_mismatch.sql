-- AC-14 (US-06): the number of orders where the ERP status contradicts the WMS equals the reference,
-- and none of them is inside the KPI scope. Rule: BR-16.
SELECT
  'AC-14' AS ac_id,
  'orders listed in gold.dq_status_mismatch' AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(count(m.order_id) AS DOUBLE) AS actual,
  count(m.order_id) = e.expected_value AS passed
FROM qa.expected_kpis e
CROSS JOIN (SELECT order_id FROM gold.dq_status_mismatch) m
WHERE e.metric = 'status_mismatch_orders'
GROUP BY e.expected_value
UNION ALL
SELECT
  'AC-14',
  'mismatched orders that are inside the KPI scope',
  CAST(0 AS DOUBLE),
  CAST(count(*) AS DOUBLE),
  count(*) = 0
FROM gold.dq_status_mismatch m
JOIN gold.fact_order f ON f.order_id = m.order_id
WHERE f.is_kpi_scope
