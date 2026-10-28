-- AC-09 (US-05): shipment lines and cases shipped from expired lots equal the reference values. Rule: BR-14.
WITH actual AS (
  SELECT sum(expired_lot_lines) AS lines, sum(expired_lot_cases) AS cases
  FROM gold.kpi_expired_lots
)
SELECT
  'AC-09' AS ac_id,
  e.metric AS check_name,
  CAST(e.expected_value AS DOUBLE) AS expected,
  CAST(CASE e.metric WHEN 'expired_lot_shipment_lines' THEN a.lines ELSE a.cases END AS DOUBLE) AS actual,
  coalesce(abs(CASE e.metric WHEN 'expired_lot_shipment_lines' THEN a.lines ELSE a.cases END
               - e.expected_value) <= 0.0001, false) AS passed
FROM qa.expected_kpis e
CROSS JOIN actual a
WHERE e.metric IN ('expired_lot_shipment_lines', 'expired_lot_shipment_cases')
