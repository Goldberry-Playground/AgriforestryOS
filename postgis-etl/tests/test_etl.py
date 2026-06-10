"""
ETL orchestration + DB SQL-building tests using in-memory fakes.

No live farmOS or PostGIS: a fake read-client returns canned JSON:API bodies,
and a fake DB records what would be written/pruned. The db.upsert SQL is
exercised against a fake psycopg cursor to verify the reprojection + upsert
shape without a database.
"""
import db as dbmod
from extract import ASSET_SPECS
from etl import ETLService


# --- Fakes -----------------------------------------------------------------

class FakeFarmOS:
    def __init__(self, bodies):
        self._bodies = bodies  # endpoint -> {"data":[...],"included":[...]}

    def fetch_all(self, endpoint, include=None):
        return self._bodies.get(endpoint, {"data": [], "included": []})


class FakeDB:
    def __init__(self):
        self.upserts = {}   # table -> rows
        self.prunes = {}    # table -> live uuids
        self.schema_ensured = False

    def connect(self):
        class _C:
            def close(self): pass
        return _C()

    def ensure_schema(self, conn):
        self.schema_ensured = True

    def upsert(self, conn, table, rows):
        self.upserts[table] = rows
        return len(rows)

    def prune(self, conn, table, live):
        self.prunes[table] = live
        return 0


def test_run_once_mirrors_trees_and_skips_geomless():
    tree_ep = next(s.endpoint for s in ASSET_SPECS if s.table == "trees")
    bodies = {tree_ep: {
        "data": [
            {"id": "t1", "attributes": {"name": "Chestnut",
                "intrinsic_geometry": {"value": "POINT (-80.79 38.30)"}},
             "relationships": {"species": {"data": {"id": "sp1"}}}},
            {"id": "t2", "attributes": {"name": "planned (no geom)"},
             "relationships": {}},
        ],
        "included": [{"id": "sp1", "attributes": {"name": "American Chestnut"}}],
    }}
    farmos, fake = FakeFarmOS(bodies), FakeDB()
    summary = ETLService(farmos, fake).run_once()

    assert fake.schema_ensured
    assert summary["trees"] == {"written": 1, "skipped_no_geometry": 1, "pruned": 0}
    row = fake.upserts["trees"][0]
    assert row["asset_uuid"] == "t1"
    assert row["species"] == "American Chestnut"
    assert fake.prunes["trees"] == ["t1"]   # only the live uuid kept


def test_run_once_handles_empty_collections():
    summary = ETLService(FakeFarmOS({}), FakeDB()).run_once()
    for spec in ASSET_SPECS:
        assert summary[spec.table]["written"] == 0


# --- db.upsert SQL shape (fake cursor) -------------------------------------

class FakeCursor:
    def __init__(self): self.sql = None; self.rows = None
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def execute(self, sql, params=None): self.sql = sql
    def executemany(self, sql, rows): self.sql = sql; self.rows = list(rows)

class FakeConn:
    def __init__(self): self.cur = FakeCursor(); self.committed = False
    def cursor(self): return self.cur
    def commit(self): self.committed = True


def test_upsert_sql_reprojects_and_upserts():
    conn = FakeConn()
    rows = [{"asset_uuid": "t1", "name": "Chestnut", "wkt": "POINT (-80.79 38.30)"}]
    n = dbmod.PostGISDB("dummy").upsert(conn, "trees", rows)
    assert n == 1
    sql = conn.cur.sql
    assert "INSERT INTO trees" in sql
    assert "ST_Transform(ST_GeomFromText(%(wkt)s, 4326), 26917)" in sql
    assert "ON CONFLICT (asset_uuid) DO UPDATE" in sql
    assert "synced_at = now()" in sql
    assert conn.committed
    # wkt feeds geom, not a literal column
    assert "name = EXCLUDED.name" in sql
    assert conn.cur.rows == rows


def test_upsert_noop_on_empty():
    conn = FakeConn()
    assert dbmod.PostGISDB("dummy").upsert(conn, "trees", []) == 0
