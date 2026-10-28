-- AC-02 (US-01): no order line has filled quantity above ordered quantity (an over-shipment is never credited).
-- Rule: BR-07, BR-12. Checked in cases and in each.
SELECT
  'AC-02' AS ac_id,
  'order lines with filled_cases > ordered_cases' AS check_name,
  CAST(0 AS DOUBLE) AS expected,
  CAST(count(*) AS DOUBLE) AS actual,
  count(*) = 0 AS passed
FROM gold.fact_order_line
WHERE filled_cases > ordered_cases
UNION ALL
SELECT
  'AC-02',
  'order lines with filled_each > ordered_each',
  CAST(0 AS DOUBLE),
  CAST(count(*) AS DOUBLE),
  count(*) = 0
FROM gold.fact_order_line
WHERE filled_each > ordered_each
UNION ALL
SELECT
  'AC-02',
  'over-shipped lines whose extra quantity leaked into filled_each',
  CAST(0 AS DOUBLE),
  CAST(count(*) AS DOUBLE),
  count(*) = 0
FROM gold.fact_order_line
WHERE shipped_each > ordered_each AND filled_each <> ordered_each
