# AgriforestryOS

A syntropic agroforestry management platform built on [farmOS 4.x](https://farmOS.org), extended with a QGIS geospatial integration and a Claude AI MCP server. Purpose-built for Goldberry Grove — a syntropic agroforestry operation in West Virginia.

[![Licence](https://img.shields.io/badge/Licence-GPL%202.0-blue.svg)](https://opensource.org/licenses/GPL-2.0/)
[![farmOS](https://img.shields.io/badge/built%20on-farmOS%204.x-green)](https://farmOS.org)

---

## What is AgriforestryOS?

Standard farm management software wasn't designed for syntropic agroforestry — a design system where trees, shrubs, and ground covers are planted together in successional layers, managed over decades, and tracked by canopy stratum, guild membership, and succession stage rather than just crop type and harvest date.

AgriforestryOS extends farmOS with:

- **Tree and Infrastructure asset types** with syntropic-specific fields (stratum, succession stage, DBH, canopy radius, Odoo lot traceability)
- **A farmOS MCP server** that lets Claude query tree inventory, infrastructure, and asset types conversationally
- **QGIS integration** so Claude can load, style, and render farm maps directly from a GIS project via the QGIS MCP plugin
- **An Odoo sync service** (Sprint 4) that mirrors nursery-to-orchard stock transfers into farmOS Tree assets automatically

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Claude (AI)                          │
│                                                             │
│  farmOS MCP server ◄──────────────────► QGIS MCP plugin    │
│  (query trees, infra,                   (load layers,       │
│   asset types)                           style, render map) │
└──────────┬──────────────────────────────────────┬──────────┘
           │                                      │
           ▼                                      ▼
┌──────────────────────┐              ┌─────────────────────┐
│   farmOS (Drupal)    │              │   QGIS Desktop      │
│                      │              │                     │
│  farm_syntropic      │              │  GoldberryGrove_    │
│  module              │              │  BasePlan.qgz       │
│                      │              │  (25 layers + DEM)  │
│  JSON:API            │              │                     │
│  (/jsonapi/*)        │              │  PostGIS (Sprint 5) │
└──────────────────────┘              └─────────────────────┘
           │
           ▼
┌──────────────────────┐
│  Odoo ERP            │
│  (nursery inventory, │
│   stock transfers,   │
│   sales orders)      │
└──────────────────────┘
```

**Layer responsibilities:**

| Layer | Tool | Role |
|---|---|---|
| Farm management | farmOS (Drupal) | Asset records, GPS geometry, activity logs, JSON:API |
| Geospatial | QGIS + PostGIS | Map rendering, spatial queries, placement planning |
| AI interface | Claude + MCP servers | Conversational queries, map generation, data entry |
| ERP | Odoo 19 | Nursery inventory, purchase orders, sales, traceability |

---

## What's Shipped

### `modules/farm_syntropic` — Drupal module

Custom farmOS module providing syntropic-specific asset types and taxonomies.

**Asset types:**

| Type | Geometry | Key fields |
|---|---|---|
| **Tree** | Point (trunk GPS) | species, variety, DBH (cm), height (m), canopy radius (m), stratum, succession stage, health status, planting date, source, Odoo lot/serial |
| **Infrastructure** | Point / LineString / Polygon | infrastructure type, material, capacity, installation date, condition, specifications |
| **Tree Planting** | LineString / Polygon | planting type, tree count, spacing (m), succession stage, design notes |

**Taxonomies:**

| Vocabulary | Terms |
|---|---|
| Syntropic Stratum | Emergent, High Canopy, Low Canopy, Shrub, Herbaceous, Ground Cover, Root/Tuber |
| Succession Stage | Placenta, Accumulation 1, Accumulation 2, Abundance |
| Infrastructure Type | Solar Panel, Solar Array, Irrigation Main Line, Irrigation Lateral, Drip Line, Fence Perimeter, Fence Interior, Gate, Valve, Well/Pump, Building/Barn, Compost Site, Water Tank/Cistern |
| Tree Health | Excellent, Good, Fair, Poor, Dead, Removed |

---

### `mcp-server/` — farmOS MCP server

A [FastMCP](https://github.com/jlowin/fastmcp) server that wraps the farmOS JSON:API and exposes five read-only tools to Claude.

**Tools:**

| Tool | Description |
|---|---|
| `list_asset_types` | List all registered asset bundle types in this farmOS instance |
| `count_trees` | Count Tree assets matching optional filters (species, stratum, planting year) |
| `query_trees` | Return a list of Tree assets with optional filters and configurable sparse fieldset |
| `get_tree` | Fetch a single Tree asset by UUID |
| `list_infrastructure` | List Infrastructure assets filtered by condition or type |

See [`mcp-server/README.md`](mcp-server/README.md) for full tool reference, auth setup, and example sessions.

Write tools (`create_tree`, `update_tree`, `archive_tree`) are planned for v1.1.

---

### QGIS Integration

Claude controls QGIS directly via the [jjsantos01/qgis_mcp](https://github.com/jjsantos01/qgis_mcp) plugin. This enables conversational map generation, layer management, and spatial analysis without leaving a Claude session.

**What this unlocks:**
- Load any vector or raster layer into QGIS from a Claude prompt
- Apply categorized/graduated symbology programmatically
- Render map images and export print layouts
- Execute arbitrary PyQGIS code for complex spatial operations
- Connect QGIS to PostGIS for live data layers (Sprint 5)

**Available MCP tools (once plugin is running):**

| Tool | Description |
|---|---|
| `ping` | Check QGIS MCP server connectivity |
| `get_qgis_info` | QGIS version and plugin state |
| `get_project_info` | Current project CRS, extent, layer count |
| `get_layers` | List all layers in the current project |
| `add_vector_layer` | Load a vector layer (shapefile, GeoJSON, KML, PostGIS) |
| `add_raster_layer` | Load a raster layer (GeoTIFF, etc.) |
| `execute_code` | Execute PyQGIS code — symbology, analysis, layout creation |
| `render_map` | Render the current map view to PNG at specified dimensions |
| `zoom_to_layer` | Zoom canvas to a layer's extent |
| `save_project` | Save the current project to `.qgz` |

#### Installing the QGIS MCP plugin

```bash
# Clone the plugin
git clone https://github.com/jjsantos01/qgis_mcp.git

# Copy the plugin folder into your QGIS plugins directory
# macOS
cp -r qgis_mcp/qgis_mcp_plugin ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/

# Linux
cp -r qgis_mcp/qgis_mcp_plugin ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```

Then in QGIS: **Plugins → Manage and Install Plugins → Installed → QGIS MCP → Enable**.
Start the server: **Plugins → QGIS MCP → Start Server** (default port 9876).

#### Configuring Claude Code

Add to your `~/.claude/settings.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": ["mcp-proxy", "http://localhost:9876/sse"]
    }
  }
}
```

Or using the Claude Code CLI:

```bash
claude mcp add qgis -- uvx mcp-proxy http://localhost:9876/sse
```

#### The Goldberry Grove base plan

`GoldberryGrove_BasePlan.qgz` (saved in `Permaculture Plans/Layouts/`) is the working QGIS project for Goldberry Grove. It contains:

| Layer group | Layers |
|---|---|
| Terrain | ClippedDEM.tif (NAD83 UTM Zone 17N), Contours 10ft |
| Property | ParcelLines (property boundary), Land Use (Forest / Field / WhiteSpace) |
| Water | Ponds, Pond Border, Pond Inflow North, Pond Inflow East |
| Structures | Buildings (categorized: Building / Greenhouse / Deck), Fence |
| Utilities | Utility Lines (overhead), Utility Points (power poles) |
| Access | Access Routes (categorized: Paved / Gravel / Unpaved / Walking) |
| Planning | Keyline (2 valid segments), Windbreaks (North / South / Riparian) |
| Planting grids | Front Fields, Back East Field, Back West Field, South Front Field, Garden, Garden Points |
| Trees | Existing Trees (canopy polygons), East Property Line |
| Soils | Soil Boundaries |

**Known data issues (documented):**
- Soil type attribute names are blank in the DBF — attribute join from the 2024 soil survey PDF is pending
- Keyline Feature 3 had a corrupt vertex (UTM coordinates stored in WGS84 layer) — filtered out via `setSubsetString('"fid" != 3')`
- DunbarRidges.shp and DunbarValleys.shp are valid WGS84 data but show `W=0 H=0` in `.extent()` queries due to small degree values — they render correctly with OTF reprojection enabled

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [QGIS 3.x](https://qgis.org/download/) (for geospatial work)
- [uv](https://docs.astral.sh/uv/) (for the MCP server)
- [Claude Code](https://claude.ai/code) with MCP support

### 1. Deploy the farmOS Docker stack

```bash
git clone https://github.com/Goldberry-Playground/AgriforestryOS.git
cd AgriforestryOS

cp .env.example .env
# Edit .env: set FARMOS_DB_PASSWORD and any other required values

docker compose up -d
```

farmOS will be available at `http://localhost`. Complete the farmOS installation wizard on first run.

### 2. Install the farm_syntropic module

Once farmOS is running:

```bash
# Via Drush inside the farmOS container
docker compose exec www drush en farm_syntropic -y
docker compose exec www drush cr
```

This installs the Tree, Infrastructure, and Tree Planting asset types plus all four syntropic taxonomy vocabularies.

### 3. Connect the farmOS MCP server to Claude

```bash
# Register with Claude Code
claude mcp add agriforestryos-mcp -- uv run --project /path/to/AgriforestryOS/mcp-server agriforestryos-mcp
```

Add credentials under `mcpServers` in `~/.claude/settings.json`:

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

### 4. Connect QGIS to Claude

See [QGIS Integration → Installing the QGIS MCP plugin](#installing-the-qgis-mcp-plugin) above.

---

## Documentation

| Document | Location |
|---|---|
| Tree inventory data entry (field guide for Wes) | [`docs/workflows/tree-inventory-data-entry.md`](docs/workflows/tree-inventory-data-entry.md) |
| farmOS MCP server tool reference | [`mcp-server/README.md`](mcp-server/README.md) |

---

## Roadmap

### Phase 1 — Foundation ✅ (Sprints 3.5–4)
- [x] Deploy farmOS 4.x Docker stack
- [x] `farm_syntropic` module: Tree, Infrastructure, Tree Planting asset types + taxonomies
- [x] farmOS MCP server v1: 5 read-only tools
- [x] QGIS MCP plugin installed and connected to Claude
- [x] Goldberry Grove base plan loaded in QGIS (25 layers + DEM)
- [ ] GeoJSON export: farmOS → QGIS layer loading script
- [ ] QGIS project template with farmOS-sourced layers + print layout
- [ ] Odoo → farmOS sync service (nursery transfers → Tree assets)

### Phase 2 — Succession + Yield (Sprints 5–6)
- [ ] PostGIS container + farmOS → PostGIS ETL
- [ ] QGIS → PostGIS live layers
- [ ] `spatial_query` tool on MCP server (ST_DWithin)
- [ ] Succession stage progression tracking and logging
- [ ] Yield and harvest records per tree/guild
- [ ] Odoo harvest → product receipt sync
- [ ] Odoo purchase orders → pending Tree assets in farmOS
- [ ] Reconciliation report: Odoo stock vs. farmOS tree counts

### Phase 3 — Research Grade
- [ ] Carbon sequestration estimation (i-Tree / USFS allometric equations)
- [ ] Canopy cover analysis from drone/satellite imagery
- [ ] Sensor data integration (soil moisture, weather station)

---

## Development

```bash
# Run MCP server tests (no live farmOS required — all mocked)
uv run --project mcp-server pytest mcp-server/tests/ -v

# Import smoke test
FARMOS_BASE_URL=http://localhost FARMOS_USERNAME=test FARMOS_PASSWORD=test \
  uv run --project mcp-server python3 -c "import server; print('ok')"
```

---

## Fork Policy

This is a private fork of farmOS. **Do not open pull requests against `farmOS/farmOS` or any other upstream project from this repository.** All work lives in `Goldberry-Playground/AgriforestryOS` only.

When using `gh pr create`, always pass `--repo Goldberry-Playground/AgriforestryOS` explicitly. Two cross-repo PRs (#1078, #1080) leaked to `farmOS/farmOS` when this flag was omitted — the GitHub CLI defaulted to the upstream parent.

```bash
# Always explicit:
gh pr create --repo Goldberry-Playground/AgriforestryOS --title "..." --body "..."
```

---

## Licence

GPL 2.0 — see [LICENSE.txt](LICENSE.txt). farmOS is developed by a community of volunteers; this fork builds on their work without intending to compete with or fragment the upstream project.
