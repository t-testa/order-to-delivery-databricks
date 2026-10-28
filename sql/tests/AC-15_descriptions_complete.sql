-- requires: databricks
-- AC-15 (US-07): every silver and gold table and every column has a description. Rule: BR-18 and governance NFR.
SELECT
  'AC-15' AS ac_id,
  'silver and gold tables without a description' AS check_name,
  CAST(0 AS DOUBLE) AS expected,
  CAST(count(*) AS DOUBLE) AS actual,
  count(*) = 0 AS passed
FROM information_schema.tables
WHERE table_schema IN ('silver', 'gold') AND (comment IS NULL OR trim(comment) = '')
UNION ALL
SELECT
  'AC-15',
  'silver and gold columns without a description',
  CAST(0 AS DOUBLE),
  CAST(count(*) AS DOUBLE),
  count(*) = 0
FROM information_schema.columns
WHERE table_schema IN ('silver', 'gold') AND (comment IS NULL OR trim(comment) = '')
