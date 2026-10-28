"""Deterministic synthetic data for Laurentia Distribution (a fictional distributor).

Two source systems are simulated and they deliberately disagree:

* ERP (commercial view): customers, products, orders, order lines.
* WMS (logistics view): shipments, shipment lines, lots and inventory.

Defects are injected on purpose (see the DEFECT_RATES constants) so that the
data quality rules in the pipeline have something real to catch.

Only the Python standard library is used, and every random draw comes from one
seeded ``random.Random``. The same seed therefore always produces the same
files, on a laptop and on Databricks.
"""
from __future__ import annotations

import csv
import json
import os
import random
from datetime import date, datetime, timedelta

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
AS_OF = date(2026, 7, 31)            # date of the WMS lot snapshot
FIRST_ORDER_DATE = date(2025, 1, 1)
LAST_ORDER_DATE = date(2026, 7, 25)
CLOSE_LAG_DAYS = 7                   # ERP closes an order 7 days after last delivery

DEFAULT_SEED = 42
DEFAULT_CUSTOMERS = 400
DEFAULT_PRODUCTS = 250
DEFAULT_ORDERS = 15000

WAREHOUSES = ["MTL", "TOR", "VAN"]
WAREHOUSE_BY_PROVINCE = {"QC": "MTL", "ON": "TOR", "BC": "VAN"}

SEGMENTS = [("Pharmacy", 0.45), ("Clinic", 0.15), ("Hardware Retail", 0.25), ("Contractor", 0.15)]
PROMISE_DAYS = {"Pharmacy": 3, "Clinic": 3, "Hardware Retail": 5, "Contractor": 4}
PROVINCES = [("QC", 0.50), ("ON", 0.35), ("BC", 0.15)]
PROVINCE_NAMES = {"QC": "Quebec", "ON": "Ontario", "BC": "British Columbia"}
CITIES = {
    "QC": ["Montreal", "Laval", "Quebec City", "Gatineau", "Sherbrooke"],
    "ON": ["Toronto", "Ottawa", "Mississauga", "Hamilton", "London"],
    "BC": ["Vancouver", "Victoria", "Surrey", "Burnaby", "Kelowna"],
}
AREA_CODES = {"QC": ["514", "438", "418"], "ON": ["416", "613", "905"], "BC": ["604", "250"]}
NAME_PREFIX = {
    "Pharmacy": ["Pharmacie", "Pharmacy", "Apothecary"],
    "Clinic": ["Clinique", "Medical Clinic", "Health Centre"],
    "Hardware Retail": ["Quincaillerie", "Hardware", "Home Centre"],
    "Contractor": ["Construction", "Builders", "Renovations"],
}
SURNAMES = ["Tremblay", "Gagnon", "Roy", "Cote", "Bouchard", "Gauthier", "Morin", "Lavoie",
            "Fortin", "Pelletier", "Smith", "Brown", "Wilson", "Taylor", "Chen", "Singh",
            "Patel", "Nguyen", "Campbell", "Martin"]
CARRIERS = ["NorthLine Freight", "Maple Express", "Pacific Haul", "Laurentian Logistics"]

# category: (share of catalogue, cost range, units per case choices, shelf life range in months or None)
CATEGORIES = {
    "Prescription Pharma": (0.25, (3.0, 60.0), [12, 24, 48], (12, 36)),
    "OTC Health": (0.20, (2.0, 25.0), [12, 24, 48], (12, 30)),
    "Medical Supplies": (0.15, (1.0, 40.0), [6, 12, 24], (24, 60)),
    "Hardware": (0.20, (2.0, 120.0), [6, 12, 24], None),
    "Garden": (0.10, (3.0, 80.0), [6, 12], None),
    "Paint": (0.10, (8.0, 45.0), [4, 6], (24, 24)),
}
PRODUCT_BASES = {
    "Prescription Pharma": ["Metformin", "Atorvastatin", "Amlodipine", "Omeprazole", "Levothyroxine", "Sertraline"],
    "OTC Health": ["Ibuprofen", "Acetaminophen", "Loratadine", "Cough Syrup", "Antacid", "Vitamin D"],
    "Medical Supplies": ["Gauze Roll", "Nitrile Gloves", "Syringe", "Bandage Pack", "Thermometer Cover", "Face Mask"],
    "Hardware": ["Wood Screws", "Cordless Drill", "Claw Hammer", "Tape Measure", "Work Gloves", "Utility Knife"],
    "Garden": ["Garden Hose", "Potting Soil", "Pruning Shears", "Lawn Seed", "Plant Fertilizer", "Rake"],
    "Paint": ["Interior Paint", "Exterior Paint", "Primer", "Wood Stain", "Paint Roller Kit", "Wall Filler"],
}
# Which categories each customer segment buys
SEGMENT_CATEGORY_WEIGHTS = {
    "Pharmacy": {"Prescription Pharma": 5, "OTC Health": 4, "Medical Supplies": 2},
    "Clinic": {"Prescription Pharma": 2, "OTC Health": 2, "Medical Supplies": 6},
    "Hardware Retail": {"Hardware": 5, "Garden": 3, "Paint": 3},
    "Contractor": {"Hardware": 5, "Paint": 4, "Garden": 1},
}

# Defect rates (share of the relevant rows)
DEFECT_RATES = {
    "cancelled_order": 0.02,
    "null_customer_order": 0.008,
    "null_promised_date": 0.01,
    "bad_order_line_qty": 0.004,
    "stale_erp_status": 0.025,
    "duplicate_shipment_line": 0.012,
    "corrected_shipment_line": 0.006,
    "negative_shipment_qty": 0.002,
    "orphan_shipment": 0.004,       # share of n_orders
    "expired_lot_pick": 0.03,       # share of perishable shipment lines (when an expired lot exists)
    "invalid_email": 0.02,
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _weighted(rng: random.Random, pairs):
    return rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs], k=1)[0]


def _fmt_wms_ts(rng: random.Random, ts: datetime, counters: dict) -> str:
    """WMS timestamp: dd/MM/yyyy HH:mm, or yyyy-MM-dd HH:mm for ~3% of rows."""
    if rng.random() < 0.03:
        counters["wms_iso_timestamps"] += 1
        return ts.strftime("%Y-%m-%d %H:%M")
    return ts.strftime("%d/%m/%Y %H:%M")


def _fmt_sku(rng: random.Random, number: int) -> str:
    """WMS SKU: plain integer or zero padded, versus 'SKU-00042' in the ERP."""
    return str(number) if rng.random() < 0.5 else f"{number:05d}"


def _fmt_order_ref(rng: random.Random, order_id: str) -> str:
    """WMS order reference: 'SO100001', 'so100001' or 'SO100001 ' versus 'SO-100001' in the ERP."""
    base = order_id.replace("-", "")
    r = rng.random()
    if r < 0.90:
        return base
    if r < 0.95:
        return base.lower()
    return base + " "


class Lot:
    __slots__ = ("lot_id", "product_no", "warehouse", "received", "expiry", "qty_on_hand")

    def __init__(self, lot_id, product_no, warehouse, received, expiry, qty_on_hand):
        self.lot_id = lot_id
        self.product_no = product_no
        self.warehouse = warehouse
        self.received = received
        self.expiry = expiry
        self.qty_on_hand = qty_on_hand


# --------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------
def build_customers(rng, n, counters):
    rows, meta = [], []
    for i in range(1, n + 1):
        segment = _weighted(rng, SEGMENTS)
        province = _weighted(rng, PROVINCES)
        city = rng.choice(CITIES[province])
        surname = rng.choice(SURNAMES)
        name = f"{rng.choice(NAME_PREFIX[segment])} {surname} #{i:03d}"
        email = f"orders{i}@{surname.lower()}{i}.example"
        r = rng.random()
        if r < DEFECT_RATES["invalid_email"]:
            email = email.replace("@", "")           # invalid format
            counters["invalid_emails"] += 1
        elif r < 0.06:
            email = email.upper()                    # shouting
        elif r < 0.08:
            email = f"  {email} "                    # stray spaces
        area = rng.choice(AREA_CODES[province])
        line = f"{rng.randint(100, 199):04d}"
        phone = rng.choice([f"{area}-555-{line}", f"({area}) 555-{line}", f"{area}.555.{line}"])
        seg_out = segment
        r = rng.random()
        if r < 0.05:
            seg_out = segment.upper()
        elif r < 0.10:
            seg_out = f" {segment.lower()} "
        prov_out = province
        r = rng.random()
        if r < 0.08:
            prov_out = PROVINCE_NAMES[province]
        elif r < 0.11:
            prov_out = province.lower()
        created = date(2018, 1, 1) + timedelta(days=rng.randint(0, 2400))
        rows.append({
            "customer_id": f"C{i:04d}", "customer_name": name, "segment": seg_out,
            "province": prov_out, "city": city, "email": email, "phone": phone,
            "credit_limit": f"{rng.choice([10000, 25000, 50000, 100000])}.00",
            "created_at": created.isoformat(),
        })
        meta.append({"customer_id": f"C{i:04d}", "segment": segment, "province": province,
                     "warehouse": WAREHOUSE_BY_PROVINCE[province]})
    return rows, meta


def build_products(rng, n):
    rows, meta = [], []
    cats = list(CATEGORIES.keys())
    counts = {c: max(1, round(n * CATEGORIES[c][0])) for c in cats}
    seq = []
    for c in cats:
        seq.extend([c] * counts[c])
    seq = seq[:n]
    while len(seq) < n:
        seq.append(cats[0])
    for i, cat in enumerate(seq, start=1):
        share, (lo, hi), upc_choices, shelf = CATEGORIES[cat]
        base = PRODUCT_BASES[cat][(i - 1) % len(PRODUCT_BASES[cat])]
        name = f"{base} Pack {i:03d}"
        cost = round(rng.uniform(lo, hi), 2)
        price = round(cost * rng.uniform(1.15, 1.6), 2)
        upc = rng.choice(upc_choices)
        shelf_months = rng.randint(shelf[0], shelf[1]) if shelf else None
        status = "ACTIVE" if rng.random() < 0.96 else "DISCONTINUED"
        rows.append({
            "product_code": f"SKU-{i:05d}", "product_name": name, "category": cat, "uom": "CASE",
            "units_per_case": str(upc), "unit_cost": f"{cost:.2f}", "unit_price": f"{price:.2f}",
            "shelf_life_months": "" if shelf_months is None else str(shelf_months), "status": status,
        })
        meta.append({"no": i, "category": cat, "upc": upc, "price": price, "cost": cost,
                     "shelf_months": shelf_months})
    return rows, meta


def build_lots(rng, products_meta):
    """Lots per (product, warehouse). Perishable lots get an expiry date."""
    lots, by_key = [], {}
    counter = 0
    for p in products_meta:
        for wh in WAREHOUSES:
            received = date(2024, 10, 1) + timedelta(days=rng.randint(0, 45))
            n_lots = rng.randint(3, 5)
            for _ in range(n_lots):
                if received > AS_OF:
                    break
                counter += 1
                expiry = None
                if p["shelf_months"] is not None:
                    expiry = received + timedelta(days=p["shelf_months"] * 30 + rng.randint(-20, 20))
                depleted = 0.65 if (expiry and expiry < AS_OF) else 0.30
                qty = 0 if rng.random() < depleted else p["upc"] * rng.randint(1, 120)
                lot = Lot(f"LOT-{wh}-{counter:06d}", p["no"], wh, received, expiry, qty)
                lots.append(lot)
                by_key.setdefault((p["no"], wh), []).append(lot)
                received = received + timedelta(days=rng.randint(60, 150))
    return lots, by_key


def pick_lot(rng, by_key, product_no, warehouse, ship_date, perishable, counters):
    """FEFO (first expiry, first out). A small share of picks wrongly takes an expired lot."""
    lots = by_key.get((product_no, warehouse), [])
    candidates = [l for l in lots if l.received <= ship_date] or lots[:1]
    if perishable and rng.random() < DEFECT_RATES["expired_lot_pick"]:
        expired = [l for l in candidates if l.expiry and l.expiry < ship_date]
        if expired:
            counters["expired_lot_picks_injected"] += 1
            return rng.choice(expired)
    valid = [l for l in candidates if l.expiry is None or l.expiry >= ship_date]
    if valid:
        return min(valid, key=lambda l: (l.expiry or date.max, l.received))
    return max(candidates, key=lambda l: l.received)


# --------------------------------------------------------------------------
# Order to delivery simulation
# --------------------------------------------------------------------------
def _random_order_date(rng):
    span = (LAST_ORDER_DATE - FIRST_ORDER_DATE).days
    while True:
        d = FIRST_ORDER_DATE + timedelta(days=rng.randint(0, span))
        weight = {5: 0.25, 6: 0.05}.get(d.weekday(), 1.0)   # fewer weekend orders
        if rng.random() < weight:
            return d


TRANSIT_WEIGHTS = {"MTL": [0.66, 0.28, 0.06], "TOR": [0.62, 0.30, 0.08], "VAN": [0.50, 0.35, 0.15]}
SHORTAGE_MULTIPLIER = {"Prescription Pharma": 1.6, "OTC Health": 1.0, "Medical Supplies": 1.2,
                       "Hardware": 0.7, "Garden": 0.8, "Paint": 0.9}


def _transit_days(rng, wh):
    t = rng.choices([1, 2, 3], weights=TRANSIT_WEIGHTS[wh], k=1)[0]
    if rng.random() < 0.08:                 # carrier delay
        t += rng.randint(1, 3)
    return t


def simulate(seed=DEFAULT_SEED, n_customers=DEFAULT_CUSTOMERS, n_products=DEFAULT_PRODUCTS,
             n_orders=DEFAULT_ORDERS):
    """Return (tables, manifest). ``tables`` maps file name to a list of string-valued rows."""
    rng = random.Random(seed)
    counters = {k: 0 for k in [
        "invalid_emails", "wms_iso_timestamps", "cancelled_orders", "null_customer_orders",
        "null_promised_orders", "bad_order_line_qty", "stale_erp_status_orders",
        "duplicate_shipment_lines", "corrected_shipment_lines", "negative_shipment_qty",
        "orphan_shipments", "expired_lot_picks_injected", "split_shipment_orders",
        "over_shipped_lines", "short_shipped_lines", "orders", "order_lines"]}

    customers, cust_meta = build_customers(rng, n_customers, counters)
    products, prod_meta = build_products(rng, n_products)
    lots, lots_by_key = build_lots(rng, prod_meta)

    products_by_cat = {}
    for p in prod_meta:
        products_by_cat.setdefault(p["category"], []).append(p)

    erp_orders, erp_lines = [], []
    wms_shipments, wms_lines = [], []
    shipment_seq = 0

    def make_shipment(order_ref_src, wh, ship_ts, lines, perishable_of):
        """Create one WMS shipment with its lines. ``lines`` = [(line_no, product_no, qty_each)]."""
        nonlocal shipment_seq
        shipment_seq += 1
        sid = f"SHP-{shipment_seq:07d}"
        delivered_ts = None
        d = ship_ts + timedelta(days=_transit_days(rng, wh))
        d = d.replace(hour=rng.randint(8, 18), minute=rng.randint(0, 59))
        if d.date() <= AS_OF:
            delivered_ts = d
        status = "DELIVERED" if delivered_ts else "IN_TRANSIT"
        if status == "DELIVERED" and rng.random() < 0.05:
            status = "delivered"
        order_ref = _fmt_order_ref(rng, order_ref_src)
        wms_shipments.append({
            "shipment_id": sid, "order_ref": order_ref,
            "ship_ts": _fmt_wms_ts(rng, ship_ts, counters),
            "delivered_ts": _fmt_wms_ts(rng, delivered_ts, counters) if delivered_ts else "",
            "carrier": rng.choice(CARRIERS), "shipment_status": status,
        })
        for line_no, product_no, qty in lines:
            lot = pick_lot(rng, lots_by_key, product_no, wh, ship_ts.date(), perishable_of(product_no), counters)
            updated = ship_ts + timedelta(minutes=rng.randint(1, 30))
            sku = _fmt_sku(rng, product_no)
            row = {"shipment_id": sid, "line_no": str(line_no), "order_ref": order_ref, "sku": sku,
                   "shipped_qty_each": str(qty), "lot_id": lot.lot_id,
                   "updated_at": updated.strftime("%Y-%m-%d %H:%M:%S")}
            r = rng.random()
            if r < DEFECT_RATES["negative_shipment_qty"]:
                row["shipped_qty_each"] = str(-rng.randint(1, 5))
                counters["negative_shipment_qty"] += 1
                wms_lines.append(row)
                continue
            wms_lines.append(row)
            if r < DEFECT_RATES["negative_shipment_qty"] + DEFECT_RATES["duplicate_shipment_line"]:
                wms_lines.append(dict(row))              # exact re-send
                counters["duplicate_shipment_lines"] += 1
            elif r < (DEFECT_RATES["negative_shipment_qty"] + DEFECT_RATES["duplicate_shipment_line"]
                      + DEFECT_RATES["corrected_shipment_line"]):
                older = dict(row)                        # earlier, wrong version of the same line
                older["updated_at"] = (updated - timedelta(minutes=rng.randint(10, 40))).strftime("%Y-%m-%d %H:%M:%S")
                older["shipped_qty_each"] = str(qty + 1 if qty <= 1 else qty - 1)
                wms_lines.append(older)
                counters["corrected_shipment_lines"] += 1
        return delivered_ts

    perishable_flag = {p["no"]: p["shelf_months"] is not None for p in prod_meta}
    perishable_of = lambda product_no: perishable_flag[product_no]

    for i in range(1, n_orders + 1):
        order_id = f"SO-{100000 + i}"
        cidx = int((rng.random() ** 1.6) * n_customers)
        cust = cust_meta[cidx]
        segment, wh = cust["segment"], cust["warehouse"]
        order_date = _random_order_date(rng)
        order_ts = datetime(order_date.year, order_date.month, order_date.day,
                            rng.randint(6, 17), rng.randint(0, 59), rng.randint(0, 59))
        promised = order_date + timedelta(days=PROMISE_DAYS[segment])
        requested = order_date + timedelta(days=rng.randint(1, 5))

        n_lines = rng.choices(range(1, 9), weights=[15, 22, 22, 17, 12, 7, 4, 1], k=1)[0]
        weights = SEGMENT_CATEGORY_WEIGHTS[segment]
        chosen, tries = [], 0
        while len(chosen) < n_lines and tries < 50:
            tries += 1
            cat = rng.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]
            p = rng.choice(products_by_cat[cat])
            if p["no"] not in [c["no"] for c in chosen]:
                chosen.append(p)
        lines = []
        for line_no, p in enumerate(chosen, start=1):
            qty_cases = min(60, 1 + int(rng.lognormvariate(1.2, 0.8)))
            lines.append({"line_no": line_no, "p": p, "cases": qty_cases, "each": qty_cases * p["upc"]})

        # ---- fulfilment simulation (the WMS truth) ----
        cancelled = rng.random() < DEFECT_RATES["cancelled_order"]
        shipped_last_delivery = None
        all_delivered = True
        pending_backorder = False
        has_shipment = False
        n_shipments = 0
        if not cancelled:
            d0 = rng.choices([0, 1, 2, 3, 4], weights=[45, 38, 12, 4, 1], k=1)[0]
            ship_date = order_date + timedelta(days=d0)
            ship_ts = datetime(ship_date.year, ship_date.month, ship_date.day,
                               rng.randint(8, 18), rng.randint(0, 59))
            if ship_ts <= order_ts:
                ship_ts = order_ts + timedelta(hours=rng.randint(1, 3))
            if ship_ts.date() <= AS_OF:
                first, remainders = [], []
                for ln in lines:
                    r = rng.random()
                    ordered_each = ln["each"]
                    mult = SHORTAGE_MULTIPLIER[ln["p"]["category"]]
                    p_short, p_zero, p_over = 0.12 * mult, 0.022 * mult, 0.008
                    if r < p_zero:
                        shipped = 0
                    elif r < p_short:
                        shipped = max(1, int(ordered_each * rng.uniform(0.3, 0.95)))
                        shipped = min(shipped, ordered_each - 1)
                    elif r < p_short + p_over:
                        shipped = ordered_each + ln["p"]["upc"]
                        counters["over_shipped_lines"] += 1
                    else:
                        shipped = ordered_each
                    ln["first"] = shipped
                    if shipped < ordered_each:
                        counters["short_shipped_lines"] += 1
                if all(ln["first"] == 0 for ln in lines):
                    lines[0]["first"] = max(1, lines[0]["each"] // 2)
                for ln in lines:
                    if ln["first"] > 0:
                        first.append((ln["line_no"], ln["p"]["no"], ln["first"]))
                    if ln["first"] < ln["each"] and rng.random() < 0.45:
                        remainders.append((ln["line_no"], ln["p"]["no"], ln["each"] - ln["first"]))
                d1 = make_shipment(order_id, wh, ship_ts, first, perishable_of)
                has_shipment = True
                n_shipments = 1
                if d1 is None:
                    all_delivered = False
                else:
                    shipped_last_delivery = d1
                if remainders:
                    ship2 = ship_ts + timedelta(days=rng.randint(2, 6))
                    if ship2.date() <= AS_OF:
                        d2 = make_shipment(order_id, wh, ship2, remainders, perishable_of)
                        n_shipments = 2
                        counters["split_shipment_orders"] += 1
                        if d2 is None:
                            all_delivered = False
                        elif shipped_last_delivery is None or d2 > shipped_last_delivery:
                            shipped_last_delivery = d2
                    else:
                        pending_backorder = True

        # ---- ERP status (lags / disagrees on purpose) ----
        if cancelled:
            status = "CANCELLED"
            counters["cancelled_orders"] += 1
        elif has_shipment:
            if (all_delivered and not pending_backorder and shipped_last_delivery is not None
                    and shipped_last_delivery.date() + timedelta(days=CLOSE_LAG_DAYS) <= AS_OF):
                status = "CLOSED"
                if rng.random() < DEFECT_RATES["stale_erp_status"]:
                    status = "SHIPPED"                      # ERP forgot to close the order
                    counters["stale_erp_status_orders"] += 1
            else:
                status = "SHIPPED"
        else:
            status = "OPEN"

        # ---- ERP rows (with injected defects) ----
        customer_out = cust["customer_id"]
        if rng.random() < DEFECT_RATES["null_customer_order"]:
            customer_out = ""
            counters["null_customer_orders"] += 1
        promised_out = promised.isoformat()
        if rng.random() < DEFECT_RATES["null_promised_date"]:
            promised_out = ""
            counters["null_promised_orders"] += 1
        status_out = status
        r = rng.random()
        if r < 0.02:
            status_out = status.lower()
        elif r < 0.04:
            status_out = status.capitalize() + " "
        erp_orders.append({
            "order_id": order_id, "customer_id": customer_out,
            "order_ts": order_ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "requested_delivery_date": requested.isoformat(),
            "promised_delivery_date": promised_out, "warehouse_code": f"WH-{wh}",
            "order_status": status_out, "channel": rng.choice(["EDI", "Portal", "Phone", "Sales Rep"]),
        })
        counters["orders"] += 1
        for ln in lines:
            qty_out = str(ln["cases"])
            if rng.random() < DEFECT_RATES["bad_order_line_qty"]:
                qty_out = rng.choice(["0", "-1"])
                counters["bad_order_line_qty"] += 1
            erp_lines.append({
                "order_id": order_id, "line_no": str(ln["line_no"]),
                "product_code": f"SKU-{ln['p']['no']:05d}", "ordered_qty_cases": qty_out,
                "unit_price": f"{ln['p']['price']:.2f}",
            })
            counters["order_lines"] += 1

    # ---- orphan shipments: WMS shipments for orders the ERP does not know ----
    n_orphans = int(n_orders * DEFECT_RATES["orphan_shipment"])
    for k in range(n_orphans):
        fake_order = f"SO-{900000 + k}"
        wh = rng.choice(WAREHOUSES)
        ship_date = FIRST_ORDER_DATE + timedelta(days=rng.randint(10, (LAST_ORDER_DATE - FIRST_ORDER_DATE).days))
        ship_ts = datetime(ship_date.year, ship_date.month, ship_date.day, rng.randint(8, 18), rng.randint(0, 59))
        picks = rng.sample(prod_meta, rng.randint(1, 3))
        lines = [(n, p["no"], p["upc"] * rng.randint(1, 10)) for n, p in enumerate(picks, start=1)]
        make_shipment(fake_order, wh, ship_ts, lines, perishable_of)
        counters["orphan_shipments"] += 1

    rng.shuffle(wms_lines)           # the WMS does not send lines in order

    lots_rows = []
    for l in lots:
        lots_rows.append({
            "lot_id": l.lot_id, "sku": _fmt_sku(rng, l.product_no), "warehouse_code": l.warehouse,
            "received_date": l.received.strftime("%d/%m/%Y"),
            "expiry_date": l.expiry.strftime("%d/%m/%Y") if l.expiry else "",
            "qty_on_hand_each": str(l.qty_on_hand), "snapshot_date": AS_OF.strftime("%d/%m/%Y"),
        })

    tables = {
        "erp/customers/customers.csv": customers,
        "erp/products/products.csv": products,
        "erp/orders/orders.csv": erp_orders,
        "erp/order_lines/order_lines.csv": erp_lines,
        "wms/shipments/shipments.csv": wms_shipments,
        "wms/shipment_lines/shipment_lines.csv": wms_lines,
        "wms/lots/lots.csv": lots_rows,
    }
    manifest = {
        "seed": seed, "as_of": AS_OF.isoformat(),
        "row_counts": {path: len(rows) for path, rows in tables.items()},
        "injected_defects": counters,
    }
    return tables, manifest


def generate(out_dir, seed=DEFAULT_SEED, n_customers=DEFAULT_CUSTOMERS, n_products=DEFAULT_PRODUCTS,
             n_orders=DEFAULT_ORDERS):
    """Generate the data and write one CSV per table under ``out_dir`` (plus manifest.json)."""
    tables, manifest = simulate(seed, n_customers, n_products, n_orders)
    for rel_path, rows in tables.items():
        full = os.path.join(out_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate the synthetic landing files.")
    parser.add_argument("--out", default="landing")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--orders", type=int, default=DEFAULT_ORDERS)
    args = parser.parse_args()
    print(json.dumps(generate(args.out, seed=args.seed, n_orders=args.orders), indent=2))
