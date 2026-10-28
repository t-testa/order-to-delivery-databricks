# Genie benchmark questions

Ten questions with the reference answer and the SQL that produces it. The answers are for the default seed (42). After the job runs, the live reference answers are in `qa.genie_reference`.

Both the answers and the SQL are verified by the local test suite (`tests/test_genie_benchmarks.py`), so the benchmark itself is known to be correct.

| ID | Question | Reference answer |
|---|---|---|
| Q01 | What is the overall fill rate? | 0.9624 |
| Q02 | Which customer segment has the lowest OTIF rate? | Pharmacy (0.5034) |
| Q03 | What was the on-time delivery rate for orders placed in 2026 Q1? | 0.8909 |
| Q04 | How many backordered lines were there for Pharmacy customers? | 1825 |
| Q05 | Which warehouse has the longest average order-to-delivery lead time? | VAN (2.5726 days) |
| Q06 | How many shipment lines left from expired lots? | 123 |
| Q07 | What is the value of expired stock in the Toronto warehouse? | 1604566.80 |
| Q08 | Which product category has the most backordered cases? | Prescription Pharma (2811.1 cases) |
| Q09 | Which customer has the most late orders? | Pharmacie Martin #002 (28) |
| Q10 | How many orders have an ERP status that contradicts the warehouse system? | 385 |

## Expected SQL

**Q01. What is the overall fill rate?**

```sql
SELECT sum(filled_cases) / sum(ordered_cases) AS fill_rate FROM gold.kpi_order_performance
```

**Q02. Which customer segment has the lowest OTIF rate?**

```sql
SELECT segment, sum(otif_orders) / sum(otd_eligible_orders) AS otif_pct FROM gold.kpi_order_performance GROUP BY segment ORDER BY otif_pct ASC LIMIT 1
```

**Q03. What was the on-time delivery rate for orders placed in 2026 Q1?**

```sql
SELECT sum(on_time_orders) / sum(otd_eligible_orders) AS otd_pct FROM gold.kpi_order_performance WHERE year_month IN ('2026-01', '2026-02', '2026-03')
```

**Q04. How many backordered lines were there for Pharmacy customers?**

```sql
SELECT sum(backorder_lines) AS backorder_lines FROM gold.kpi_order_performance WHERE segment = 'Pharmacy'
```

**Q05. Which warehouse has the longest average order-to-delivery lead time?**

```sql
SELECT warehouse_code, sum(lead_time_days_sum) / sum(lead_time_orders) AS avg_lead_time_days FROM gold.kpi_order_performance GROUP BY warehouse_code ORDER BY avg_lead_time_days DESC LIMIT 1
```

**Q06. How many shipment lines left from expired lots?**

```sql
SELECT sum(expired_lot_lines) AS expired_lot_lines FROM gold.kpi_expired_lots
```

**Q07. What is the value of expired stock in the Toronto warehouse?**

```sql
SELECT sum(expired_stock_value) AS expired_stock_value FROM gold.kpi_inventory_expiry WHERE warehouse_code = 'TOR'
```

**Q08. Which product category has the most backordered cases?**

```sql
SELECT p.category, sum(f.backorder_cases) AS backorder_cases FROM gold.fact_order_line f JOIN gold.dim_product p ON p.product_key = f.product_key WHERE f.is_kpi_scope GROUP BY p.category ORDER BY backorder_cases DESC LIMIT 1
```

**Q09. Which customer has the most late orders?**

```sql
SELECT c.customer_name, count(*) AS late_orders FROM gold.fact_order o JOIN gold.dim_customer c ON c.customer_id = o.customer_id WHERE o.is_kpi_scope AND o.is_on_time = false GROUP BY c.customer_name ORDER BY late_orders DESC LIMIT 1
```

**Q10. How many orders have an ERP status that contradicts the warehouse system?**

```sql
SELECT count(*) AS mismatched_orders FROM gold.dq_status_mismatch
```

## Result

| Date | Correct answers | Notes |
|---|---|---|
| to be recorded after the first Genie run | _ / 10 | |
