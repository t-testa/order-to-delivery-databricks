# Business Rules and Data Quality Rules

Every rule has an ID. The pipeline code, the acceptance tests and the data dictionary refer to these IDs.

## 1. Business rules

### BR-01 System of record
The ERP owns commercial facts: customers, products, orders, order lines, prices, promised delivery dates and order status. The WMS owns logistics facts: shipments, shipped quantities, lots, expiry dates, and ship and delivery timestamps. When the two disagree, the owning system wins.

### BR-02 Key harmonisation
- `order_key` = the order number with every character that is not a letter or digit removed, in upper case. `SO-100001`, `SO100001` and `so100001 ` all become `SO100001`.
- `product_key` = the digits of the product code or SKU, left-padded with zeros to 5 characters. `SKU-00042`, `42` and `00042` all become `00042`.
- `warehouse_code` = the warehouse code in upper case without the `WH-` prefix. `WH-MTL` and `MTL` both become `MTL`.

### BR-03 Unit of measure
The ERP orders in cases. The WMS ships and counts stock in each (single units). `cases = each / units_per_case`, where `units_per_case` comes from the ERP product. All quantity comparisons are made in each (integers) to avoid rounding issues. Cases are used only for reporting.

### BR-04 Timestamp harmonisation
WMS timestamps arrive as `dd/MM/yyyy HH:mm` or, for a small share of rows, `yyyy-MM-dd HH:mm`. Both formats are accepted. A value that matches neither becomes NULL. The ship date and delivery date are the date part of the timestamp.

### BR-05 Shipment line deduplication
The WMS re-sends lines. There is one row per (`shipment_id`, `line_no`). When several rows exist, the one with the latest `updated_at` wins.

### BR-06 KPI scope
Order KPIs (fill rate, on-time, in-full, OTIF, backorders, lead time) cover orders whose ERP status is `CLOSED` and that have at least one valid order line. Orders that are open, shipped but not closed, or cancelled are excluded because their outcome is not final yet.

### BR-07 Fill rate
Per line: `filled = least(shipped, ordered)`, using cumulative shipped quantity across all shipments of the order. Over-shipments are not credited.
Fill rate = sum(filled cases) / sum(ordered cases) over in-scope lines.

### BR-08 On-time delivery (OTD)
An order is on time when its first delivery date is on or before its promised delivery date. An order with no promised date is not eligible: it is excluded from the numerator and the denominator. An order with no delivery is not on time.
OTD % = on-time orders / eligible orders.

### BR-09 In full
An order is in full when every line has cumulative shipped each greater than or equal to ordered each, regardless of timing.
In-full % = in-full orders / in-scope orders.

### BR-10 OTIF (on time and in full)
An order is OTIF when it has a promised date and every line had at least its ordered quantity delivered on or before the promised date. Quantity delivered after the promised date does not count.
OTIF % = OTIF orders / eligible orders.
By construction an OTIF order is also on time and in full. Acceptance test AC-06 checks this invariant.

### BR-11 Backorder
A line of an in-scope order with shipped < ordered is a backordered line. Backorder cases = ordered cases minus filled cases. Remaining quantity of a closed order is considered cancelled by the ERP, so it is a permanent shortage.

### BR-12 Over-shipment
A line with shipped > ordered is flagged `over_shipped_cases = (shipped - ordered) / units_per_case`. The extra quantity is not credited to the fill rate (BR-07).

### BR-13 Order-to-delivery lead time
Calendar days between the order date and the first delivery date. The average is taken over in-scope orders that have a delivery.

### BR-14 Expired-lot shipment (compliance)
A shipment line is an expired-lot shipment when the lot has an expiry date and the expiry date is earlier than the ship date. Lots without an expiry date (non-perishable goods) are never expired. This rule applies to every valid shipment line, including shipments whose order is unknown, because the compliance risk exists regardless.

### BR-15 Expired stock
At the snapshot date, a lot is expired when its expiry date is earlier than the snapshot date. Expired stock units = sum of on-hand each in expired lots. Expired stock value = on-hand each x unit cost.

### BR-16 Status reconciliation
An order is reported in `gold.dq_status_mismatch` when the ERP status is neither `CLOSED` nor `CANCELLED`, all its shipments are delivered in the WMS, and the last delivery is at least 7 days before the snapshot date. These orders stay out of the KPI scope (BR-06) until the ERP is corrected, and the finding is visible to the data steward.

### BR-17 Referential integrity
- An ERP order without a customer is rejected.
- An order line whose order is missing or rejected is rejected.
- A WMS shipment whose order is unknown is kept in silver (it is a real shipment) but is excluded from order KPIs. It is still included in compliance KPIs (BR-14).
- An order without any valid line does not appear in `fact_order`.

### BR-18 Personal data
Customer email and phone are personal data. They are tagged `pii = true` in silver and are not carried into gold.

## 2. Data quality rules

Actions: **DROP** removes the row from the table, **WARN** keeps the row and records the violation in the pipeline event log, **FAIL** stops the pipeline update.

| ID | Table (silver) | Rule | Action | Linked rule |
|---|---|---|---|---|
| DQ-01 | customers | `customer_id` is not null | DROP | BR-17 |
| DQ-02 | customers | `email` has a valid format | WARN | BR-18 |
| DQ-03 | products | `units_per_case` > 0 | DROP | BR-03 |
| DQ-04 | products | `product_key` is not null | DROP | BR-02 |
| DQ-05 | orders | `order_key` is not null | DROP | BR-02 |
| DQ-06 | orders | `customer_id` is not null | DROP | BR-17 |
| DQ-07 | orders | `order_ts` is a valid timestamp | DROP | BR-04 |
| DQ-08 | orders | `order_status` is OPEN, SHIPPED, CLOSED or CANCELLED | DROP | BR-06 |
| DQ-09 | orders | `promised_delivery_date` is not null | WARN | BR-08 |
| DQ-10 | orders | `promised_delivery_date` >= `order_date` | WARN | BR-08 |
| DQ-11 | order_lines | `ordered_qty_cases` > 0 | DROP | BR-03 |
| DQ-12 | order_lines | `product_key` is not null | DROP | BR-02 |
| DQ-13 | shipments | `shipment_id` is not null | DROP | BR-05 |
| DQ-14 | shipments | `order_key` is not null | DROP | BR-02 |
| DQ-15 | shipments | `ship_ts` is a valid timestamp | DROP | BR-04 |
| DQ-16 | shipments | a DELIVERED shipment has a `delivered_ts` | WARN | BR-08 |
| DQ-17 | shipment_lines | `shipped_qty_each` >= 0 | DROP | BR-03 |
| DQ-18 | shipment_lines | `product_key` is not null | DROP | BR-02 |
| DQ-19 | shipment_lines | `lot_id` is not null | WARN | BR-14 |
| DQ-20 | lots | `lot_id` is not null | DROP | BR-14 |
| DQ-21 | lots | `qty_on_hand_each` >= 0 | DROP | BR-15 |
| DQ-22 | lots | `expiry_date` >= `received_date` | WARN | BR-14 |

Each rule is declared in `src/pipelines/silver.sql` as a named `CONSTRAINT ... EXPECT` using the same ID, so the pipeline event log shows pass and fail counts per rule.
