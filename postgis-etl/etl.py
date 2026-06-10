"""
farmOS → PostGIS ETL (Sprint 5).

Mirrors farmOS asset geometries into the PostGIS spatial database so QGIS can
draw live layers and the farmOS MCP server can run spatial queries (ST_DWithin
etc.) without re-fetching from farmOS each time.

Each pass, per asset type: fetch all assets from farmOS JSON:API, flatten to
rows, upsert into PostGIS keyed on asset UUID, and prune rows whose assets no
longer exist upstream. Idempotent — re-running converges the mirror to match
farmOS exactly.

Run:
    uv run --env-file .env python etl.py            # one pass then poll loop
    uv run --env-file .env python etl.py --once     # single pass (cron/CI)
"""
from __future__ import annotations

import argparse
import logging
import os
import time

from db import PostGISDB
from extract import ASSET_SPECS, asset_to_row, build_name_lookup
from farmos import FarmOSReadClient

log = logging.getLogger("farmos_postgis_etl")


class ETLService:
    def __init__(self, farmos: FarmOSReadClient, db: PostGISDB) -> None:
        self._farmos = farmos
        self._db = db

    def run_once(self) -> dict:
        """Run one full mirror pass. Returns per-table counts."""
        conn = self._db.connect()
        try:
            self._db.ensure_schema(conn)
            summary: dict = {}
            for spec in ASSET_SPECS:
                body = self._farmos.fetch_all(spec.endpoint, spec.include)
                names = build_name_lookup(body["included"])
                rows, skipped = [], 0
                for rec in body["data"]:
                    row = asset_to_row(rec, names, spec)
                    if row is None:
                        skipped += 1
                    else:
                        rows.append(row)
                written = self._db.upsert(conn, spec.table, rows)
                pruned = self._db.prune(conn, spec.table, [r["asset_uuid"] for r in rows])
                summary[spec.table] = {"written": written, "skipped_no_geometry": skipped, "pruned": pruned}
                log.info("%s: %d written, %d pruned, %d skipped (no geometry)",
                         spec.table, written, pruned, skipped)
            return summary
        finally:
            conn.close()


def build_service_from_env() -> ETLService:
    required = ["FARMOS_BASE_URL", "FARMOS_USERNAME", "FARMOS_PASSWORD", "POSTGIS_DSN"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")
    farmos = FarmOSReadClient(
        base_url=os.environ["FARMOS_BASE_URL"],
        username=os.environ["FARMOS_USERNAME"],
        password=os.environ["FARMOS_PASSWORD"],
    )
    db = PostGISDB(dsn=os.environ["POSTGIS_DSN"])
    return ETLService(farmos, db)


def main() -> None:
    parser = argparse.ArgumentParser(description="farmOS → PostGIS spatial-mirror ETL.")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit.")
    parser.add_argument("--interval", type=int,
                        default=int(os.environ.get("ETL_INTERVAL_SECONDS", "900")),
                        help="Seconds between passes (default 900 = 15 min).")
    args = parser.parse_args()

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    service = build_service_from_env()

    if args.once:
        service.run_once()
        return

    log.info("starting ETL poll loop (every %ds)", args.interval)
    while True:
        try:
            service.run_once()
        except Exception:  # noqa: BLE001 — never let one bad pass kill the loop
            log.exception("ETL pass failed; will retry next interval")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
