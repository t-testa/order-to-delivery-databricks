"""The synthetic data is deterministic and contains the defects the pipeline must handle."""
import csv
import hashlib
import json
import os

import generate


def _hash_tree(root):
    digest = hashlib.sha256()
    for folder, _, files in sorted(os.walk(root)):
        for name in sorted(files):
            digest.update(name.encode())
            with open(os.path.join(folder, name), "rb") as fh:
                digest.update(fh.read())
    return digest.hexdigest()


def _rows(landing, rel):
    with open(os.path.join(landing, rel), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_same_seed_gives_identical_files(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate.generate(str(a), seed=7, n_orders=800)
    generate.generate(str(b), seed=7, n_orders=800)
    assert _hash_tree(a) == _hash_tree(b)


def test_different_seed_gives_different_files(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate.generate(str(a), seed=7, n_orders=800)
    generate.generate(str(b), seed=8, n_orders=800)
    assert _hash_tree(a) != _hash_tree(b)


def test_the_two_systems_disagree_on_formats(landing_dir):
    orders = _rows(landing_dir, "erp/orders/orders.csv")
    shipments = _rows(landing_dir, "wms/shipments/shipments.csv")
    lines = _rows(landing_dir, "wms/shipment_lines/shipment_lines.csv")
    assert all(o["order_id"].startswith("SO-") for o in orders)
    refs = [s["order_ref"] for s in shipments]
    assert any(r.startswith("SO") and "-" not in r for r in refs)           # dash removed
    assert any(r.startswith("so") for r in refs)                             # lower case
    assert any(r.endswith(" ") for r in refs)                                # trailing space
    assert any("/" in s["ship_ts"] for s in shipments)                       # dd/MM/yyyy HH:mm
    assert any("-" in s["ship_ts"] and "/" not in s["ship_ts"] for s in shipments)   # yyyy-MM-dd HH:mm
    skus = {l["sku"] for l in lines}
    assert any(len(s) == 5 for s in skus) and any(len(s) < 5 for s in skus)  # padded and unpadded


def test_defects_are_injected(landing_dir):
    manifest = json.load(open(os.path.join(landing_dir, "manifest.json")))["injected_defects"]
    for key in ("null_customer_orders", "null_promised_orders", "bad_order_line_qty", "stale_erp_status_orders",
                "duplicate_shipment_lines", "corrected_shipment_lines", "negative_shipment_qty",
                "orphan_shipments", "expired_lot_picks_injected", "split_shipment_orders",
                "over_shipped_lines", "invalid_emails"):
        assert manifest[key] > 0, key


def test_duplicate_and_corrected_lines_exist_in_the_file(landing_dir):
    lines = _rows(landing_dir, "wms/shipment_lines/shipment_lines.csv")
    seen = {}
    for l in lines:
        seen.setdefault((l["shipment_id"], l["line_no"]), []).append(l)
    multi = [v for v in seen.values() if len(v) > 1]
    assert multi
    assert any(len({x["shipped_qty_each"] for x in v}) > 1 for v in multi)   # a correction with another quantity
    assert any(len({x["shipped_qty_each"] for x in v}) == 1 for v in multi)  # an exact re-send
