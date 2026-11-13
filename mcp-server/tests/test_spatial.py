"""Tests for the spatial query builder + runner (PostGIS mirror)."""
import decimal
import sys
import types

import pytest

import spatial


# ---------------------------------------------------------------------------
# build_spatial_query — pure SQL builder
# ---------------------------------------------------------------------------

def test_within_radius_uses_st_dwithin():
    sql, params = spatial.build_spatial_query("trees", 38.30, -80.79, within_m=30, limit=10)
    assert "ST_DWithin(t.geom, q.pt, %(within_m)s)" in sql
    assert params["within_m"] == 30.0
    assert params["lat"] == 38.30 and params["lon"] == -80.79
    assert params["limit"] == 10
    # point transformed from WGS84 → 26917 in-DB
    assert "ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)" in sql
    assert "ST_Transform(" in sql and "26917" in sql
    assert "FROM trees t" in sql
    assert "ORDER BY t.geom <-> q.pt" in sql  # KNN, index-assisted


def test_nearest_n_omits_dwithin():
    sql, params = spatial.build_spatial_query("infrastructure", 38.3, -80.8, within_m=None, limit=5)
    assert "ST_DWithin" not in sql
    assert "within_m" not in params
    assert "FROM infrastructure t" in sql
    assert params["limit"] == 5


def test_distance_m_selected():
    sql, _ = spatial.build_spatial_query("trees", 38.3, -80.8)
    assert "ST_Distance(t.geom, q.pt)" in sql
    assert "AS distance_m" in sql


def test_columns_are_allowlisted_per_type():
    sql_t, _ = spatial.build_spatial_query("trees", 0, 0)
    assert "t.species" in sql_t and "t.tenure" in sql_t
    sql_i, _ = spatial.build_spatial_query("infrastructure", 0, 0)
    assert "t.infrastructure_type" in sql_i
    assert "species" not in sql_i  # no cross-table column bleed


def test_unknown_asset_type_rejected():
    with pytest.raises(ValueError, match="unknown asset_type"):
        spatial.build_spatial_query("'; DROP TABLE trees; --", 0, 0)


def test_nonpositive_limit_rejected():
    with pytest.raises(ValueError, match="limit must be positive"):
        spatial.build_spatial_query("trees", 0, 0, limit=0)


def test_asset_types_constant():
    assert set(spatial.ASSET_TYPES) == {"trees", "infrastructure", "plantings", "land_areas"}


# ---------------------------------------------------------------------------
# run_spatial_query — execution against a fake psycopg
# ---------------------------------------------------------------------------

class _FakeCursor:
    def __init__(self, rows): self._rows = rows; self.executed = None
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def execute(self, sql, params): self.executed = (sql, params)
    def fetchall(self): return self._rows

class _FakeConn:
    def __init__(self, rows): self._rows = rows
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def cursor(self, row_factory=None): return _FakeCursor(self._rows)


def test_run_spatial_query_converts_decimal(monkeypatch):
    rows = [{"asset_uuid": "t1", "name": "Chestnut",
             "dbh_cm": decimal.Decimal("15.5"), "distance_m": decimal.Decimal("12.3")}]
    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.connect = lambda dsn: _FakeConn(rows)
    fake_rows = types.ModuleType("psycopg.rows")
    fake_rows.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", fake_rows)

    out = spatial.run_spatial_query("dsn", "trees", 38.3, -80.8, within_m=30, limit=10)
    assert out == [{"asset_uuid": "t1", "name": "Chestnut", "dbh_cm": 15.5, "distance_m": 12.3}]
    assert isinstance(out[0]["dbh_cm"], float)  # Decimal → float
