-- ============================================================================
-- BRONZE: raw landing, no business logic.
-- One streaming table per source file, loaded with Auto Loader from the landing
-- volume. Every business column stays a STRING exactly as received.
-- Two audit columns are added: _ingested_at and _source_file.
-- Source-to-target mapping: docs/03_source_to_target_mapping.md (section 1).
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE bronze.erp_customers
COMMENT 'Raw ERP customer extract, exactly as received. All business columns are strings.'
AS SELECT
  customer_id, customer_name, segment, province, city, email, phone, credit_limit, created_at,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '${landing_path}/erp/customers/',
  format => 'csv',
  header => true,
  schema => 'customer_id STRING, customer_name STRING, segment STRING, province STRING, city STRING, email STRING, phone STRING, credit_limit STRING, created_at STRING'
);

CREATE OR REFRESH STREAMING TABLE bronze.erp_products
COMMENT 'Raw ERP product extract, exactly as received. All business columns are strings.'
AS SELECT
  product_code, product_name, category, uom, units_per_case, unit_cost, unit_price, shelf_life_months, status,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '${landing_path}/erp/products/',
  format => 'csv',
  header => true,
  schema => 'product_code STRING, product_name STRING, category STRING, uom STRING, units_per_case STRING, unit_cost STRING, unit_price STRING, shelf_life_months STRING, status STRING'
);

CREATE OR REFRESH STREAMING TABLE bronze.erp_orders
COMMENT 'Raw ERP order header extract, exactly as received. All business columns are strings.'
AS SELECT
  order_id, customer_id, order_ts, requested_delivery_date, promised_delivery_date, warehouse_code, order_status, channel,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '${landing_path}/erp/orders/',
  format => 'csv',
  header => true,
  schema => 'order_id STRING, customer_id STRING, order_ts STRING, requested_delivery_date STRING, promised_delivery_date STRING, warehouse_code STRING, order_status STRING, channel STRING'
);

CREATE OR REFRESH STREAMING TABLE bronze.erp_order_lines
COMMENT 'Raw ERP order line extract, exactly as received. All business columns are strings.'
AS SELECT
  order_id, line_no, product_code, ordered_qty_cases, unit_price,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '${landing_path}/erp/order_lines/',
  format => 'csv',
  header => true,
  schema => 'order_id STRING, line_no STRING, product_code STRING, ordered_qty_cases STRING, unit_price STRING'
);

CREATE OR REFRESH STREAMING TABLE bronze.wms_shipments
COMMENT 'Raw WMS shipment header extract, exactly as received. All business columns are strings.'
AS SELECT
  shipment_id, order_ref, ship_ts, delivered_ts, carrier, shipment_status,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '${landing_path}/wms/shipments/',
  format => 'csv',
  header => true,
  schema => 'shipment_id STRING, order_ref STRING, ship_ts STRING, delivered_ts STRING, carrier STRING, shipment_status STRING'
);

CREATE OR REFRESH STREAMING TABLE bronze.wms_shipment_lines
COMMENT 'Raw WMS shipment line extract, exactly as received, including re-sent and corrected lines. All business columns are strings.'
AS SELECT
  shipment_id, line_no, order_ref, sku, shipped_qty_each, lot_id, updated_at,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '${landing_path}/wms/shipment_lines/',
  format => 'csv',
  header => true,
  schema => 'shipment_id STRING, line_no STRING, order_ref STRING, sku STRING, shipped_qty_each STRING, lot_id STRING, updated_at STRING'
);

CREATE OR REFRESH STREAMING TABLE bronze.wms_lots
COMMENT 'Raw WMS lot and inventory snapshot extract, exactly as received. All business columns are strings.'
AS SELECT
  lot_id, sku, warehouse_code, received_date, expiry_date, qty_on_hand_each, snapshot_date,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '${landing_path}/wms/lots/',
  format => 'csv',
  header => true,
  schema => 'lot_id STRING, sku STRING, warehouse_code STRING, received_date STRING, expiry_date STRING, qty_on_hand_each STRING, snapshot_date STRING'
);
