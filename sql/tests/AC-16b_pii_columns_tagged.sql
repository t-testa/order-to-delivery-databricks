-- requires: databricks
-- AC-16 (US-07): the personal data columns of silver.customers are tagged pii = true. Rule: BR-18.
SELECT
  'AC-16' AS ac_id,
  'tagged PII columns in silver.customers (email, phone)' AS check_name,
  CAST(2 AS DOUBLE) AS expected,
  CAST(count(*) AS DOUBLE) AS actual,
  count(*) = 2 AS passed
FROM information_schema.column_tags
WHERE schema_name = 'silver' AND table_name = 'customers'
  AND column_name IN ('email', 'phone') AND tag_name = 'pii' AND tag_value = 'true'
