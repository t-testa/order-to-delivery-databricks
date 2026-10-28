-- AC-06 (US-03): in every KPI row OTIF orders never exceed on-time orders or in-full orders. Rule: BR-10.
SELECT
  'AC-06' AS ac_id,
  'KPI rows where otif_orders > on_time_orders or otif_orders > in_full_orders' AS check_name,
  CAST(0 AS DOUBLE) AS expected,
  CAST(count(*) AS DOUBLE) AS actual,
  count(*) = 0 AS passed
FROM gold.kpi_order_performance
WHERE otif_orders > on_time_orders OR otif_orders > in_full_orders
