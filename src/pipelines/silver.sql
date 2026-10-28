-- ============================================================================
-- SILVER: cleaned and conformed.
-- Applies key harmonisation (BR-02), units (BR-03), timestamps (BR-04),
-- deduplication (BR-05) and referential integrity (BR-17).
-- Every data quality rule is a named expectation (DQ-xx, see
-- docs/02_business_rules.md). DROP ROW removes the row; an expectation with no
-- action keeps the row and records the violation in the pipeline event log.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW silver.customers (
  CONSTRAINT dq01_customer_id_not_null EXPECT (customer_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq02_email_valid EXPECT (email RLIKE '^[^@ ]+@[^@ ]+[.][^@ ]+$')
)
COMMENT 'Cleaned ERP customers. Segment and province are standardised. Email and phone are personal data (BR-18).'
AS SELECT
  nullif(trim(customer_id), '') AS customer_id,
  trim(customer_name) AS customer_name,
  CASE lower(trim(segment))
    WHEN 'pharmacy' THEN 'Pharmacy'
    WHEN 'clinic' THEN 'Clinic'
    WHEN 'hardware retail' THEN 'Hardware Retail'
    WHEN 'contractor' THEN 'Contractor'
  END AS segment,
  CASE upper(trim(province))
    WHEN 'QC' THEN 'QC' WHEN 'QUEBEC' THEN 'QC'
    WHEN 'ON' THEN 'ON' WHEN 'ONTARIO' THEN 'ON'
    WHEN 'BC' THEN 'BC' WHEN 'BRITISH COLUMBIA' THEN 'BC'
  END AS province_code,
  trim(city) AS city,
  lower(trim(email)) AS email,
  regexp_replace(phone, '[^0-9]', '') AS phone,
  try_cast(credit_limit AS DECIMAL(12,2)) AS credit_limit,
  try_cast(created_at AS DATE) AS created_date
FROM bronze.erp_customers;

CREATE OR REFRESH MATERIALIZED VIEW silver.products (
  CONSTRAINT dq03_units_per_case_positive EXPECT (units_per_case > 0) ON VIOLATION DROP ROW,
  CONSTRAINT dq04_product_key_not_null EXPECT (product_key IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Cleaned ERP products with the harmonised 5-digit product key (BR-02) and units per case (BR-03).'
AS SELECT
  lpad(nullif(regexp_extract(product_code, '([0-9]+)', 1), ''), 5, '0') AS product_key,
  trim(product_code) AS product_code,
  trim(product_name) AS product_name,
  trim(category) AS category,
  try_cast(units_per_case AS INT) AS units_per_case,
  try_cast(unit_cost AS DECIMAL(10,2)) AS unit_cost,
  try_cast(unit_price AS DECIMAL(10,2)) AS unit_price,
  try_cast(nullif(trim(shelf_life_months), '') AS INT) AS shelf_life_months,
  nullif(trim(shelf_life_months), '') IS NOT NULL AS is_expirable,
  upper(trim(status)) AS status
FROM bronze.erp_products;

CREATE OR REFRESH MATERIALIZED VIEW silver.orders (
  CONSTRAINT dq05_order_key_not_null EXPECT (order_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq06_customer_id_not_null EXPECT (customer_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq07_order_ts_valid EXPECT (order_ts IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq08_order_status_valid EXPECT (order_status IN ('OPEN', 'SHIPPED', 'CLOSED', 'CANCELLED')) ON VIOLATION DROP ROW,
  CONSTRAINT dq09_promised_date_present EXPECT (promised_delivery_date IS NOT NULL),
  CONSTRAINT dq10_promised_not_before_order EXPECT (promised_delivery_date IS NULL OR promised_delivery_date >= order_date)
)
COMMENT 'Cleaned ERP order headers. The ERP is the system of record for promised dates and order status (BR-01).'
AS SELECT
  nullif(upper(regexp_replace(trim(order_id), '[^A-Za-z0-9]', '')), '') AS order_key,
  trim(order_id) AS order_id,
  nullif(trim(customer_id), '') AS customer_id,
  try_cast(order_ts AS TIMESTAMP) AS order_ts,
  CAST(try_cast(order_ts AS TIMESTAMP) AS DATE) AS order_date,
  try_cast(requested_delivery_date AS DATE) AS requested_delivery_date,
  try_cast(promised_delivery_date AS DATE) AS promised_delivery_date,
  regexp_replace(upper(trim(warehouse_code)), '^WH-', '') AS warehouse_code,
  upper(trim(order_status)) AS order_status,
  trim(channel) AS channel
FROM bronze.erp_orders;

CREATE OR REFRESH MATERIALIZED VIEW silver.order_lines (
  CONSTRAINT dq11_ordered_qty_positive EXPECT (ordered_qty_cases > 0) ON VIOLATION DROP ROW,
  CONSTRAINT dq12_product_key_not_null EXPECT (product_key IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'Cleaned ERP order lines. Lines whose order is missing or rejected are removed (BR-17).'
AS WITH lines AS (
  SELECT
    nullif(upper(regexp_replace(trim(order_id), '[^A-Za-z0-9]', '')), '') AS order_key,
    try_cast(line_no AS INT) AS line_no,
    lpad(nullif(regexp_extract(product_code, '([0-9]+)', 1), ''), 5, '0') AS product_key,
    try_cast(ordered_qty_cases AS INT) AS ordered_qty_cases,
    try_cast(unit_price AS DECIMAL(10,2)) AS unit_price
  FROM bronze.erp_order_lines
)
SELECT
  l.order_key,
  l.line_no,
  l.product_key,
  l.ordered_qty_cases,
  l.unit_price,
  CAST(l.ordered_qty_cases * l.unit_price AS DECIMAL(14,2)) AS line_amount
FROM lines l
WHERE l.order_key IN (SELECT order_key FROM silver.orders);

CREATE OR REFRESH MATERIALIZED VIEW silver.shipments (
  CONSTRAINT dq13_shipment_id_not_null EXPECT (shipment_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq14_order_key_not_null EXPECT (order_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq15_ship_ts_valid EXPECT (ship_ts IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq16_delivered_has_timestamp EXPECT (shipment_status <> 'DELIVERED' OR delivered_ts IS NOT NULL)
)
COMMENT 'Cleaned WMS shipment headers. The WMS is the system of record for ship and delivery times (BR-01, BR-04).'
AS WITH parsed AS (
  SELECT
    nullif(trim(shipment_id), '') AS shipment_id,
    nullif(upper(regexp_replace(trim(order_ref), '[^A-Za-z0-9]', '')), '') AS order_key,
    coalesce(try_to_timestamp(ship_ts, 'dd/MM/yyyy HH:mm'), try_to_timestamp(ship_ts, 'yyyy-MM-dd HH:mm')) AS ship_ts,
    coalesce(try_to_timestamp(delivered_ts, 'dd/MM/yyyy HH:mm'), try_to_timestamp(delivered_ts, 'yyyy-MM-dd HH:mm')) AS delivered_ts,
    trim(carrier) AS carrier,
    upper(trim(shipment_status)) AS shipment_status
  FROM bronze.wms_shipments
)
SELECT
  shipment_id,
  order_key,
  ship_ts,
  CAST(ship_ts AS DATE) AS ship_date,
  delivered_ts,
  CAST(delivered_ts AS DATE) AS delivered_date,
  carrier,
  shipment_status
FROM parsed;

CREATE OR REFRESH MATERIALIZED VIEW silver.shipment_lines (
  CONSTRAINT dq17_shipped_qty_not_negative EXPECT (shipped_qty_each >= 0) ON VIOLATION DROP ROW,
  CONSTRAINT dq18_product_key_not_null EXPECT (product_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq19_lot_id_present EXPECT (lot_id IS NOT NULL)
)
COMMENT 'Cleaned WMS shipment lines, one row per shipment and line number. The latest update wins (BR-05).'
AS WITH parsed AS (
  SELECT
    nullif(trim(shipment_id), '') AS shipment_id,
    try_cast(line_no AS INT) AS line_no,
    nullif(upper(regexp_replace(trim(order_ref), '[^A-Za-z0-9]', '')), '') AS order_key,
    lpad(nullif(regexp_extract(sku, '([0-9]+)', 1), ''), 5, '0') AS product_key,
    try_cast(shipped_qty_each AS INT) AS shipped_qty_each,
    nullif(trim(lot_id), '') AS lot_id,
    try_cast(updated_at AS TIMESTAMP) AS updated_at
  FROM bronze.wms_shipment_lines
)
SELECT shipment_id, line_no, order_key, product_key, shipped_qty_each, lot_id, updated_at
FROM parsed
QUALIFY row_number() OVER (PARTITION BY shipment_id, line_no ORDER BY updated_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW silver.lots (
  CONSTRAINT dq20_lot_id_not_null EXPECT (lot_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT dq21_qty_not_negative EXPECT (qty_on_hand_each >= 0) ON VIOLATION DROP ROW,
  CONSTRAINT dq22_expiry_not_before_received EXPECT (expiry_date IS NULL OR expiry_date >= received_date)
)
COMMENT 'Cleaned WMS lots with expiry dates and the inventory snapshot. Lots without an expiry date are non-perishable (BR-14).'
AS SELECT
  nullif(trim(lot_id), '') AS lot_id,
  lpad(nullif(regexp_extract(sku, '([0-9]+)', 1), ''), 5, '0') AS product_key,
  regexp_replace(upper(trim(warehouse_code)), '^WH-', '') AS warehouse_code,
  CAST(try_to_timestamp(received_date, 'dd/MM/yyyy') AS DATE) AS received_date,
  CAST(try_to_timestamp(expiry_date, 'dd/MM/yyyy') AS DATE) AS expiry_date,
  try_cast(qty_on_hand_each AS INT) AS qty_on_hand_each,
  CAST(try_to_timestamp(snapshot_date, 'dd/MM/yyyy') AS DATE) AS snapshot_date
FROM bronze.wms_lots;
