# Source-to-Target Mapping

Notation: `bronze` columns are all strings, exactly as received. `silver` applies the harmonisation rules (BR-02 to BR-05) and the data quality rules (DQ-xx). `gold` is the star schema and KPI layer.

## 1. Bronze (raw landing, no business logic)

One streaming table per source file, loaded with Auto Loader (`read_files`) from the landing volume. Two audit columns are added to every table: `_ingested_at` (load timestamp) and `_source_file` (file path).

| Bronze table | Source file | Columns (all STRING) |
|---|---|---|
| `bronze.erp_customers` | ERP | customer_id, customer_name, segment, province, city, email, phone, credit_limit, created_at |
| `bronze.erp_products` | ERP | product_code, product_name, category, uom, units_per_case, unit_cost, unit_price, shelf_life_months, status |
| `bronze.erp_orders` | ERP | order_id, customer_id, order_ts, requested_delivery_date, promised_delivery_date, warehouse_code, order_status, channel |
| `bronze.erp_order_lines` | ERP | order_id, line_no, product_code, ordered_qty_cases, unit_price |
| `bronze.wms_shipments` | WMS | shipment_id, order_ref, ship_ts, delivered_ts, carrier, shipment_status |
| `bronze.wms_shipment_lines` | WMS | shipment_id, line_no, order_ref, sku, shipped_qty_each, lot_id, updated_at |
| `bronze.wms_lots` | WMS | lot_id, sku, warehouse_code, received_date, expiry_date, qty_on_hand_each, snapshot_date |

## 2. Silver (clean and conformed)

### silver.customers (from bronze.erp_customers)
| Target | Rule |
|---|---|
| customer_id | trim; DQ-01 |
| customer_name | trim |
| segment | map case-insensitively to Pharmacy, Clinic, Hardware Retail, Contractor |
| province_code | map QC/Quebec, ON/Ontario, BC/British Columbia to the 2-letter code |
| city | trim |
| email | lower, trim; DQ-02; PII (BR-18) |
| phone | digits only; PII (BR-18) |
| credit_limit | cast to DECIMAL(12,2) |
| created_date | cast to DATE |

### silver.products (from bronze.erp_products)
| Target | Rule |
|---|---|
| product_key | BR-02 on `product_code`; DQ-04 |
| product_code | as received (trim) |
| product_name, category | trim |
| units_per_case | cast to INT; DQ-03 |
| unit_cost, unit_price | cast to DECIMAL(10,2) |
| shelf_life_months | cast to INT, NULL for non-perishable |
| is_expirable | `shelf_life_months IS NOT NULL` |
| status | upper, trim |

### silver.orders (from bronze.erp_orders)
| Target | Rule |
|---|---|
| order_key | BR-02 on `order_id`; DQ-05 |
| order_id | trim |
| customer_id | trim; DQ-06 |
| order_ts, order_date | parse ISO timestamp; DQ-07; date part |
| requested_delivery_date, promised_delivery_date | cast to DATE; DQ-09, DQ-10 |
| warehouse_code | BR-02 |
| order_status | upper, trim; DQ-08 |
| channel | trim |

### silver.order_lines (from bronze.erp_order_lines)
| Target | Rule |
|---|---|
| order_key | BR-02; kept only if the order exists in `silver.orders` (BR-17) |
| line_no | cast to INT |
| product_key | BR-02 on `product_code`; DQ-12 |
| ordered_qty_cases | cast to INT; DQ-11 |
| unit_price | cast to DECIMAL(10,2) |
| line_amount | `ordered_qty_cases * unit_price` |

### silver.shipments (from bronze.wms_shipments)
| Target | Rule |
|---|---|
| shipment_id | trim; DQ-13 |
| order_key | BR-02 on `order_ref`; DQ-14 |
| ship_ts, ship_date | BR-04; DQ-15 |
| delivered_ts, delivered_date | BR-04; DQ-16 |
| carrier | trim |
| shipment_status | upper, trim |

### silver.shipment_lines (from bronze.wms_shipment_lines)
| Target | Rule |
|---|---|
| shipment_id, line_no | key; BR-05 keeps the latest `updated_at` per key |
| order_key | BR-02 on `order_ref` |
| product_key | BR-02 on `sku`; DQ-18 |
| shipped_qty_each | cast to INT; DQ-17 |
| lot_id | trim; DQ-19 |
| updated_at | parse timestamp |

### silver.lots (from bronze.wms_lots)
| Target | Rule |
|---|---|
| lot_id | trim; DQ-20 |
| product_key | BR-02 on `sku` |
| warehouse_code | BR-02 |
| received_date, expiry_date | BR-04 (date format `dd/MM/yyyy`); DQ-22 |
| qty_on_hand_each | cast to INT; DQ-21 |
| snapshot_date | BR-04 |

## 3. Gold (star schema and KPIs)

### Dimensions
| Table | Grain | Source and rule |
|---|---|---|
| gold.dim_date | one row per calendar day | all dates present in silver, filled to a contiguous range |
| gold.dim_customer | customer | silver.customers without email and phone (BR-18) |
| gold.dim_product | product | silver.products |
| gold.dim_warehouse | warehouse | MTL, TOR, VAN reference list |

### Facts
| Table | Grain | Rule |
|---|---|---|
| gold.fact_order_line | order line | silver.order_lines + cumulative shipped each from silver.shipment_lines (BR-03, BR-05) + delivered-by-promise each (BR-10); filled (BR-07), backorder (BR-11), over-shipment (BR-12) |
| gold.fact_order | order | aggregated from fact_order_line plus first and last delivery dates; flags is_kpi_scope (BR-06), is_on_time (BR-08), is_in_full (BR-09), is_otif (BR-10); lead time (BR-13) |
| gold.fact_shipment_line | shipment line | silver.shipment_lines + lot expiry; `is_expired_lot_shipped` (BR-14) |
| gold.fact_inventory_lot | lot at snapshot | silver.lots + product cost; `is_expired` and expired value (BR-15) |

### KPI tables and views
| Table | Grain | Content |
|---|---|---|
| gold.kpi_order_performance | year_month x segment x warehouse | numerators, denominators and ratios for fill rate, OTD, in-full, OTIF; backorders; lead time |
| gold.kpi_expired_lots | year_month x warehouse x category | shipment lines and cases from expired lots |
| gold.kpi_inventory_expiry | warehouse x category | stock and expired stock units and value |
| gold.dq_status_mismatch | order | orders where the ERP status contradicts the WMS (BR-16) |

Ratios in KPI tables are always stored together with their numerator and denominator so that they can be re-aggregated correctly at any level.
