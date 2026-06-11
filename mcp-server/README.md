# AgriforestryOS MCP Server

Read-only [FastMCP](https://github.com/jlowin/fastmcp) server that exposes AgriforestryOS farm data to Claude via five curated JSON:API tools.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- A running AgriforestryOS farmOS instance with `jsonapi` and `basic_auth` modules enabled

## Install and register with Claude

```bash
# Register the server with Claude Code
claude mcp add agriforestryos-mcp -- uv run --project /absolute/path/to/AgriforestryOS/mcp-server agriforestryos-mcp
```

Add credentials to `~/.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "agriforestryos-mcp": {
      "env": {
        "FARMOS_BASE_URL": "http://localhost",
        "FARMOS_USERNAME": "admin",
        "FARMOS_PASSWORD": "your-password"
      }
    }
  }
}
```

Or use a `.env` file for local development:

```bash
# mcp-server/.env  (gitignored)
FARMOS_BASE_URL=http://localhost
FARMOS_USERNAME=admin
FARMOS_PASSWORD=your-password
```

```bash
uv run --project mcp-server --env-file mcp-server/.env agriforestryos-mcp
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `FARMOS_BASE_URL` | Yes | Base URL of your farmOS instance (e.g. `http://localhost`) |
| `FARMOS_USERNAME` | Yes | farmOS username |
| `FARMOS_PASSWORD` | Yes | farmOS password |
| `FARMOS_AUTH_MODE` | No | `basic` (default). Reserved for `oauth2` in v1.1. |
| `POSTGIS_DSN` | No | libpq DSN for the PostGIS mirror, e.g. `postgresql://farm:farm@localhost:5433/agriforestryos`. Enables `spatial_query`; the other tools work without it. |

## Tool reference

### `list_asset_types`

Lists all registered asset bundle types in the farmOS instance.

- **Parameters:** none
- **Returns:** `[{"id": "tree", "label": "Tree"}, ...]`
- **When to use:** Discover what asset types are available before querying.

### `count_trees`

Counts Tree assets matching optional filters.

- **Parameters:** `species`, `stratum`, `planting_year` (all optional)
- **Returns:** `{"count": 42, "filters_applied": {"species": "American Chestnut"}}`
- **When to use:** "How many chestnuts did we plant in 2025?"

### `query_trees`

Returns a list of Tree assets with optional filters and configurable fields.

- **Parameters:** `species`, `min_dbh_cm`, `max_dbh_cm`, `stratum`, `limit` (default 50, max 500), `fields` (sparse fieldset override)
- **Returns:** List of flat attribute dicts with resolved relationship names
- **When to use:** "Show me all trees in the high canopy stratum with DBH over 10cm."

### `get_tree`

Fetches a single Tree asset by UUID.

- **Parameters:** `id` (UUID string, required)
- **Returns:** Flat attribute dict
- **When to use:** When you have a specific tree's UUID and need full details.

### `list_infrastructure`

Lists Infrastructure assets with optional condition/type filters.

- **Parameters:** `condition` (`new`, `good`, `fair`, `needs_repair`, `decommissioned`), `infrastructure_type` (name string)
- **Returns:** List of flat attribute dicts
- **When to use:** "What infrastructure needs repair?" or "List all fence lines."

### `spatial_query` (PostGIS mirror — Sprint 5)

Finds assets near a point, ordered nearest-first, using the PostGIS spatial
mirror. Distances are in metres.

- **Parameters:** `asset_type` (`trees`, `infrastructure`, `plantings`, `land_areas`), `lat`, `lon` (WGS84), `within_m` (optional radius — omit for nearest-N), `limit` (default 20)
- **Returns:** List of asset dicts each with a `distance_m` field, nearest first
- **When to use:** "What trees are within 30 m of the well?" (radius) or "the 5 nearest infrastructure items to this spot" (nearest-N)
- **Requires:** `POSTGIS_DSN` set and the farmOS→PostGIS ETL (`postgis-etl/`) populated. Without it the tool returns a clear error; the other five tools are unaffected.

### `list_harvests` (Sprint 6 — yield tracking)

Lists harvest logs with their harvested assets and quantities.

- **Parameters:** `asset_id` (filter to one asset's harvests), `since` / `until` (ISO timestamps), `limit` (default 50)
- **Returns:** `[{id, name, timestamp, status, notes, assets: [names], quantities: [{value, units, measure, label}]}]`, newest first
- **When to use:** "What did we harvest from the Apple tree?" or "harvests since June"

### `harvest_summary` (Sprint 6 — yield tracking)

Aggregates harvest quantities by a dimension.

- **Parameters:** `group_by` — `asset`, `month` (YYYY-MM), or `measure` (count / weight / …)
- **Returns:** `[{group, total_value, harvest_count}]`, sorted by group
- **When to use:** "How much have we harvested per month this season?"

## Example session

```
User: How many American Chestnut trees are in the orchard?

Claude: [calls count_trees(species="American Chestnut")]
There are 12 American Chestnut trees recorded in AgriforestryOS.

User: Show me the ones with a DBH greater than 20cm.

Claude: [calls query_trees(species="American Chestnut", min_dbh_cm=20)]
Found 3 trees with DBH > 20cm:
- Chestnut Row A - Tree 1: dbh_cm=25.5, height_m=6.2, stratum_name=High Canopy
- Chestnut Row A - Tree 3: dbh_cm=22.1, height_m=5.8, stratum_name=High Canopy
- Orchard North - Block 2 - Tree 4: dbh_cm=28.0, height_m=7.1, stratum_name=Emergent

User: What infrastructure needs repair?

Claude: [calls list_infrastructure(condition="needs_repair")]
1 item needs repair:
- Test Fence (Fence Perimeter) — installed 2024-01-15, wood construction
```

## GeoJSON export → QGIS (Sprint 4)

`export_geojson.py` pulls Tree, Infrastructure, and Tree Planting assets from
the farmOS JSON:API and writes one GeoJSON FeatureCollection per type. It
converts each asset's `intrinsic_geometry` (WKT, WGS84) to GeoJSON and
flattens relationship indirection (species / stratum / health /
infrastructure_type) into flat feature properties for styling and labels.

```bash
# Export all three layers (default: ./qgis_layers/)
uv run --project mcp-server --env-file mcp-server/.env \
  python mcp-server/export_geojson.py

# Custom output directory
uv run --project mcp-server --env-file mcp-server/.env \
  python mcp-server/export_geojson.py --out /path/to/layers
```

Output (EPSG:4326 / CRS84 — QGIS reprojects to the project CRS on load):
- `trees.geojson` — points
- `infrastructure.geojson` — mixed geometry (points, lines, polygons)
- `plantings.geojson` — polygons / lines

Assets with no usable geometry (e.g. a planned tree with null coordinates)
are skipped and reported in the run summary rather than aborting the export.

### Loading into QGIS

`load_qgis_layers.py` builds a self-contained PyQGIS script that adds the
three layers with styling matching the `GoldberryGrove_BasePlan` conventions
(layers tagged `[farmOS]` to distinguish them from hand-drawn planning
layers). Drive it via the QGIS MCP `execute_code` tool:

```bash
# Print the load script (paste into QGIS MCP execute_code, or QGIS console)
uv run --project mcp-server python mcp-server/load_qgis_layers.py \
  --dir mcp-server/qgis_layers
```

The reload is idempotent — re-running replaces the `[farmOS]` layers in place,
so re-exporting after farmOS edits and re-loading refreshes the map.

## v1.1 preview

Write tools (`create_tree`, `update_tree`, `archive_tree`) are planned for v1.1 once the read tools are validated against real Goldberry Grove data. Authentication will migrate to OAuth2 client credentials flow for production use.

## Development

```bash
# Run tests (no live farmOS required — all mocked)
uv run --project mcp-server pytest mcp-server/tests/ -v

# Import smoke test
FARMOS_BASE_URL=http://localhost FARMOS_USERNAME=test FARMOS_PASSWORD=test \
  uv run --project mcp-server python3 -c "import server; print('ok')"
```
