"""
Odoo → farmOS sync service (Sprint 4).

Bidirectional, location-driven sync keyed on Odoo lot/serial:

  • Stock move INTO  the Orchard  → create a farmOS Tree asset
                                     (tenure from product category)
  • Stock move OUT of the Orchard → archive the matching Tree asset

Idempotent: a move-in whose lot already exists as a Tree is skipped; a
move-out with no matching active Tree is a no-op. Re-running never
duplicates or double-archives.

Run:
    uv run --env-file .env python sync.py            # one poll then loop
    uv run --env-file .env python sync.py --once     # single pass (for cron/CI)
"""
from __future__ import annotations

import argparse
import logging
import os
import time

from farmos_writer import FarmOSWriter
from mapping import Transfer, build_tree_attributes, determine_tenure
from odoo_client import OdooClient
from state import SyncState

log = logging.getLogger("odoo_farmos_sync")


class SyncService:
    """Orchestrates one or more sync passes between Odoo and farmOS."""

    def __init__(
        self,
        odoo: OdooClient,
        farmos: FarmOSWriter,
        state: SyncState,
        orchard_location_id: int,
        nursery_stock_categories: set[str],
    ) -> None:
        self._odoo = odoo
        self._farmos = farmos
        self._state = state
        self._orchard_id = orchard_location_id
        self._nursery_cats = nursery_stock_categories

    def run_once(self) -> dict:
        """Run a single sync pass. Returns counts {created, archived, skipped}."""
        cursor = self._state.load_cursor()
        moves_in = self._odoo.moves_into_orchard(self._orchard_id, since=cursor)
        moves_out = self._odoo.moves_out_of_orchard(self._orchard_id, since=cursor)

        counts = {"created": 0, "archived": 0, "skipped": 0}
        max_date = cursor

        # Process oldest-first across both directions so the cursor advances
        # monotonically and a mid-batch crash resumes cleanly.
        for transfer in sorted(
            moves_in + moves_out, key=lambda t: t.date or ""
        ):
            if transfer.direction == "in":
                self._handle_move_in(transfer, counts)
            else:
                self._handle_move_out(transfer, counts)
            if transfer.date and (max_date is None or transfer.date > max_date):
                max_date = transfer.date

        if max_date and max_date != cursor:
            self._state.save_cursor(max_date)

        log.info(
            "sync pass complete: created=%(created)d archived=%(archived)d skipped=%(skipped)d",
            counts,
        )
        return counts

    def _handle_move_in(self, transfer: Transfer, counts: dict) -> None:
        # Idempotency: skip if a Tree with this lot already exists.
        if self._farmos.find_tree_by_lot(transfer.lot):
            log.debug("skip move-in: lot %s already synced", transfer.lot)
            counts["skipped"] += 1
            return
        tenure = determine_tenure(transfer.category_name, self._nursery_cats)
        attrs = build_tree_attributes(transfer, tenure)
        self._farmos.create_tree(attrs, species_name=transfer.species)
        log.info("created Tree for lot %s (tenure=%s)", transfer.lot, tenure)
        counts["created"] += 1

    def _handle_move_out(self, transfer: Transfer, counts: dict) -> None:
        tree = self._farmos.find_tree_by_lot(transfer.lot, status="active")
        if not tree:
            log.debug("skip move-out: no active Tree for lot %s", transfer.lot)
            counts["skipped"] += 1
            return
        self._farmos.archive_tree(tree["id"])
        log.info("archived Tree for lot %s (left Orchard)", transfer.lot)
        counts["archived"] += 1


# ---------------------------------------------------------------------------
# Wiring / entry point
# ---------------------------------------------------------------------------

def build_service_from_env() -> SyncService:
    required = [
        "ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASSWORD",
        "FARMOS_BASE_URL", "FARMOS_USERNAME", "FARMOS_PASSWORD",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")

    odoo = OdooClient(
        url=os.environ["ODOO_URL"], db=os.environ["ODOO_DB"],
        username=os.environ["ODOO_USER"], password=os.environ["ODOO_PASSWORD"],
    )
    farmos = FarmOSWriter(
        base_url=os.environ["FARMOS_BASE_URL"],
        username=os.environ["FARMOS_USERNAME"],
        password=os.environ["FARMOS_PASSWORD"],
    )
    state = SyncState(os.environ.get("SYNC_STATE_FILE", "/data/sync_state.json"))

    location_name = os.environ.get("ODOO_ORCHARD_LOCATION", "Orchard")
    explicit_id = os.environ.get("ODOO_ORCHARD_LOCATION_ID")
    orchard_id = int(explicit_id) if explicit_id else odoo.find_location_id(location_name)
    if not orchard_id:
        raise EnvironmentError(
            f"Could not resolve Orchard location '{location_name}'. "
            "Set ODOO_ORCHARD_LOCATION_ID explicitly."
        )

    nursery_cats = {
        c.strip() for c in os.environ.get("NURSERY_STOCK_CATEGORIES", "").split(",") if c.strip()
    }
    return SyncService(odoo, farmos, state, orchard_id, nursery_cats)


def main() -> None:
    parser = argparse.ArgumentParser(description="Odoo → farmOS tree sync.")
    parser.add_argument("--once", action="store_true", help="Run a single pass and exit.")
    parser.add_argument(
        "--interval", type=int, default=int(os.environ.get("POLL_INTERVAL_SECONDS", "900")),
        help="Seconds between polls (default 900 = 15 min).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    service = build_service_from_env()

    if args.once:
        service.run_once()
        return

    log.info("starting poll loop (every %ds)", args.interval)
    while True:
        try:
            service.run_once()
        except Exception:  # noqa: BLE001 — never let one bad pass kill the loop
            log.exception("sync pass failed; will retry next interval")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
