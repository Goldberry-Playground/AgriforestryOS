"""Tests for the harvest → Odoo receipt sync (pure transforms + orchestration)."""
import copy

import harvest_sync as hs
from state import SyncState


# A farmOS harvest-log collection: one log, two harvested assets, one quantity.
_BODY = {
    "data": [{
        "id": "log-1", "type": "log--harvest",
        "attributes": {"name": "Apple pick", "timestamp": "2026-09-15T12:00:00+00:00"},
        "relationships": {
            "asset": {"data": [{"type": "asset--tree", "id": "tree-apple"}]},
            "quantity": {"data": [{"type": "quantity--standard", "id": "q1"}]},
        },
    }],
    "included": [
        {"type": "asset--tree", "id": "tree-apple", "attributes": {"name": "Apple Heritage"}},
        {"type": "taxonomy_term--unit", "id": "u-kg", "attributes": {"name": "kg"}},
        {"type": "quantity--standard", "id": "q1",
         "attributes": {"label": "Apples", "measure": "weight",
                        "value": {"numerator": 12, "denominator": 1}},
         "relationships": {"units": {"data": {"type": "taxonomy_term--unit", "id": "u-kg"}}}},
    ],
}


# --- pure transforms --------------------------------------------------------

def test_quantity_value_forms():
    assert hs.quantity_value({"value": {"numerator": 12, "denominator": 1}}) == 12.0
    assert hs.quantity_value({"value": {"decimal": "3.5"}}) == 3.5
    assert hs.quantity_value({"value": "4.2"}) == 4.2
    assert hs.quantity_value({}) is None


def test_harvest_to_receipts_uses_label_then_asset():
    receipts = hs.harvest_to_receipts(_BODY["data"][0], _BODY["included"])
    assert len(receipts) == 1
    r = receipts[0]
    assert r["log_uuid"] == "log-1"
    assert r["product_hint"] == "Apples"      # quantity label wins
    assert r["quantity"] == 12.0
    assert r["unit"] == "kg"
    assert r["date"].startswith("2026-09-15")


def test_harvest_to_receipts_falls_back_to_asset_name():
    body = copy.deepcopy(_BODY)  # deep-copy so we don't pollute the shared fixture
    for i in body["included"]:
        if i["id"] == "q1":
            i["attributes"] = {"measure": "weight", "value": {"numerator": 5, "denominator": 1}}
    receipts = hs.harvest_to_receipts(body["data"][0], body["included"])
    assert receipts[0]["product_hint"] == "Apple Heritage"


def test_harvest_to_receipts_drops_valueless():
    body = copy.deepcopy(_BODY)
    for i in body["included"]:
        if i["id"] == "q1":
            i["attributes"] = {"label": "Apples", "value": None}
    assert hs.harvest_to_receipts(body["data"][0], body["included"]) == []


# --- orchestration ----------------------------------------------------------

class FakeFarmOS:
    def __init__(self, body): self._body = body; self.since = "unset"
    def get_harvests(self, since=None): self.since = since; return self._body

class FakeOdoo:
    def __init__(self, products, existing_origins=()):
        self._products = products          # name → id
        self._existing = set(existing_origins)
        self.created = []
    def harvest_receipt_exists(self, origin): return origin in self._existing
    def find_product_id(self, name): return self._products.get(name)
    def create_harvest_receipt(self, product_id, quantity, date, origin):
        self.created.append({"product_id": product_id, "quantity": quantity, "origin": origin})
        self._existing.add(origin)
        return len(self.created)


def _svc(farmos, odoo, tmp_path):
    return hs.HarvestSyncService(farmos, odoo, SyncState(tmp_path / "h.json"))


def test_records_new_harvest(tmp_path):
    odoo = FakeOdoo(products={"Apples": 42})
    counts = _svc(FakeFarmOS(_BODY), odoo, tmp_path).run_once()
    assert counts["recorded"] == 1
    assert odoo.created[0] == {"product_id": 42, "quantity": 12.0,
                               "origin": "farmOS:harvest:log-1"}


def test_idempotent_skips_existing(tmp_path):
    odoo = FakeOdoo(products={"Apples": 42}, existing_origins={"farmOS:harvest:log-1"})
    counts = _svc(FakeFarmOS(_BODY), odoo, tmp_path).run_once()
    assert counts["recorded"] == 0 and counts["skipped_existing"] == 1
    assert odoo.created == []


def test_skips_unmatched_product(tmp_path):
    odoo = FakeOdoo(products={})  # no "Apples" product in Odoo
    counts = _svc(FakeFarmOS(_BODY), odoo, tmp_path).run_once()
    assert counts["recorded"] == 0 and counts["skipped_no_product"] == 1


def test_cursor_advances(tmp_path):
    svc = _svc(FakeFarmOS(_BODY), FakeOdoo(products={"Apples": 42}), tmp_path)
    svc.run_once()
    assert svc._state.load_cursor() == "2026-09-15T12:00:00+00:00"


def test_empty_body_noop(tmp_path):
    counts = _svc(FakeFarmOS({"data": [], "included": []}),
                  FakeOdoo(products={}), tmp_path).run_once()
    assert counts == {"recorded": 0, "skipped_existing": 0, "skipped_no_product": 0}
