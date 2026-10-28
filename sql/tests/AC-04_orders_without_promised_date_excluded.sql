-- AC-04 (US-02): orders without a promised date are excluded from the on-time denominator,
-- and the number excluded equals the reference. Rule: BR-08.
WITH actual AS (
  SELECT
    sum(orders) AS in_scope_orders,
    sum(otd_eligible_orders) AS eligible_orders,
    sum(orders) - sum(otd_eligible_orders) AS excluded_orders
  FROM gold.kpi_order_performance
)
SELECT
  'AC-04' AS ac_id,
  concat('KPI scope: ', e.metric) AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(CASE e.metric
         WHEN 'orders_in_scope' THEN a.in_scope_orders
         WHEN 'otd_eligible_orders' THEN a.eligible_orders
         WHEN 'otd_excluded_orders' THEN a.excluded_orders
       END AS DOUBLE) AS actual,
  coalesce(e.expected_value = CASE e.metric
         WHEN 'orders_in_scope' THEN a.in_scope_orders
         WHEN 'otd_eligible_orders' THEN a.eligible_orders
         WHEN 'otd_excluded_orders' THEN a.excluded_orders
       END, false) AS passed
FROM qa.expected_kpis e
CROSS JOIN actual a
WHERE e.metric IN ('orders_in_scope', 'otd_eligible_orders', 'otd_excluded_orders')
