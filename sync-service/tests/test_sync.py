"""
Orchestration tests for SyncService using in-memory fakes.

The fakes implement just the OdooClient / FarmOSWriter surface the
orchestrator calls, so these tests exercise the create/archive/idempotency
logic without HTTP or XML-RPC.
"""
import tempfile
from pathlib import Path

import pytest

from mapping import Transfer
from state import SyncState
from sync import SyncService


class FakeOdoo:
    def __init__(self, moves_in=None, moves_out=None):
        self._in = moves_in or []
        self._out = moves_out or []

    def moves_into_orchard(self, orchard_id, since=None):
        return list(self._in)

    def moves_out_of_orchard(self, orchard_id, since=None):
        return list(self._out)


class FakeFarmOS:
    def __init__(self, existing=None):
        # existing: list of {"id", "odoo_lot", "status"}
        self.trees = list(existing or [])
        self.created = []
        self.archived = []

    def find_tree_by_lot(self, lot, status=None):
        for t in self.trees:
            if t["odoo_lot"] == lot and (status is None or t["status"] == status):
                return t
        return None

    def create_tree(self, attributes, species_name=None):
        rec = {"id": f"uuid-{len(self.trees)+1}", "odoo_lot": attributes["odoo_lot"],
               "status": "active", "attributes": attributes, "species": species_name}
        self.trees.append(rec)
        self.created.append(rec)
        return rec

    def archive_tree(self, asset_id):
        for t in self.trees:
            if t["id"] == asset_id:
                t["status"] = "archived"
                self.archived.append(t)
                return t
        return None


def _service(odoo, farmos, tmp_path, nursery_cats=None):
    state = SyncState(Path(tmp_path) / "state.json")
    return SyncService(odoo, farmos, state, orchard_location_id=117,
                       nursery_stock_categories=nursery_cats or set())


def _t(lot, direction, **kw):
    base = dict(lot=lot, direction=direction, product_name="Tree", date=f"2026-06-06 1{lot[-1]}:00:00")
    base.update(kw)
    return Transfer(**base)


# ---------------------------------------------------------------------------

def test_move_in_creates_tree(tmp_path):
    odoo = FakeOdoo(moves_in=[_t("L1", "in", category_name="Plants / Trees")])
    farmos = FakeFarmOS()
    counts = _service(odoo, farmos, tmp_path).run_once()
    assert counts["created"] == 1
    assert farmos.trees[0]["odoo_lot"] == "L1"
    assert farmos.trees[0]["attributes"]["tenure"] == "permanent"


def test_move_in_sets_nursery_stock_tenure(tmp_path):
    odoo = FakeOdoo(moves_in=[_t("L1", "in", category_name="Plants / Nursery Stock")])
    farmos = FakeFarmOS()
    _service(odoo, farmos, tmp_path, nursery_cats={"Plants / Nursery Stock"}).run_once()
    assert farmos.trees[0]["attributes"]["tenure"] == "nursery_stock"


def test_move_in_is_idempotent(tmp_path):
    # Tree with lot L1 already exists — must skip, not duplicate.
    odoo = FakeOdoo(moves_in=[_t("L1", "in")])
    farmos = FakeFarmOS(existing=[{"id": "x", "odoo_lot": "L1", "status": "active"}])
    counts = _service(odoo, farmos, tmp_path).run_once()
    assert counts["created"] == 0
    assert counts["skipped"] == 1
    assert len(farmos.trees) == 1


def test_move_out_archives_active_tree(tmp_path):
    odoo = FakeOdoo(moves_out=[_t("L1", "out")])
    farmos = FakeFarmOS(existing=[{"id": "x", "odoo_lot": "L1", "status": "active"}])
    counts = _service(odoo, farmos, tmp_path).run_once()
    assert counts["archived"] == 1
    assert farmos.trees[0]["status"] == "archived"


def test_move_out_noop_when_no_active_tree(tmp_path):
    odoo = FakeOdoo(moves_out=[_t("L9", "out")])
    farmos = FakeFarmOS()
    counts = _service(odoo, farmos, tmp_path).run_once()
    assert counts["archived"] == 0
    assert counts["skipped"] == 1


def test_cursor_advances_to_latest_move_date(tmp_path):
    odoo = FakeOdoo(moves_in=[_t("L1", "in"), _t("L2", "in")])
    farmos = FakeFarmOS()
    svc = _service(odoo, farmos, tmp_path)
    svc.run_once()
    # L2 has the later synthetic date (…12:00:00 vs …11:00:00)
    assert svc._state.load_cursor() == "2026-06-06 12:00:00"


def test_full_lifecycle_in_then_out(tmp_path):
    # Move in creates; a later move out archives the same lot.
    farmos = FakeFarmOS()
    _service(FakeOdoo(moves_in=[_t("L1", "in")]), farmos, tmp_path).run_once()
    assert farmos.trees[0]["status"] == "active"

    _service(FakeOdoo(moves_out=[_t("L1", "out")]), farmos, tmp_path).run_once()
    assert farmos.trees[0]["status"] == "archived"
