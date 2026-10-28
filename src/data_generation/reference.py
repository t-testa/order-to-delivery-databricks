"""Independent reference implementation of the silver rules and gold KPIs.

This module reads the raw landing files with pandas and recomputes every figure
that the SQL acceptance tests check. It deliberately shares no code with the
SQL pipeline, so when the two agree it is real evidence, not a tautology.

Business rule IDs (BR-xx) refer to docs/02_business_rules.md.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd

CLOSE_LAG_DAYS = 7
VALID_STATUSES = {"OPEN", "SHIPPED", "CLOSED", "CANCELLED"}


# --------------------------------------------------------------------------
# Reading and harmonisation (BR-02, BR-04)
# --------------------------------------------------------------------------
def _read(landing_dir: str, rel_path: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(landing_dir, rel_path), dtype=str, keep_default_na=False)
    return df.apply(lambda col: col.str.strip())


def _blank_to_na(s: pd.Series) -> pd.Series:
    return s.where(s != "", other=pd.NA)


def order_key(s: pd.Series) -> pd.Series:
    return _blank_to_na(s.str.replace(r"[^A-Za-z0-9]", "", regex=True).str.upper())


def product_key(s: pd.Series) -> pd.Series:
    return s.str.extract(r"([0-9]+)", expand=False).str.zfill(5)


def warehouse(s: pd.Series) -> pd.Series:
    return s.str.upper().str.replace(r"^WH-", "", regex=True)


def wms_timestamp(s: pd.Series) -> pd.Series:
    a = pd.to_datetime(s, format="%d/%m/%Y %H:%M", errors="coerce")
    b = pd.to_datetime(s, format="%Y-%m-%d %H:%M", errors="coerce")
    return a.fillna(b)


def wms_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")


# --------------------------------------------------------------------------
# Silver (BR-05, BR-17 and the DQ rules)
# --------------------------------------------------------------------------
def build_silver(landing_dir: str) -> dict:
    cust = _read(landing_dir, "erp/customers/customers.csv")
    silver_customers = cust[cust["customer_id"] != ""].copy()
    silver_customers["segment"] = silver_customers["segment"].str.lower().map(
        {"pharmacy": "Pharmacy", "clinic": "Clinic", "hardware retail": "Hardware Retail",
         "contractor": "Contractor"})
    silver_customers["credit_limit"] = silver_customers["credit_limit"].astype(float)

    prod = _read(landing_dir, "erp/products/products.csv")
    prod["product_key"] = product_key(prod["product_code"])
    prod["units_per_case"] = pd.to_numeric(prod["units_per_case"], errors="coerce")
    prod["unit_cost"] = prod["unit_cost"].astype(float)
    silver_products = prod[prod["product_key"].notna() & (prod["units_per_case"] > 0)].copy()

    orders = _read(landing_dir, "erp/orders/orders.csv")
    orders["order_key"] = order_key(orders["order_id"])
    orders["order_ts"] = pd.to_datetime(orders["order_ts"], format="%Y-%m-%dT%H:%M:%S", errors="coerce")
    orders["order_date"] = orders["order_ts"].dt.normalize()
    orders["promised"] = pd.to_datetime(orders["promised_delivery_date"], format="%Y-%m-%d", errors="coerce")
    orders["warehouse"] = warehouse(orders["warehouse_code"])
    orders["status"] = orders["order_status"].str.upper()
    keep = (orders["order_key"].notna() & (orders["customer_id"] != "") & orders["order_ts"].notna()
            & orders["status"].isin(VALID_STATUSES))
    silver_orders = orders[keep].copy()

    lines = _read(landing_dir, "erp/order_lines/order_lines.csv")
    lines["order_key"] = order_key(lines["order_id"])
    lines["product_key"] = product_key(lines["product_code"])
    lines["ordered_qty_cases"] = pd.to_numeric(lines["ordered_qty_cases"], errors="coerce")
    lines["line_no"] = lines["line_no"].astype(int)
    keep = (lines["order_key"].isin(silver_orders["order_key"]) & (lines["ordered_qty_cases"] > 0)
            & lines["product_key"].notna())
    silver_lines = lines[keep].copy()

    ship = _read(landing_dir, "wms/shipments/shipments.csv")
    ship["order_key"] = order_key(ship["order_ref"])
    ship["ship_ts"] = wms_timestamp(ship["ship_ts"])
    ship["delivered_ts"] = wms_timestamp(ship["delivered_ts"])
    ship["ship_date"] = ship["ship_ts"].dt.normalize()
    ship["delivered_date"] = ship["delivered_ts"].dt.normalize()
    keep = (ship["shipment_id"] != "") & ship["order_key"].notna() & ship["ship_ts"].notna()
    silver_shipments = ship[keep].copy()

    sl = _read(landing_dir, "wms/shipment_lines/shipment_lines.csv")
    sl["order_key"] = order_key(sl["order_ref"])
    sl["product_key"] = product_key(sl["sku"])
    sl["line_no"] = sl["line_no"].astype(int)
    sl["shipped_qty_each"] = pd.to_numeric(sl["shipped_qty_each"], errors="coerce")
    sl["updated_at"] = pd.to_datetime(sl["updated_at"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    sl = sl.sort_values(["shipment_id", "line_no", "updated_at"]).drop_duplicates(
        ["shipment_id", "line_no"], keep="last")                       # BR-05
    keep = (sl["shipped_qty_each"] >= 0) & sl["product_key"].notna()
    silver_shipment_lines = sl[keep].copy()

    lots = _read(landing_dir, "wms/lots/lots.csv")
    lots["product_key"] = product_key(lots["sku"])
    lots["expiry"] = wms_date(lots["expiry_date"])
    lots["snapshot"] = wms_date(lots["snapshot_date"])
    lots["qty_on_hand_each"] = pd.to_numeric(lots["qty_on_hand_each"], errors="coerce")
    silver_lots = lots[(lots["lot_id"] != "") & (lots["qty_on_hand_each"] >= 0)].copy()

    return {
        "customers": silver_customers, "products": silver_products, "orders": silver_orders,
        "order_lines": silver_lines, "shipments": silver_shipments,
        "shipment_lines": silver_shipment_lines, "lots": silver_lots,
    }


# --------------------------------------------------------------------------
# Gold (BR-03, BR-06 to BR-16)
# --------------------------------------------------------------------------
def build_gold(silver: dict) -> dict:
    products = silver["products"][["product_key", "units_per_case", "unit_cost", "category"]]
    orders = silver["orders"]
    customers = silver["customers"][["customer_id", "segment"]]

    ol = (silver["order_lines"].drop(columns=["order_id"])
          .merge(products, on="product_key", how="inner")
          .merge(orders[["order_key", "order_id", "customer_id", "warehouse", "order_date", "promised", "status"]],
                 on="order_key", how="inner")
          .merge(customers, on="customer_id", how="left"))
    ol["ordered_each"] = (ol["ordered_qty_cases"] * ol["units_per_case"]).astype(int)

    shipped = (silver["shipment_lines"].groupby(["order_key", "line_no"], as_index=False)["shipped_qty_each"].sum()
               .rename(columns={"shipped_qty_each": "shipped_each"}))
    ol = ol.merge(shipped, on=["order_key", "line_no"], how="left")
    ol["shipped_each"] = ol["shipped_each"].fillna(0).astype(int)

    # quantity delivered on or before the promised date (BR-10)
    sh_dates = silver["shipments"][["shipment_id", "delivered_date"]]
    sl = silver["shipment_lines"].merge(sh_dates, on="shipment_id", how="inner")
    prom = orders[["order_key", "promised"]]
    sl = sl.merge(prom, on="order_key", how="inner")
    on_time_sl = sl[sl["delivered_date"].notna() & sl["promised"].notna() & (sl["delivered_date"] <= sl["promised"])]
    by_promise = (on_time_sl.groupby(["order_key", "line_no"], as_index=False)["shipped_qty_each"].sum()
                  .rename(columns={"shipped_qty_each": "delivered_by_promise_each"}))
    ol = ol.merge(by_promise, on=["order_key", "line_no"], how="left")
    ol["delivered_by_promise_each"] = ol["delivered_by_promise_each"].fillna(0).astype(int)

    ol["filled_each"] = ol[["shipped_each", "ordered_each"]].min(axis=1)
    ol["ordered_cases"] = ol["ordered_each"] / ol["units_per_case"]
    ol["filled_cases"] = ol["filled_each"] / ol["units_per_case"]
    ol["is_backordered"] = ol["shipped_each"] < ol["ordered_each"]
    ol["backorder_cases"] = (ol["ordered_each"] - ol["filled_each"]) / ol["units_per_case"]
    ol["line_in_full"] = ol["shipped_each"] >= ol["ordered_each"]
    ol["line_by_promise"] = ol["delivered_by_promise_each"] >= ol["ordered_each"]

    # order level
    deliveries = (silver["shipments"][silver["shipments"]["delivered_date"].notna()]
                  .groupby("order_key", as_index=False)
                  .agg(first_delivered=("delivered_date", "min"), last_delivered=("delivered_date", "max")))
    fo = ol.groupby("order_key", as_index=False).agg(
        order_id=("order_id", "first"), customer_id=("customer_id", "first"), segment=("segment", "first"),
        warehouse=("warehouse", "first"), order_date=("order_date", "first"), promised=("promised", "first"),
        status=("status", "first"), line_count=("line_no", "count"),
        in_full=("line_in_full", "all"), by_promise=("line_by_promise", "all"))
    fo = fo.merge(deliveries, on="order_key", how="left")
    fo["is_kpi_scope"] = fo["status"] == "CLOSED"
    has_promise = fo["promised"].notna()
    fo["is_on_time"] = has_promise & fo["first_delivered"].notna() & (fo["first_delivered"] <= fo["promised"])
    fo["is_otif"] = has_promise & fo["by_promise"]
    fo["lead_time_days"] = (fo["first_delivered"] - fo["order_date"]).dt.days
    fo["year_month"] = fo["order_date"].dt.strftime("%Y-%m")

    return {"order_lines": ol, "orders": fo}


def _ratio(num, den):
    return float(num) / float(den) if den else None


def expected_metrics(landing_dir: str) -> list[tuple]:
    """Return rows (metric, dimension, dim_value, expected_value) for qa.expected_kpis."""
    silver = build_silver(landing_dir)
    gold = build_gold(silver)
    rows: list[tuple] = []

    # AC-11: silver row counts
    for name, df in silver.items():
        rows.append(("silver_rows", "table", name, float(len(df))))

    ol, fo = gold["order_lines"], gold["orders"]
    sc_lines = ol[ol["status"] == "CLOSED"]
    sc = fo[fo["is_kpi_scope"]]
    eligible = sc[sc["promised"].notna()]

    def add_all(metric, value):
        rows.append((metric, "all", "all", float(value)))

    add_all("orders_in_scope", len(sc))
    add_all("otd_eligible_orders", len(eligible))
    add_all("otd_excluded_orders", len(sc) - len(eligible))
    add_all("fill_rate", _ratio(sc_lines["filled_cases"].sum(), sc_lines["ordered_cases"].sum()))
    add_all("otd_pct", _ratio(eligible["is_on_time"].sum(), len(eligible)))
    add_all("in_full_pct", _ratio(sc["in_full"].sum(), len(sc)))
    add_all("otif_pct", _ratio(eligible["is_otif"].sum(), len(eligible)))
    add_all("avg_lead_time_days", sc["lead_time_days"].mean())
    add_all("backorder_lines", sc_lines["is_backordered"].sum())
    add_all("backorder_cases", sc_lines.loc[sc_lines["is_backordered"], "backorder_cases"].sum())

    for seg, g in sc_lines.groupby("segment"):
        rows.append(("fill_rate", "segment", seg, _ratio(g["filled_cases"].sum(), g["ordered_cases"].sum())))
    for wh, g in eligible.groupby("warehouse"):
        rows.append(("otd_pct", "warehouse", wh, _ratio(g["is_on_time"].sum(), len(g))))
    for ym, g in eligible.groupby("year_month"):
        rows.append(("otif_pct", "year_month", ym, _ratio(g["is_otif"].sum(), len(g))))

    # AC-09: shipments from expired lots (BR-14)
    sl = (silver["shipment_lines"]
          .merge(silver["shipments"][["shipment_id", "ship_date"]], on="shipment_id", how="left")
          .merge(silver["lots"][["lot_id", "expiry"]], on="lot_id", how="left")
          .merge(silver["products"][["product_key", "units_per_case"]], on="product_key", how="left"))
    expired = sl[sl["expiry"].notna() & sl["ship_date"].notna() & (sl["expiry"] < sl["ship_date"])]
    add_all("expired_lot_shipment_lines", len(expired))
    add_all("expired_lot_shipment_cases", (expired["shipped_qty_each"] / expired["units_per_case"]).sum())

    # AC-10: expired stock at the snapshot date (BR-15)
    lots = silver["lots"].merge(silver["products"][["product_key", "unit_cost"]], on="product_key", how="left")
    snapshot = lots["snapshot"].max()
    exp_lots = lots[lots["expiry"].notna() & (lots["expiry"] < snapshot)]
    add_all("expired_stock_units", exp_lots["qty_on_hand_each"].sum())
    add_all("expired_stock_value", (exp_lots["qty_on_hand_each"] * exp_lots["unit_cost"]).sum())

    # AC-14: ERP status contradicts the WMS (BR-16)
    ship = silver["shipments"]
    agg = ship.groupby("order_key", as_index=False).agg(
        n=("shipment_id", "count"), n_delivered=("delivered_date", "count"), last_delivered=("delivered_date", "max"))
    agg = agg[(agg["n"] == agg["n_delivered"])]
    cand = silver["orders"].merge(agg, on="order_key", how="inner")
    cutoff = snapshot - pd.Timedelta(days=CLOSE_LAG_DAYS)
    mismatch = cand[~cand["status"].isin(["CLOSED", "CANCELLED"]) & (cand["last_delivered"] <= cutoff)]
    add_all("status_mismatch_orders", len(mismatch))
    return rows


def genie_reference(landing_dir: str) -> list[tuple]:
    """Reference answers for the Genie benchmark questions: (id, question, answer)."""
    silver = build_silver(landing_dir)
    gold = build_gold(silver)
    ol, fo = gold["order_lines"], gold["orders"]
    sc_lines = ol[ol["status"] == "CLOSED"]
    sc = fo[fo["is_kpi_scope"]]
    eligible = sc[sc["promised"].notna()]
    answers = []

    answers.append(("Q01", "What is the overall fill rate?",
                    f"{sc_lines['filled_cases'].sum() / sc_lines['ordered_cases'].sum():.4f}"))
    seg = eligible.groupby("segment").apply(lambda g: g["is_otif"].sum() / len(g), include_groups=False)
    answers.append(("Q02", "Which customer segment has the lowest OTIF rate?", f"{seg.idxmin()} ({seg.min():.4f})"))
    q1 = eligible[(eligible["order_date"] >= "2026-01-01") & (eligible["order_date"] < "2026-04-01")]
    answers.append(("Q03", "What was the on-time delivery rate for orders placed in 2026 Q1?",
                    f"{q1['is_on_time'].sum() / len(q1):.4f}"))
    ph = sc_lines[(sc_lines["segment"] == "Pharmacy") & sc_lines["is_backordered"]]
    answers.append(("Q04", "How many backordered lines were there for Pharmacy customers?", str(len(ph))))
    lt = sc.groupby("warehouse")["lead_time_days"].mean()
    answers.append(("Q05", "Which warehouse has the longest average order-to-delivery lead time?",
                    f"{lt.idxmax()} ({lt.max():.4f} days)"))
    metrics = {(m, d, v): x for m, d, v, x in expected_metrics(landing_dir)}
    answers.append(("Q06", "How many shipment lines left from expired lots?",
                    str(int(metrics[("expired_lot_shipment_lines", "all", "all")]))))
    lots = silver["lots"].merge(silver["products"][["product_key", "unit_cost"]], on="product_key", how="left")
    snap = lots["snapshot"].max()
    tor = lots[(lots["warehouse_code"] == "TOR") & lots["expiry"].notna() & (lots["expiry"] < snap)]
    answers.append(("Q07", "What is the value of expired stock in the Toronto warehouse?",
                    f"{(tor['qty_on_hand_each'] * tor['unit_cost']).sum():.2f}"))
    cat = sc_lines[sc_lines["is_backordered"]].groupby("category")["backorder_cases"].sum()
    answers.append(("Q08", "Which product category has the most backordered cases?",
                    f"{cat.idxmax()} ({cat.max():.1f} cases)"))
    late = sc[sc["promised"].notna() & ~sc["is_on_time"]].groupby("customer_id").size().sort_values(
        ascending=False, kind="stable")
    names = silver["customers"].set_index("customer_id")["customer_name"]
    tied = len(late) > 1 and late.iloc[0] == late.iloc[1]
    answers.append(("Q09", "Which customer has the most late orders?",
                    f"{names[late.index[0]]} ({late.iloc[0]})" + (" [TIE AT RANK 1]" if tied else "")))
    answers.append(("Q10", "How many orders have an ERP status that contradicts the warehouse system?",
                    str(int(metrics[("status_mismatch_orders", "all", "all")]))))
    return answers
