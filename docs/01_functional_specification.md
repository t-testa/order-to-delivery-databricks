# Functional Specification: Order-to-Delivery Analytics

Project: order-to-delivery-databricks
Status: Approved for build
Author: t-testa

## 1. Purpose

Laurentia Distribution (a fictional company) ships pharmacy, medical and hardware products from three warehouses to customers across Quebec, Ontario and British Columbia. Today its two operational systems disagree with each other, and nobody can answer a basic question with confidence: **are we delivering what customers ordered, when we promised it?**

This project delivers a governed analytics layer on Databricks that:

1. Reconciles the ERP (commercial view) and the WMS (logistics view) into one trusted model.
2. Publishes agreed KPIs: fill rate, on-time delivery, OTIF, backorders, lead time and expired-lot exposure.
3. Proves every KPI with executable acceptance tests.
4. Lets business users ask questions in plain language through a Genie space.

## 2. Scope

In scope:

- Batch ingestion of CSV extracts from two source systems into a medallion model (bronze, silver, gold).
- Data quality rules, each traceable to a business rule.
- A star schema and KPI tables in the gold layer.
- Unity Catalog governance: descriptions on every table and column, tags on sensitive columns.
- SQL acceptance tests, one or more per acceptance criterion.
- A Genie space on the gold layer with benchmark questions.
- Deployment as a Databricks Asset Bundle.

Out of scope:

- Real-time or streaming ingestion from live systems (extracts are files in a Unity Catalog volume).
- Dashboards beyond the Genie space (the gold layer is dashboard-ready).
- Forecasting, route optimisation, cost-to-serve analysis.
- Real customer or product data. All data is synthetic and generated deterministically.

## 3. Stakeholders and personas

| Persona | Need |
|---|---|
| Operations manager | Fill rate by month, segment and warehouse |
| Customer service lead | On-time delivery and lead time |
| VP Supply Chain | One OTIF number everyone trusts |
| Inventory planner | Backorders and expired stock |
| Quality and compliance officer | Evidence of shipments from expired lots |
| Data steward | Reconciliation between systems, visible data quality |
| Governance lead | Described tables and columns, tagged sensitive data |
| Business user | Plain-language questions without writing SQL |

## 4. Source systems

| System | Owns (system of record) | Extract files |
|---|---|---|
| ERP | Customers, products, orders, order lines, prices, promised delivery dates, order status | `erp_customers`, `erp_products`, `erp_orders`, `erp_order_lines` |
| WMS | Shipments, shipped quantities, lots, expiry dates, ship and delivery timestamps, inventory | `wms_shipments`, `wms_shipment_lines`, `wms_lots` |

Known disagreements between the systems (all handled by business rules BR-01 to BR-05):

- Order numbers: `SO-100001` in the ERP, `SO100001`, `so100001` or `SO100001 ` in the WMS.
- Product keys: `SKU-00042` in the ERP, `42` or `00042` in the WMS.
- Warehouse codes: `WH-MTL` in the ERP, `MTL` in the WMS.
- Units of measure: the ERP orders in cases, the WMS ships in each (units).
- Timestamps: ISO 8601 in the ERP, `dd/MM/yyyy HH:mm` (occasionally `yyyy-MM-dd HH:mm`) in the WMS.
- Order status: the ERP sometimes lags behind what the WMS knows.
- The WMS re-sends some shipment lines (exact duplicates and later corrections).

## 5. User stories and acceptance criteria

Each acceptance criterion (AC) is implemented as an executable SQL test in `sql/tests/`. Expected values come from an independent reference implementation (`src/data_generation/reference.py`) so the SQL is never graded against itself.

### US-01 Fill rate
As an operations manager, I want the order fill rate by month, customer segment and warehouse, so that I can spot supply shortages early.

- **AC-01** Overall fill rate and fill rate per customer segment equal the reference values (tolerance 0.000001).
- **AC-02** No order line has filled cases above ordered cases (an over-shipment is never credited).

### US-02 On-time delivery
As a customer service lead, I want the percentage of orders delivered by the promised date, so that I can manage customer expectations.

- **AC-03** Overall on-time delivery percentage and on-time delivery percentage per warehouse equal the reference values.
- **AC-04** Orders without a promised date are excluded from the on-time denominator, and the number excluded equals the reference value.

### US-03 OTIF
As the VP Supply Chain, I want one OTIF (on time and in full) figure, so that every team works from the same number.

- **AC-05** Overall OTIF percentage and OTIF percentage per month equal the reference values.
- **AC-06** In every KPI row, OTIF orders never exceed on-time orders or in-full orders.

### US-04 Backorders and lead time
As an inventory planner, I want to see backordered lines and the order-to-delivery lead time, so that I can prioritise replenishment.

- **AC-07** Backorder line count and backorder cases equal the reference values.
- **AC-08** Average order-to-delivery lead time (days) equals the reference value.

### US-05 Expiry exposure
As a quality and compliance officer, I want to know which shipments left from expired lots and how much expired stock sits in the warehouses, so that I can act on compliance risk.

- **AC-09** The number of shipment lines and cases shipped from expired lots equals the reference values.
- **AC-10** Expired stock units and expired stock value at the snapshot date equal the reference values.

### US-06 Reconciliation and data quality
As a data steward, I want proof that the layers reconcile and that bad rows are handled by documented rules, so that I can trust the numbers.

- **AC-11** Silver row counts, after applying the data quality rules, equal the reference counts for every table.
- **AC-12** Keys are unique at the declared grain in every silver and gold table.
- **AC-13** Every foreign key in the gold facts resolves to a row in a gold dimension.
- **AC-14** The number of orders where the ERP status contradicts the WMS equals the reference value, and each is listed in `gold.dq_status_mismatch`.

### US-07 Governance
As a governance lead, I want every table and column described and sensitive columns tagged, so that data can be discovered and protected.

- **AC-15** Every silver and gold table has a description and every column has a description (checked against `information_schema`).
- **AC-16** Columns holding personal data are tagged `pii = true` in silver, and no PII column exists in gold.

### US-08 Plain-language questions
As a business user, I want to ask questions in plain language and get correct answers, so that I do not depend on an analyst for routine figures.

- **AC-17** A Genie space on the gold layer answers at least 8 of the 10 benchmark questions in `genie/benchmark_questions.md` with the reference answer. This is a manual test and the result is recorded in the README.

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | The whole project deploys from Git with one command (`databricks bundle deploy`) and runs end to end with one job. |
| NFR-02 | Data generation is deterministic: the same seed always produces the same files and the same KPI values. |
| NFR-03 | Every data quality rule is declared in the pipeline as an expectation and listed in the business rules document. |
| NFR-04 | Transformation logic can be tested without a Databricks workspace (local DuckDB emulation, run in CI). |
| NFR-05 | The project runs on Databricks Free Edition (serverless compute only). |
| NFR-06 | No personal data reaches the gold layer. |

## 7. Assumptions

- The snapshot (as-of) date is the date of the WMS lot snapshot. It is derived from the data, never from the system clock, so results are reproducible.
- All timestamps are in the warehouse's local time. No time zone conversion is applied.
- The ERP closes an order 7 days after the last delivery.

## 8. Traceability

| User story | Acceptance criteria | Business rules | Main gold objects |
|---|---|---|---|
| US-01 | AC-01, AC-02 | BR-03, BR-06, BR-07 | `fact_order_line`, `kpi_order_performance` |
| US-02 | AC-03, AC-04 | BR-04, BR-06, BR-08 | `fact_order`, `kpi_order_performance` |
| US-03 | AC-05, AC-06 | BR-09, BR-10 | `fact_order`, `kpi_order_performance` |
| US-04 | AC-07, AC-08 | BR-11, BR-12, BR-13 | `fact_order_line`, `kpi_order_performance` |
| US-05 | AC-09, AC-10 | BR-14, BR-15 | `fact_shipment_line`, `fact_inventory_lot`, `kpi_expired_lots`, `kpi_inventory_expiry` |
| US-06 | AC-11 to AC-14 | BR-01, BR-02, BR-05, BR-16, BR-17 | all silver tables, `dq_status_mismatch` |
| US-07 | AC-15, AC-16 | BR-18 | all tables |
| US-08 | AC-17 | all | all gold tables |

## 9. Revision history

| Version | Change |
|---|---|
| 1.0 | Initial specification, approved before the build. |
