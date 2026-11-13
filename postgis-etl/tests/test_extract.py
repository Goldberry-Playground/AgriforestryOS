"""Pure-function tests for the farmOS → row extraction layer."""
from extract import (ASSET_SPECS, asset_to_row, build_name_lookup, extract_wkt)


def _spec(asset_type):
    return next(s for s in ASSET_SPECS if s.asset_type == asset_type)


# ---------------------------------------------------------------------------
# extract_wkt
# ---------------------------------------------------------------------------

def test_extract_wkt_prefers_intrinsic():
    attrs = {"intrinsic_geometry": {"value": "POINT (-80.79 38.30)"},
             "geometry": {"value": "POINT (0 0)"}}
    assert extract_wkt(attrs) == "POINT (-80.79 38.30)"


def test_extract_wkt_falls_back():
    assert extract_wkt({"geometry": {"value": "POINT (1 2)"}}) == "POINT (1 2)"


def test_extract_wkt_none_when_absent():
    assert extract_wkt({"name": "x"}) is None
    assert extract_wkt({"intrinsic_geometry": {"value": ""}}) is None


# ---------------------------------------------------------------------------
# build_name_lookup
# ---------------------------------------------------------------------------

def test_name_lookup():
    inc = [{"id": "t1", "attributes": {"name": "American Chestnut"}},
           {"id": "t2", "attributes": {"name": "High Canopy"}},
           {"id": "t3", "attributes": {}}]  # no name → skipped
    lut = build_name_lookup(inc)
    assert lut == {"t1": "American Chestnut", "t2": "High Canopy"}


# ---------------------------------------------------------------------------
# asset_to_row
# ---------------------------------------------------------------------------

def test_tree_row_flattens_attrs_and_relationships():
    rec = {
        "id": "tree-uuid-1",
        "attributes": {
            "name": "Chestnut A1", "variety": "Dunstan", "dbh_cm": "15.5",
            "tenure": "permanent", "odoo_lot": "GG-001",
            "intrinsic_geometry": {"value": "POINT (-80.7955 38.3015)"},
        },
        "relationships": {
            "species": {"data": {"id": "sp1"}},
            "stratum": {"data": {"id": "st1"}},
            "succession_stage": {"data": None},
        },
    }
    lut = {"sp1": "American Chestnut", "st1": "High Canopy"}
    row = asset_to_row(rec, lut, _spec("tree"))
    assert row["asset_uuid"] == "tree-uuid-1"
    assert row["wkt"] == "POINT (-80.7955 38.3015)"
    assert row["name"] == "Chestnut A1"
    assert row["variety"] == "Dunstan"
    assert row["tenure"] == "permanent"
    assert row["species"] == "American Chestnut"
    assert row["stratum"] == "High Canopy"
    assert row["succession_stage"] is None   # null relationship → None


def test_row_is_none_without_geometry():
    rec = {"id": "t2", "attributes": {"name": "planned"}, "relationships": {}}
    assert asset_to_row(rec, {}, _spec("tree")) is None


def test_infrastructure_row():
    rec = {
        "id": "infra-1",
        "attributes": {"name": "West Fence", "condition": "good", "material": "wood",
                       "intrinsic_geometry": {"value": "LINESTRING (0 0, 1 1)"}},
        "relationships": {"infrastructure_type": {"data": {"id": "it1"}}},
    }
    row = asset_to_row(rec, {"it1": "Fence Perimeter"}, _spec("infrastructure"))
    assert row["infrastructure_type"] == "Fence Perimeter"
    assert row["condition"] == "good"
    assert row["wkt"].startswith("LINESTRING")


def test_specs_cover_four_tables():
    assert {s.table for s in ASSET_SPECS} == {"trees", "infrastructure", "plantings", "land_areas"}
