# Genie space setup

A Genie space lets business users ask questions about the gold layer in plain language. This file holds everything to paste into the space so the setup is reproducible.

## 1. Create the space

1. In Databricks, open **Genie** and select **New**.
2. Title: `Order-to-delivery analytics`.
3. Default warehouse: the serverless starter warehouse.
4. Add these tables from the `gold` schema of your catalog (default `o2d`):
   `kpi_order_performance`, `kpi_expired_lots`, `kpi_inventory_expiry`, `fact_order`, `fact_order_line`, `fact_shipment_line`, `fact_inventory_lot`, `dq_status_mismatch`, `dim_customer`, `dim_product`, `dim_warehouse`, `dim_date`.

## 2. Description (paste into the space description)

Order fulfilment analytics for Laurentia Distribution, a fictional distributor of pharmacy, medical and hardware products shipping from three warehouses (MTL Montreal, TOR Toronto, VAN Vancouver). Data is synthetic. Order KPIs cover closed orders only. All money is in CAD.

## 3. General instructions (paste into Instructions, Text)

```
KPI definitions. Always use these formulas and always re-aggregate numerators and denominators. Never average a percentage column.
- Fill rate = sum(filled_cases) / sum(ordered_cases).
- On-time delivery % (OTD) = sum(on_time_orders) / sum(otd_eligible_orders).
- In-full % = sum(in_full_orders) / sum(orders).
- OTIF % = sum(otif_orders) / sum(otd_eligible_orders).
- Average lead time in days = sum(lead_time_days_sum) / sum(lead_time_orders).
- Backorders: backorder_lines and backorder_cases.

Where to look.
- Order KPIs by month, segment or warehouse: gold.kpi_order_performance. It is already limited to closed orders. year_month is the order month in yyyy-MM format. Quarter 1 means months 01, 02 and 03.
- For questions by customer, product or category, use gold.fact_order or gold.fact_order_line with is_kpi_scope = true, joined to the dimensions.
- Shipments from expired lots: gold.kpi_expired_lots (expired_lot_lines, expired_lot_cases).
- Expired stock: gold.kpi_inventory_expiry (expired_units, expired_stock_value).
- Orders whose ERP status contradicts the warehouse system: gold.dq_status_mismatch.

Joins.
- fact_order.customer_id = dim_customer.customer_id
- fact_order_line.product_key = dim_product.product_key
- fact_order_line.order_id = fact_order.order_id
- fact_shipment_line.product_key = dim_product.product_key
- fact_inventory_lot.product_key = dim_product.product_key
- date keys are integers yyyyMMdd and join to dim_date.date_key

Vocabulary. Segments: Pharmacy, Clinic, Hardware Retail, Contractor. Warehouse codes: MTL, TOR, VAN. "Late order" means is_on_time = false. "Shortage" and "stock-out" mean backordered. Respond with the number and a one-line interpretation.

Ranking questions. When a question asks "which" item has the most, least, highest, lowest or longest, return exactly one row (LIMIT 1) containing only the item name and the measure. Do not add extra columns and do not return a top 10 unless the user asks for a top N or a list.
```

## 4. Sample questions (add as sample questions on the space)

- What is the overall fill rate?
- Show OTIF by customer segment.
- Which warehouse has the lowest on-time delivery?
- How many orders were delivered late each month?
- How much expired stock do we hold by warehouse?

## 5. Benchmarks

Add the 10 questions from `benchmark.csv` as benchmarks (each has the expected SQL; write table names as `o2d.gold.<table>` so they resolve in the benchmark), run the benchmark, and record the score in the README. Acceptance criterion AC-17 requires at least 8 of 10 correct. The reference answers are in `benchmark_questions.md`, and the live values are stored in the table `qa.genie_reference` after the job has run.
