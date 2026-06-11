"""
Spatial queries against the PostGIS mirror (Sprint 5).

Backs the `spatial_query` MCP tool. The SQL builder is pure and unit-tested;
execution is a thin psycopg wrapper. Geometry in the mirror is EPSG:26917, so
distances come back in metres. The query point arrives as WGS84 lat/lon and is
transformed in-DB.

Safety: the asset type selects from a fixed allow-list of tables/columns —
never interpolated from arbitrary input — and all values are bound parameters,
so there is no SQL-injection surface.
"""
from __future__ import annotations

# asset_type → (table, display columns). Allow-list: anything not here is rejected.
_TABLES: dict[str, tuple[str, list[str]]] = {
    "trees": ("trees", ["asset_uuid", "name", "species", "variety", "dbh_cm", "height_m", "tenure"]),
    "infrastructure": ("infrastructure", ["asset_uuid", "name", "infrastructure_type", "condition"]),
    "plantings": ("plantings", ["asset_uuid", "name", "planting_type"]),
    "land_areas": ("land_areas", ["asset_uuid", "name", "land_type"]),
}

ASSET_TYPES = tuple(_TABLES)


def build_spatial_query(
    asset_type: str,
    lat: float,
    lon: float,
    within_m: float | None = None,
    limit: int = 20,
) -> tuple[str, dict]:
    """Build the (sql, params) for a nearest-first spatial query.

    Finds assets of `asset_type` ordered by distance from (lat, lon); if
    `within_m` is given, restricts to that radius (ST_DWithin, index-assisted).
    Returns each row's columns plus `distance_m`.

    Raises ValueError for an unknown asset_type or a non-positive limit.
    """
    if asset_type not in _TABLES:
        raise ValueError(
            f"unknown asset_type {asset_type!r}; expected one of {', '.join(ASSET_TYPES)}"
        )
    if limit <= 0:
        raise ValueError("limit must be positive")

    table, cols = _TABLES[asset_type]
    col_list = ", ".join(f"t.{c}" for c in cols)

    where = ["t.geom IS NOT NULL"]
    params: dict = {"lat": lat, "lon": lon, "limit": int(limit)}
    if within_m is not None:
        where.append("ST_DWithin(t.geom, q.pt, %(within_m)s)")
        params["within_m"] = float(within_m)

    sql = (
        "WITH q AS ("
        "SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326), 26917) AS pt"
        ") "
        f"SELECT {col_list}, round(ST_Distance(t.geom, q.pt)::numeric, 1) AS distance_m "
        f"FROM {table} t, q "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY t.geom <-> q.pt "
        "LIMIT %(limit)s"
    )
    return sql, params


def run_spatial_query(dsn: str, asset_type: str, lat: float, lon: float,
                      within_m: float | None = None, limit: int = 20) -> list[dict]:
    """Execute a spatial query against PostGIS and return rows as dicts.

    Imports psycopg lazily so the MCP server (and its other tools) work even
    when psycopg / PostGIS aren't available.
    """
    import psycopg
    from psycopg.rows import dict_row

    sql, params = build_spatial_query(asset_type, lat, lon, within_m, limit)
    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    # Decimal → float for clean JSON serialization
    import decimal
    return [
        {k: (float(v) if isinstance(v, decimal.Decimal) else v) for k, v in r.items()}
        for r in rows
    ]
