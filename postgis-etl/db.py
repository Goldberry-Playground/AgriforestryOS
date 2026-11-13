"""
PostGIS access layer for the ETL.

Bootstraps the schema and performs idempotent upserts keyed on the farmOS
asset UUID. Geometry arrives as WGS84 WKT and is reprojected to EPSG:26917
in-database via ST_Transform(ST_GeomFromText(wkt, 4326), 26917).
"""
from __future__ import annotations

from pathlib import Path

import psycopg

_SCHEMA_SQL = Path(__file__).parent / "schema.sql"


class PostGISDB:
    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("dsn is required")
        self._dsn = dsn

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def ensure_schema(self, conn: psycopg.Connection) -> None:
        """Create the PostGIS extension + tables if absent (idempotent)."""
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL.read_text())
        conn.commit()

    def upsert(self, conn: psycopg.Connection, table: str, rows: list[dict]) -> int:
        """Upsert rows into `table`, keyed on asset_uuid. Returns rows written.

        Each row dict has `asset_uuid`, `wkt`, and the table's columns. The
        geometry column `geom` is set from ST_Transform(ST_GeomFromText(wkt,
        4326), 26917). On UUID conflict, all non-key columns are refreshed and
        synced_at bumped to now().
        """
        if not rows:
            return 0

        # Columns common to every row (excluding wkt, which feeds geom).
        cols = [c for c in rows[0] if c != "wkt"]
        insert_cols = cols + ["geom"]
        placeholders = [f"%({c})s" for c in cols] + [
            "ST_Transform(ST_GeomFromText(%(wkt)s, 4326), 26917)"
        ]
        update_cols = [c for c in cols if c != "asset_uuid"]
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        set_clause = (set_clause + ", " if set_clause else "") + "geom = EXCLUDED.geom, synced_at = now()"

        sql = (
            f"INSERT INTO {table} ({', '.join(insert_cols)}) "
            f"VALUES ({', '.join(placeholders)}) "
            f"ON CONFLICT (asset_uuid) DO UPDATE SET {set_clause}"
        )
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
        return len(rows)

    def prune(self, conn: psycopg.Connection, table: str, live_uuids: list[str]) -> int:
        """Delete rows whose asset_uuid is no longer present in farmOS.

        Keeps the mirror in step when assets are archived/deleted upstream.
        Returns the number of rows removed.
        """
        with conn.cursor() as cur:
            if live_uuids:
                cur.execute(
                    f"DELETE FROM {table} WHERE asset_uuid <> ALL(%s)", (live_uuids,)
                )
            else:
                cur.execute(f"DELETE FROM {table}")
            removed = cur.rowcount
        conn.commit()
        return removed
