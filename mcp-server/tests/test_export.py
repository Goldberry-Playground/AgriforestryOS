"""
Tests for export_geojson.py — farmOS → GeoJSON export for QGIS.

Pure-function tests for the WKT parser and feature flattening, plus an
end-to-end export run intercepted by pytest-httpx writing to tmp_path.
"""
import json

import pytest
from pytest_httpx import HTTPXMock

from client import FarmOSClient
import export_geojson as ex


# ---------------------------------------------------------------------------
# WKT → GeoJSON
# ---------------------------------------------------------------------------

def test_wkt_point():
    g = ex.wkt_to_geojson("POINT (-80.7955 38.3015)")
    assert g == {"type": "Point", "coordinates": [-80.7955, 38.3015]}


def test_wkt_point_drops_z():
    g = ex.wkt_to_geojson("POINT Z (-80.7955 38.3015 100)")
    assert g == {"type": "Point", "coordinates": [-80.7955, 38.3015]}


def test_wkt_linestring():
    g = ex.wkt_to_geojson("LINESTRING (-80.79 38.30, -80.78 38.31)")
    assert g["type"] == "LineString"
    assert g["coordinates"] == [[-80.79, 38.30], [-80.78, 38.31]]


def test_wkt_polygon():
    g = ex.wkt_to_geojson(
        "POLYGON ((-80.79 38.30, -80.78 38.30, -80.78 38.31, -80.79 38.30))"
    )
    assert g["type"] == "Polygon"
    assert len(g["coordinates"]) == 1
    assert g["coordinates"][0][0] == [-80.79, 38.30]


def test_wkt_polygon_with_hole():
    g = ex.wkt_to_geojson(
        "POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0), (1 1, 2 1, 2 2, 1 1))"
    )
    assert g["type"] == "Polygon"
    assert len(g["coordinates"]) == 2  # outer ring + hole


def test_wkt_multipolygon():
    g = ex.wkt_to_geojson(
        "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 0)), ((2 2, 3 2, 3 3, 2 2)))"
    )
    assert g["type"] == "MultiPolygon"
    assert len(g["coordinates"]) == 2


def test_wkt_empty_returns_none():
    assert ex.wkt_to_geojson("") is None
    assert ex.wkt_to_geojson(None) is None


def test_wkt_garbage_returns_none():
    assert ex.wkt_to_geojson("not wkt at all") is None


# ---------------------------------------------------------------------------
# Geometry extraction
# ---------------------------------------------------------------------------

def test_extract_prefers_intrinsic_geometry():
    attrs = {
        "intrinsic_geometry": {"value": "POINT (-80.79 38.30)"},
        "geometry": {"value": "POINT (0 0)"},
    }
    g = ex.extract_geometry(attrs)
    assert g["coordinates"] == [-80.79, 38.30]


def test_extract_falls_back_to_geometry():
    attrs = {"geometry": {"value": "POINT (-80.79 38.30)"}}
    assert ex.extract_geometry(attrs)["coordinates"] == [-80.79, 38.30]


def test_extract_none_when_no_geometry():
    assert ex.extract_geometry({"name": "x"}) is None


# ---------------------------------------------------------------------------
# Feature flattening
# ---------------------------------------------------------------------------

def test_to_features_flattens_relationships_and_skips_geomless():
    records = [
        {
            "id": "uuid-1",
            "attributes": {
                "name": "Chestnut A1",
                "dbh_cm": "15.50",
                "intrinsic_geometry": {"value": "POINT (-80.79 38.30)"},
            },
            "relationships": {
                "species": {"data": {"id": "sp-1"}},
                "stratum": {"data": {"id": "st-1"}},
            },
        },
        {  # no geometry — must be skipped
            "id": "uuid-2",
            "attributes": {"name": "Planned tree"},
            "relationships": {},
        },
    ]
    lookup = {"sp-1": "American Chestnut", "st-1": "High Canopy"}
    spec = ex.EXPORT_SPECS["tree"]

    features, skipped = ex.to_features(records, lookup, spec)

    assert skipped == 1
    assert len(features) == 1
    f = features[0]
    assert f["properties"]["name"] == "Chestnut A1"
    assert f["properties"]["dbh_cm"] == "15.50"
    assert f["properties"]["species_name"] == "American Chestnut"
    assert f["properties"]["stratum_name"] == "High Canopy"
    assert f["geometry"]["type"] == "Point"


def test_tenure_is_carried_to_feature_properties():
    # Regression: tenure must reach the GeoJSON so QGIS can style nursery
    # stock distinctly. The E2E pipeline test caught this when tenure was
    # added to the Tree asset but not to the export spec.
    assert "tenure" in ex.EXPORT_SPECS["tree"]["properties"]
    records = [{
        "id": "t-1",
        "attributes": {
            "name": "Redbud A1", "tenure": "nursery_stock",
            "intrinsic_geometry": {"value": "POINT (-80.79 38.30)"},
        },
        "relationships": {},
    }]
    features, _ = ex.to_features(records, {}, ex.EXPORT_SPECS["tree"])
    assert features[0]["properties"]["tenure"] == "nursery_stock"


def test_feature_collection_has_crs():
    fc = ex.feature_collection([])
    assert fc["type"] == "FeatureCollection"
    assert "CRS84" in fc["crs"]["properties"]["name"]


# ---------------------------------------------------------------------------
# End-to-end export (httpx-mocked, writes to tmp_path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_writes_three_files(httpx_mock: HTTPXMock, tmp_path, monkeypatch):
    monkeypatch.setenv("FARMOS_BASE_URL", "http://farmos.local")
    monkeypatch.setenv("FARMOS_USERNAME", "admin")
    monkeypatch.setenv("FARMOS_PASSWORD", "admin")

    tree_resp = {
        "data": [{
            "id": "t-1",
            "attributes": {
                "name": "Chestnut A1",
                "dbh_cm": "15.50",
                "intrinsic_geometry": {"value": "POINT (-80.7955 38.3015)"},
            },
            "relationships": {"species": {"data": {"id": "sp-1"}}},
        }],
        "included": [
            {"id": "sp-1", "attributes": {"name": "American Chestnut"}}
        ],
        "links": {},
    }
    empty = {"data": [], "included": [], "links": {}}

    # EXPORT_SPECS is ordered tree → infrastructure → tree_planting, so a
    # single page each fires in that order; FIFO response matching suffices.
    httpx_mock.add_response(method="GET", json=tree_resp)
    httpx_mock.add_response(method="GET", json=empty)
    httpx_mock.add_response(method="GET", json=empty)

    summary = await ex.export(tmp_path)

    assert summary["tree"]["count"] == 1
    assert (tmp_path / "trees.geojson").exists()
    assert (tmp_path / "infrastructure.geojson").exists()
    assert (tmp_path / "plantings.geojson").exists()

    trees = json.loads((tmp_path / "trees.geojson").read_text())
    assert trees["type"] == "FeatureCollection"
    assert trees["features"][0]["properties"]["species_name"] == "American Chestnut"
    assert trees["features"][0]["geometry"]["coordinates"] == [-80.7955, 38.3015]
