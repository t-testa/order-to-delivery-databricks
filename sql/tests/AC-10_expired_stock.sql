-- AC-10 (US-05): expired stock units and value at the snapshot date equal the reference values. Rule: BR-15.
WITH actual AS (
  SELECT sum(expired_units) AS units, sum(expired_stock_value) AS value
  FROM gold.kpi_inventory_expiry
)
SELECT
  'AC-10' AS ac_id,
  e.metric AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(CASE e.metric WHEN 'expired_stock_units' THEN a.units ELSE a.value END AS DOUBLE) AS actual,
  coalesce(abs(CASE e.metric WHEN 'expired_stock_units' THEN a.units ELSE a.value END
               - e.expected_value) <= 0.01, false) AS passed
FROM qa.expected_kpis e
CROSS JOIN actual a
WHERE e.metric IN ('expired_stock_units', 'expired_stock_value')
