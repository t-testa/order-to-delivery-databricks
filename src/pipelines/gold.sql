-- ============================================================================
-- GOLD: star schema and KPIs.
-- Business rules BR-03 and BR-06 to BR-16 (docs/02_business_rules.md).
-- Quantities are compared in each (integers); cases are for reporting only.
-- No personal data (email, phone) is carried into gold (BR-18).
-- ============================================================================

-- ---------------------------------------------------------------- dimensions

CREATE OR REFRESH MATERIALIZED VIEW gold.dim_date
COMMENT 'Calendar dimension, one row per day, contiguous from the first to the last business date in the data.'
AS WITH bounds AS (
  SELECT min(d) AS d_min, max(d) AS d_max
  FROM (
    SELECT order_date AS d FROM silver.orders
    UNION ALL SELECT promised_delivery_date FROM silver.orders
    UNION ALL SELECT ship_date FROM silver.shipments
    UNION ALL SELECT delivered_date FROM silver.shipments
    UNION ALL SELECT snapshot_date FROM silver.lots
  )
),
days AS (
  SELECT explode(sequence(d_min, d_max, INTERVAL 1 DAY)) AS full_date FROM bounds
)
SELECT
  CAST(date_format(full_date, 'yyyyMMdd') AS INT) AS date_key,
  full_date,
  year(full_date) AS year,
  quarter(full_date) AS quarter,
  month(full_date) AS month,
  date_format(full_date, 'MMMM') AS month_name,
  date_format(full_date, 'yyyy-MM') AS year_month,
  date_format(full_date, 'EEE') AS day_name,
  date_format(full_date, 'EEE') IN ('Sat', 'Sun') AS is_weekend
FROM days;

CREATE OR REFRESH MATERIALIZED VIEW gold.dim_customer
COMMENT 'Customer dimension. Email and phone are deliberately excluded because they are personal data (BR-18).'
AS SELECT
  customer_id, customer_name, segment, province_code, city, credit_limit
FROM silver.customers;

CREATE OR REFRESH MATERIALIZED VIEW gold.dim_product
COMMENT 'Product dimension with units per case, cost, price and perishability.'
AS SELECT
  product_key, product_code, product_name, category, units_per_case, unit_cost, unit_price, is_expirable, status
FROM silver.products;

CREATE OR REFRESH MATERIALIZED VIEW gold.dim_warehouse
COMMENT 'Warehouse dimension (reference list of the three distribution centres).'
AS SELECT * FROM VALUES
  ('MTL', 'Montreal Distribution Centre', 'QC'),
  ('TOR', 'Toronto Distribution Centre', 'ON'),
  ('VAN', 'Vancouver Distribution Centre', 'BC')
AS w(warehouse_code, warehouse_name, province_code);

-- --------------------------------------------------------------------- facts

CREATE OR REFRESH MATERIALIZED VIEW gold.fact_order_line
COMMENT 'One row per order line with cumulative shipped quantity, fill, backorder and over-shipment measures (BR-03, BR-07, BR-10 to BR-12).'
AS WITH shipped AS (
  SELECT order_key, line_no, sum(shipped_qty_each) AS shipped_each
  FROM silver.shipment_lines
  GROUP BY order_key, line_no
),
by_promise AS (
  SELECT sl.order_key, sl.line_no, sum(sl.shipped_qty_each) AS delivered_by_promise_each
  FROM silver.shipment_lines sl
  JOIN silver.shipments s ON s.shipment_id = sl.shipment_id
  JOIN silver.orders o ON o.order_key = sl.order_key
  WHERE s.delivered_date IS NOT NULL
    AND o.promised_delivery_date IS NOT NULL
    AND s.delivered_date <= o.promised_delivery_date
  GROUP BY sl.order_key, sl.line_no
),
base AS (
  SELECT
    o.order_id,
    ol.order_key,
    ol.line_no,
    ol.product_key,
    o.customer_id,
    o.warehouse_code,
    o.order_status,
    CAST(date_format(o.order_date, 'yyyyMMdd') AS INT) AS order_date_key,
    CAST(date_format(o.promised_delivery_date, 'yyyyMMdd') AS INT) AS promised_date_key,
    p.units_per_case,
    ol.ordered_qty_cases * p.units_per_case AS ordered_each,
    coalesce(s.shipped_each, 0) AS shipped_each,
    coalesce(bp.delivered_by_promise_each, 0) AS delivered_by_promise_each,
    ol.line_amount
  FROM silver.order_lines ol
  JOIN silver.orders o ON o.order_key = ol.order_key
  JOIN silver.products p ON p.product_key = ol.product_key
  LEFT JOIN shipped s ON s.order_key = ol.order_key AND s.line_no = ol.line_no
  LEFT JOIN by_promise bp ON bp.order_key = ol.order_key AND bp.line_no = ol.line_no
),
calc AS (
  SELECT *, least(shipped_each, ordered_each) AS filled_each
  FROM base
)
SELECT
  order_id,
  order_key,
  line_no,
  product_key,
  customer_id,
  warehouse_code,
  order_status,
  order_date_key,
  promised_date_key,
  units_per_case,
  ordered_each,
  shipped_each,
  delivered_by_promise_each,
  filled_each,
  ordered_each / units_per_case AS ordered_cases,
  shipped_each / units_per_case AS shipped_cases,
  filled_each / units_per_case AS filled_cases,
  greatest(shipped_each - ordered_each, 0) / units_per_case AS over_shipped_cases,
  (ordered_each - filled_each) / units_per_case AS backorder_cases,
  shipped_each < ordered_each AS is_backordered,
  shipped_each >= ordered_each AS is_in_full,
  delivered_by_promise_each >= ordered_each AS is_in_full_by_promise,
  line_amount,
  order_status = 'CLOSED' AS is_kpi_scope
FROM calc;

CREATE OR REFRESH MATERIALIZED VIEW gold.fact_order
COMMENT 'One row per order with delivery dates, lead time and the on-time, in-full and OTIF flags (BR-06, BR-08 to BR-10, BR-13).'
AS WITH deliveries AS (
  SELECT
    order_key,
    min(delivered_date) AS first_delivered_date,
    max(delivered_date) AS last_delivered_date
  FROM silver.shipments
  WHERE delivered_date IS NOT NULL
  GROUP BY order_key
),
agg AS (
  SELECT
    order_id,
    order_key,
    customer_id,
    warehouse_code,
    order_status,
    count(*) AS line_count,
    sum(ordered_cases) AS ordered_cases,
    sum(shipped_cases) AS shipped_cases,
    sum(filled_cases) AS filled_cases,
    sum(CASE WHEN is_backordered THEN 1 ELSE 0 END) AS backorder_lines,
    sum(backorder_cases) AS backorder_cases,
    sum(line_amount) AS order_amount,
    bool_and(is_in_full) AS is_in_full,
    bool_and(is_in_full_by_promise) AS is_in_full_by_promise
  FROM gold.fact_order_line
  GROUP BY order_id, order_key, customer_id, warehouse_code, order_status
)
SELECT
  a.order_id,
  a.order_key,
  a.customer_id,
  a.warehouse_code,
  a.order_status,
  o.order_date,
  o.promised_delivery_date AS promised_date,
  d.first_delivered_date,
  d.last_delivered_date,
  CAST(date_format(o.order_date, 'yyyyMMdd') AS INT) AS order_date_key,
  CAST(date_format(o.promised_delivery_date, 'yyyyMMdd') AS INT) AS promised_date_key,
  CAST(date_format(d.first_delivered_date, 'yyyyMMdd') AS INT) AS first_delivered_date_key,
  CAST(date_format(d.last_delivered_date, 'yyyyMMdd') AS INT) AS last_delivered_date_key,
  a.line_count,
  a.ordered_cases,
  a.shipped_cases,
  a.filled_cases,
  a.backorder_lines,
  a.backorder_cases,
  a.order_amount,
  datediff(d.first_delivered_date, o.order_date) AS lead_time_days,
  a.order_status = 'CLOSED' AS is_kpi_scope,
  CASE WHEN o.promised_delivery_date IS NULL THEN NULL
       ELSE coalesce(d.first_delivered_date <= o.promised_delivery_date, false) END AS is_on_time,
  a.is_in_full,
  CASE WHEN o.promised_delivery_date IS NULL THEN NULL
       ELSE a.is_in_full_by_promise END AS is_otif
FROM agg a
JOIN silver.orders o ON o.order_key = a.order_key
LEFT JOIN deliveries d ON d.order_key = a.order_key;

CREATE OR REFRESH MATERIALIZED VIEW gold.fact_shipment_line
COMMENT 'One row per shipment line with the lot expiry check. Includes shipments of unknown orders because the compliance risk exists anyway (BR-14, BR-17).'
AS SELECT
  sl.shipment_id,
  sl.line_no,
  sl.order_key,
  sl.product_key,
  sl.lot_id,
  l.warehouse_code,
  s.ship_date,
  CAST(date_format(s.ship_date, 'yyyyMMdd') AS INT) AS ship_date_key,
  CAST(date_format(s.delivered_date, 'yyyyMMdd') AS INT) AS delivered_date_key,
  l.expiry_date AS lot_expiry_date,
  sl.shipped_qty_each AS shipped_each,
  sl.shipped_qty_each / p.units_per_case AS shipped_cases,
  coalesce(l.expiry_date < s.ship_date, false) AS is_expired_lot_shipped
FROM silver.shipment_lines sl
LEFT JOIN silver.shipments s ON s.shipment_id = sl.shipment_id
LEFT JOIN silver.lots l ON l.lot_id = sl.lot_id
LEFT JOIN silver.products p ON p.product_key = sl.product_key;

CREATE OR REFRESH MATERIALIZED VIEW gold.fact_inventory_lot
COMMENT 'One row per lot at the snapshot date with stock, stock value and expiry status (BR-15).'
AS SELECT
  l.lot_id,
  l.product_key,
  l.warehouse_code,
  CAST(date_format(l.snapshot_date, 'yyyyMMdd') AS INT) AS snapshot_date_key,
  l.received_date,
  l.expiry_date,
  l.qty_on_hand_each,
  l.qty_on_hand_each / p.units_per_case AS qty_on_hand_cases,
  l.qty_on_hand_each * p.unit_cost AS stock_value,
  coalesce(l.expiry_date < l.snapshot_date, false) AS is_expired,
  CASE WHEN coalesce(l.expiry_date < l.snapshot_date, false) THEN l.qty_on_hand_each ELSE 0 END AS expired_qty_each,
  CASE WHEN coalesce(l.expiry_date < l.snapshot_date, false) THEN l.qty_on_hand_each * p.unit_cost ELSE 0 END AS expired_stock_value
FROM silver.lots l
LEFT JOIN silver.products p ON p.product_key = l.product_key;

-- ----------------------------------------------------------------------- KPIs

CREATE OR REFRESH MATERIALIZED VIEW gold.kpi_order_performance
COMMENT 'Order KPIs by order month, customer segment and warehouse for closed orders. Numerators and denominators are stored with the ratios so they can be re-aggregated (BR-06 to BR-13).'
AS SELECT
  date_format(o.order_date, 'yyyy-MM') AS year_month,
  c.segment,
  o.warehouse_code,
  count(*) AS orders,
  count(o.is_on_time) AS otd_eligible_orders,
  count_if(o.is_on_time) AS on_time_orders,
  count_if(o.is_in_full) AS in_full_orders,
  count_if(o.is_otif) AS otif_orders,
  sum(o.ordered_cases) AS ordered_cases,
  sum(o.filled_cases) AS filled_cases,
  sum(o.backorder_lines) AS backorder_lines,
  sum(o.backorder_cases) AS backorder_cases,
  sum(o.lead_time_days) AS lead_time_days_sum,
  count(o.lead_time_days) AS lead_time_orders,
  sum(o.filled_cases) / sum(o.ordered_cases) AS fill_rate,
  try_divide(count_if(o.is_on_time), count(o.is_on_time)) AS otd_pct,
  count_if(o.is_in_full) / count(*) AS in_full_pct,
  try_divide(count_if(o.is_otif), count(o.is_on_time)) AS otif_pct,
  try_divide(sum(o.lead_time_days), count(o.lead_time_days)) AS avg_lead_time_days
FROM gold.fact_order o
JOIN gold.dim_customer c ON c.customer_id = o.customer_id
WHERE o.is_kpi_scope
GROUP BY date_format(o.order_date, 'yyyy-MM'), c.segment, o.warehouse_code;

CREATE OR REFRESH MATERIALIZED VIEW gold.kpi_expired_lots
COMMENT 'Shipment lines and cases that left from expired lots, by ship month, warehouse and product category (BR-14).'
AS SELECT
  date_format(f.ship_date, 'yyyy-MM') AS year_month,
  f.warehouse_code,
  p.category,
  count(*) AS shipment_lines,
  count_if(f.is_expired_lot_shipped) AS expired_lot_lines,
  sum(f.shipped_cases) AS shipped_cases,
  sum(CASE WHEN f.is_expired_lot_shipped THEN f.shipped_cases ELSE 0 END) AS expired_lot_cases
FROM gold.fact_shipment_line f
LEFT JOIN gold.dim_product p ON p.product_key = f.product_key
GROUP BY date_format(f.ship_date, 'yyyy-MM'), f.warehouse_code, p.category;

CREATE OR REFRESH MATERIALIZED VIEW gold.kpi_inventory_expiry
COMMENT 'Stock and expired stock at the snapshot date, by warehouse and product category (BR-15).'
AS SELECT
  i.warehouse_code,
  p.category,
  count(*) AS lots,
  count_if(i.is_expired) AS expired_lots,
  sum(i.qty_on_hand_each) AS stock_units,
  sum(i.expired_qty_each) AS expired_units,
  sum(i.stock_value) AS stock_value,
  sum(i.expired_stock_value) AS expired_stock_value,
  try_divide(sum(i.expired_stock_value), sum(i.stock_value)) AS expired_value_pct
FROM gold.fact_inventory_lot i
LEFT JOIN gold.dim_product p ON p.product_key = i.product_key
GROUP BY i.warehouse_code, p.category;

CREATE OR REFRESH MATERIALIZED VIEW gold.dq_status_mismatch
COMMENT 'Orders whose ERP status contradicts the WMS: every shipment is delivered and the last delivery is at least 7 days old, yet the ERP has not closed the order (BR-16).'
AS WITH ship AS (
  SELECT
    order_key,
    count(*) AS shipments,
    count(delivered_date) AS delivered_shipments,
    max(delivered_date) AS last_delivered_date
  FROM silver.shipments
  GROUP BY order_key
),
snap AS (
  SELECT max(snapshot_date) AS snapshot_date FROM silver.lots
)
SELECT
  o.order_id,
  o.order_status AS erp_status,
  s.shipments,
  s.last_delivered_date,
  snap.snapshot_date,
  datediff(snap.snapshot_date, s.last_delivered_date) AS days_since_last_delivery
FROM silver.orders o
JOIN ship s ON s.order_key = o.order_key
CROSS JOIN snap
WHERE o.order_status NOT IN ('CLOSED', 'CANCELLED')
  AND s.shipments = s.delivered_shipments
  AND datediff(snap.snapshot_date, s.last_delivered_date) >= 7;
