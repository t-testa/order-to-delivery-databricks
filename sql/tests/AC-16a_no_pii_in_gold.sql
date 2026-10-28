-- AC-16 (US-07): no personal data column exists in gold. Rule: BR-18.
SELECT
  'AC-16' AS ac_id,
  'gold columns named email or phone' AS check_name,
  CAST(0 AS DOUBLE) AS expected,
  CAST(count(*) AS DOUBLE) AS actual,
  count(*) = 0 AS passed
FROM information_schema.columns
WHERE table_schema = 'gold' AND lower(column_name) IN ('email', 'phone')
