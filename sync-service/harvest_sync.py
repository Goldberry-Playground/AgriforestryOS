"""
Harvest → Odoo receipt sync (Sprint 6, farmOS → Odoo, event-driven).

The reverse of the nursery sync: when a harvest is logged in farmOS, record the
produced goods in Odoo so orchard output lands in the ERP for sales/inventory.

Model decision (flagged for review): a harvest is *production*, so each
harvested quantity becomes an Odoo `stock.move` from the virtual Production
location into the stock location, for the matching product. The farmOS harvest
log UUID is stamped as the move `origin`, which is also the idempotency key —
re-running never double-records (Odoo itself is the dedup source of truth).

Product mapping is best-effort by name (quantity label → product). Unmatched
products are skipped and logged rather than guess-created.

Pure flatten/map functions are unit-tested; the Odoo/farmOS I/O is faked.
"""
from __future__ import annotations

import argparse
import logging
import os
import time

log = logging.getLogger("harvest_odoo_sync")


# ---------------------------------------------------------------------------
# Pure transforms (no I/O)
# ---------------------------------------------------------------------------

def quantity_value(attrs: dict) -> float | None:
    """Normalize a farmOS quantity `value` (fraction form) to a number."""
    v = attrs.get("value")
    if v is None:
        return None
    if isinstance(v, dict):
        if v.get("decimal") not in (None, ""):
            try:
                return float(v["decimal"])
            except (TypeError, ValueError):
                pass
        num, den = v.get("numerator"), v.get("denominator")
        if num is not None and den:
            try:
                return float(num) / float(den)
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _index_names(included: list) -> dict[str, str]:
    return {
        inc["id"]: inc.get("attributes", {}).get("name")
        for inc in included
        if inc.get("id") and inc.get("attributes", {}).get("name")
    }


def harvest_to_receipts(log_record: dict, included: list) -> list[dict]:
    """Map one farmOS harvest log → a list of Odoo receipt intents.

    One intent per quantity on the log:
      {log_uuid, date, product_hint, quantity, unit}

    `product_hint` is the quantity label (the crop), falling back to the first
    harvested asset's name. Quantities with no numeric value are dropped.
    """
    names = _index_names(included)
    resources = {inc["id"]: inc for inc in included if inc.get("id")}
    attrs = log_record.get("attributes", {})
    rels = log_record.get("relationships", {})
    log_uuid = log_record.get("id")
    date = attrs.get("timestamp")

    asset_names = [
        names[r["id"]]
        for r in _rel_list(rels.get("asset"))
        if r["id"] in names
    ]
    fallback = asset_names[0] if asset_names else None

    receipts = []
    for ref in _rel_list(rels.get("quantity")):
        q = resources.get(ref["id"])
        if not q:
            continue
        qa = q.get("attributes", {})
        val = quantity_value(qa)
        if val is None:
            continue
        unit_ref = q.get("relationships", {}).get("units", {}).get("data")
        receipts.append({
            "log_uuid": log_uuid,
            "date": date,
            "product_hint": qa.get("label") or fallback,
            "quantity": val,
            "unit": names.get(unit_ref["id"]) if isinstance(unit_ref, dict) and unit_ref else None,
        })
    return receipts


def _rel_list(rel: dict | None) -> list[dict]:
    if not rel:
        return []
    data = rel.get("data")
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class HarvestSyncService:
    def __init__(self, farmos, odoo, state) -> None:
        self._farmos = farmos
        self._odoo = odoo
        self._state = state

    def run_once(self) -> dict:
        """One pass: new harvest logs → Odoo receipts. Returns counts."""
        cursor = self._state.load_cursor()
        body = self._farmos.get_harvests(since=cursor)
        logs = body.get("data", [])
        included = body.get("included", [])

        counts = {"recorded": 0, "skipped_existing": 0, "skipped_no_product": 0}
        max_date = cursor
        for rec in sorted(logs, key=lambda r: r.get("attributes", {}).get("timestamp") or ""):
            ts = rec.get("attributes", {}).get("timestamp")
            for receipt in harvest_to_receipts(rec, included):
                self._record(receipt, counts)
            if ts and (max_date is None or ts > max_date):
                max_date = ts

        if max_date and max_date != cursor:
            self._state.save_cursor(max_date)
        log.info("harvest sync: recorded=%(recorded)d skipped_existing=%(skipped_existing)d "
                 "skipped_no_product=%(skipped_no_product)d", counts)
        return counts

    def _record(self, receipt: dict, counts: dict) -> None:
        origin = f"farmOS:harvest:{receipt['log_uuid']}"
        if self._odoo.harvest_receipt_exists(origin):
            counts["skipped_existing"] += 1
            return
        product_id = self._odoo.find_product_id(receipt["product_hint"]) if receipt["product_hint"] else None
        if not product_id:
            log.warning("no Odoo product for harvest %r — skipped", receipt["product_hint"])
            counts["skipped_no_product"] += 1
            return
        self._odoo.create_harvest_receipt(
            product_id=product_id, quantity=receipt["quantity"],
            date=receipt["date"], origin=origin,
        )
        counts["recorded"] += 1


def build_service_from_env():
    from farmos_writer import FarmOSWriter
    from odoo_client import OdooClient
    from state import SyncState

    required = ["FARMOS_BASE_URL", "FARMOS_USERNAME", "FARMOS_PASSWORD",
                "ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASSWORD"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing env vars: {', '.join(missing)}")

    farmos = FarmOSWriter(os.environ["FARMOS_BASE_URL"], os.environ["FARMOS_USERNAME"],
                          os.environ["FARMOS_PASSWORD"])
    odoo = OdooClient(os.environ["ODOO_URL"], os.environ["ODOO_DB"],
                      os.environ["ODOO_USER"], os.environ["ODOO_PASSWORD"])
    state = SyncState(os.environ.get("HARVEST_SYNC_STATE_FILE", "/data/harvest_sync_state.json"))
    return HarvestSyncService(farmos, odoo, state)


def main() -> None:
    parser = argparse.ArgumentParser(description="farmOS harvest → Odoo receipt sync.")
    parser.add_argument("--once", action="store_true", help="Single pass then exit.")
    parser.add_argument("--interval", type=int,
                        default=int(os.environ.get("HARVEST_POLL_SECONDS", "900")))
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    service = build_service_from_env()
    if args.once:
        service.run_once()
        return
    log.info("starting harvest-sync poll loop (every %ds)", args.interval)
    while True:
        try:
            service.run_once()
        except Exception:  # noqa: BLE001
            log.exception("harvest sync pass failed; retry next interval")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
