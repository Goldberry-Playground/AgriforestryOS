# AgriforestryOS — Odoo ↔ farmOS Sync Service

A small Python service that keeps farmOS Tree assets in step with Odoo
nursery inventory, keyed on Odoo **lot/serial** numbers. It is the
location-driven half of the AgriforestryOS data loop (Sprint 4):

```
Odoo (nursery)                     farmOS                       QGIS
─────────────                      ──────                       ────
move INTO  Orchard  ── sync ──►   Tree asset created   ── export ──►  map layer
move OUT of Orchard ── sync ──►   Tree asset archived             (export_geojson.py)
```

## What it does

**Direction: Odoo → farmOS (location-driven).** Every poll, it asks Odoo for
completed stock-move lines touching the **Orchard** stock location:

- **Move *into* Orchard** → create a farmOS Tree asset.
  - Species relationship resolved/auto-created in the `plant_type` vocabulary.
  - `tenure` set from the product category: `permanent` (orchard planting)
    or `nursery_stock` (alley-crop stock for sale, e.g. eastern redbud
    grown between chestnuts). Nursery stock is styled distinctly on the map.
  - **No geometry** — a transferred tree has no GPS until physically placed;
    it appears in farmOS and lands on the map once coordinates are recorded.
- **Move *out of* Orchard** (sale/removal) → **archive** the matching Tree
  asset. History is preserved; it drops off the active map.

**Idempotent.** The Odoo lot/serial becomes farmOS `odoo_lot` and is the
dedup key. A move-in whose lot already exists is skipped; a move-out with no
matching active Tree is a no-op. Re-running never duplicates or
double-archives. A JSON cursor (`SYNC_STATE_FILE`) tracks the latest
processed move date so each poll only fetches new moves.

> The **reverse** flow — scion-wood / graft harvest logged in farmOS pushing
> inventory *back* to Odoo — is event-driven, not location-driven, and is
> tracked as a separate backlog feature request.

## Configuration

All via environment variables (never hard-coded):

| Var | Purpose |
|---|---|
| `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD` | Odoo XML-RPC auth |
| `FARMOS_BASE_URL`, `FARMOS_USERNAME`, `FARMOS_PASSWORD` | farmOS JSON:API (basic auth) |
| `ODOO_ORCHARD_LOCATION` | Orchard location name (default `Orchard`) |
| `ODOO_ORCHARD_LOCATION_ID` | Skip name lookup; use this id directly |
| `NURSERY_STOCK_CATEGORIES` | Comma-separated Odoo product categories that mean `nursery_stock` |
| `SYNC_STATE_FILE` | Cursor file path (default `/data/sync_state.json`) |
| `POLL_INTERVAL_SECONDS` | Loop interval (default `900` = 15 min) |
| `LOG_LEVEL` | `INFO` (default) / `DEBUG` |

## Running

```bash
# Continuous poll loop (production / docker)
uv run --project sync-service --env-file sync-service/.env python sync-service/sync.py

# Single pass — for cron or CI smoke tests
uv run --project sync-service --env-file sync-service/.env python sync-service/sync.py --once
```

### Docker

```bash
docker build -t agriforestryos-sync sync-service/
docker run --env-file sync-service/.env -v sync_state:/data agriforestryos-sync
```

## Development

```bash
# Tests (no live Odoo or farmOS required — all faked / HTTP-mocked)
uv run --project sync-service pytest sync-service/tests/ -v
```

## Module layout

| File | Responsibility |
|---|---|
| `mapping.py` | Pure transforms: `Transfer`, `determine_tenure`, `build_tree_attributes` |
| `odoo_client.py` | XML-RPC client → normalized `Transfer` objects |
| `farmos_writer.py` | JSON:API writes: create/archive Tree, resolve species term |
| `state.py` | Sync cursor persistence (JSON high-water mark) |
| `sync.py` | `SyncService` orchestration + poll-loop entry point (Odoo → farmOS) |
| `harvest_sync.py` | `HarvestSyncService` — farmOS harvest logs → Odoo production receipts (the reverse direction). Separate entry point `agriforestryos-harvest-sync`. |

## Harvest → Odoo receipt sync

The reverse, event-driven flow (`agriforestryos-harvest-sync`): polls farmOS for
new harvest logs and records each harvested quantity in Odoo as a **production
`stock.move`** (virtual Production → stock), increasing on-hand qty of the
matched product. The farmOS log UUID is the move `origin` and idempotency key.
Products are matched by name (quantity label); unmatched are skipped, not
created. Runs off the same image with `python harvest_sync.py` and its own
`HARVEST_SYNC_STATE_FILE` cursor.

```bash
uv run --project sync-service --env-file sync-service/.env python sync-service/harvest_sync.py --once
```
