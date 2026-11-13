# AgriforestryOS — farmOS → PostGIS ETL

Mirrors farmOS asset geometries into a PostGIS spatial database (Sprint 5).
This is the **spatial mirror** in the AgriforestryOS architecture:

```
farmOS (system of record)  ──ETL──►  PostGIS (spatial mirror)  ──►  QGIS live layers
                                              ▲                       Claude spatial_query (MCP)
                                              └── ST_DWithin, ST_Intersects, …
```

farmOS stores asset geometries, but answering *"which trees are within 30 m of
the well?"* against JSON:API is slow and awkward. The ETL keeps a PostGIS copy
in step so QGIS can draw **live** layers and the farmOS MCP server can run real
spatial SQL.

## What it does

Each pass, for every mirrored asset type (Tree, Infrastructure, Tree Planting,
Land), it:

1. Fetches all assets from the farmOS JSON:API (paginated, with relationships).
2. Flattens each to a row — scalar attributes + relationship names + the
   `intrinsic_geometry` WKT.
3. **Upserts** into the matching PostGIS table, keyed on the farmOS asset UUID.
   Geometry (WGS84 WKT) is reprojected to **EPSG:26917** in-database via
   `ST_Transform(ST_GeomFromText(wkt, 4326), 26917)` so spatial queries return
   metres.
4. **Prunes** rows whose asset is no longer in farmOS (archived/deleted).

Idempotent: re-running converges the mirror to match farmOS exactly — no
duplicates, no stale rows.

## Tables (`schema.sql`)

`trees`, `infrastructure`, `plantings`, `land_areas` — each with `asset_uuid`
(PK / back-reference), type-specific columns, a GiST-indexed `geom`
(EPSG:26917), and `synced_at`.

## Configuration

| Var | Purpose |
|---|---|
| `FARMOS_BASE_URL`, `FARMOS_USERNAME`, `FARMOS_PASSWORD` | farmOS JSON:API (basic auth) |
| `POSTGIS_DSN` | libpq DSN, e.g. `postgresql://farm:farm@localhost:5433/agriforestryos` |
| `ETL_INTERVAL_SECONDS` | Poll interval (default `900` = 15 min) |
| `LOG_LEVEL` | `INFO` (default) / `DEBUG` |

## Running

```bash
# Bring up PostGIS (compose override) — port 5433, schema auto-created by the ETL
cd docker && docker compose \
  -f docker-compose.development.yml \
  -f docker-compose.postgis.yml up -d postgis

# Continuous poll loop
uv run --project postgis-etl --env-file postgis-etl/.env python postgis-etl/etl.py

# Single pass (cron / CI smoke)
uv run --project postgis-etl --env-file postgis-etl/.env python postgis-etl/etl.py --once
```

### Docker

```bash
docker build -t agriforestryos-postgis-etl postgis-etl/
docker run --env-file postgis-etl/.env agriforestryos-postgis-etl
```

## Development

```bash
# Tests (no live farmOS or PostGIS — faked / fake-cursor)
uv run --project postgis-etl pytest postgis-etl/tests/ -v
```

## Module layout

| File | Responsibility |
|---|---|
| `schema.sql` | PostGIS DDL (4 tables, GiST indexes) |
| `farmos.py` | Minimal paginated JSON:API read client |
| `extract.py` | Pure transforms: asset specs + `asset_to_row` |
| `db.py` | psycopg connection, schema bootstrap, upsert/prune (reprojection) |
| `etl.py` | `ETLService` orchestration + poll-loop entry point |
