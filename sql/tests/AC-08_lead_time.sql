-- AC-08 (US-04): average order-to-delivery lead time equals the reference value. Rule: BR-13.
SELECT
  'AC-08' AS ac_id,
  'avg_lead_time_days all all' AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(sum(k.lead_time_days_sum) / sum(k.lead_time_orders) AS DOUBLE) AS actual,
  coalesce(abs(sum(k.lead_time_days_sum) / sum(k.lead_time_orders) - e.expected_value) <= 0.000001, false) AS passed
FROM qa.expected_kpis e
CROSS JOIN gold.kpi_order_performance k
WHERE e.metric = 'avg_lead_time_days'
GROUP BY e.expected_value
