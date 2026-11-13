"""
AgriforestryOS MCP server — read-only farmOS + PostGIS tools.

Eight tools expose tree inventory, infrastructure, asset-type data, spatial
queries, and harvest/yield data to Claude. Most wrap the farmOS JSON:API;
`spatial_query` runs against the PostGIS spatial mirror (Sprint 5) for
proximity questions; `list_harvests` / `harvest_summary` (Sprint 6) read
the harvest log for yield tracking.

Probe results (documented here for reference):
  - page[limit]=0 WITH meta.count: farmOS Drupal JSON:API returns meta.count
    when page[limit]=0. Primary code path uses this. Fallback counts len(data).
  - Range filter syntax: two-condition >=/<= is standard Drupal JSON:API.
    e.g. filter[dbh-min][path]=dbh_cm&filter[dbh-min][value]=5&filter[dbh-min][operator]=%3E%3D
"""
import os
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError  # noqa: F401 — imported for re-export to tests
from client import FarmOSClient

_REQUIRED_VARS = ["FARMOS_BASE_URL", "FARMOS_USERNAME", "FARMOS_PASSWORD"]
_missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
if _missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(_missing)}. "
        "Set them in mcp-server/.env and run with: "
        "uv run --env-file mcp-server/.env agriforestryos-mcp"
    )

_client = FarmOSClient(
    base_url=os.environ["FARMOS_BASE_URL"],
    username=os.environ["FARMOS_USERNAME"],
    password=os.environ["FARMOS_PASSWORD"],
)

mcp = FastMCP("agriforestryos")


def main() -> None:
    """Entry point for `agriforestryos-mcp` console script."""
    mcp.run()


# ---------------------------------------------------------------------------
# Tool: list_asset_types
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_asset_types() -> list[dict]:
    """List all registered asset bundle types in this farmOS instance.

    Returns a list of {id, label} dicts. Use this to discover what asset
    types are available before querying specific bundles.
    """
    data = await _client.get("/jsonapi/asset_type/asset_type")
    return [
        {
            "id": item["id"],
            "label": item["attributes"].get("label")
            or item["attributes"].get("drupal_internal__id")
            or item["id"],
        }
        for item in data.get("data", [])
    ]


# ---------------------------------------------------------------------------
# Tool: count_trees
# ---------------------------------------------------------------------------

@mcp.tool()
async def count_trees(
    species: str | None = None,
    stratum: str | None = None,
    planting_year: int | None = None,
) -> dict:
    """Count Tree assets matching optional filters.

    Args:
        species: Filter by species name (e.g. "American Chestnut").
        stratum: Filter by syntropic stratum name (e.g. "High Canopy").
        planting_year: Filter to trees planted in this calendar year.

    Returns:
        {"count": int, "filters_applied": dict}
    """
    params: dict = {"page[limit]": "0"}
    filters_applied: dict = {}

    if species:
        params["filter[species.name]"] = species
        filters_applied["species"] = species
    if stratum:
        params["filter[stratum.name]"] = stratum
        filters_applied["stratum"] = stratum
    if planting_year:
        params["filter[planting_date][value]"] = str(planting_year)
        params["filter[planting_date][operator]"] = "STARTS_WITH"
        filters_applied["planting_year"] = planting_year

    response = await _client.get("/jsonapi/asset/tree", params=params)

    # Primary path: farmOS returns meta.count with page[limit]=0
    if "count" in response.get("meta", {}):
        count = response["meta"]["count"]
    else:
        # Fallback: count the returned data array
        count = len(response.get("data", []))

    return {"count": count, "filters_applied": filters_applied}


# ---------------------------------------------------------------------------
# Tool: query_trees
# ---------------------------------------------------------------------------

_DEFAULT_TREE_FIELDS = [
    "id", "name", "species", "dbh_cm", "height_m",
    "stratum", "health_status", "planting_date",
]


@mcp.tool()
async def query_trees(
    species: str | None = None,
    min_dbh_cm: float | None = None,
    max_dbh_cm: float | None = None,
    stratum: str | None = None,
    limit: int = 50,
    fields: list[str] | None = None,
) -> list[dict]:
    """Query Tree assets with optional filters, returning a flat list.

    Args:
        species: Filter by species name.
        min_dbh_cm: Minimum DBH in centimeters (inclusive).
        max_dbh_cm: Maximum DBH in centimeters (inclusive).
        stratum: Filter by syntropic stratum name.
        limit: Max records to return (clamped to 500).
        fields: Override default sparse fieldset. Defaults to
                [id, name, species, dbh_cm, height_m, stratum, health_status, planting_date].

    Returns:
        List of flat attribute dicts (included relationships resolved to names).

    Range filter syntax (Drupal JSON:API two-condition form):
        filter[dbh-min][path]=dbh_cm&filter[dbh-min][value]=N&filter[dbh-min][operator]=%3E%3D
    """
    effective_limit = min(limit, 500)
    effective_fields = fields or _DEFAULT_TREE_FIELDS

    params: dict = {
        "fields[asset--tree]": ",".join(effective_fields),
        "page[limit]": str(effective_limit),
        "include": "species,stratum,succession_stage,health_status",
    }

    if species:
        params["filter[species.name]"] = species
    if stratum:
        params["filter[stratum.name]"] = stratum
    if min_dbh_cm is not None:
        params["filter[dbh-min][path]"] = "dbh_cm"
        params["filter[dbh-min][value]"] = str(min_dbh_cm)
        params["filter[dbh-min][operator]"] = ">="
    if max_dbh_cm is not None:
        params["filter[dbh-max][path]"] = "dbh_cm"
        params["filter[dbh-max][value]"] = str(max_dbh_cm)
        params["filter[dbh-max][operator]"] = "<="

    response = await _client.get("/jsonapi/asset/tree", params=params)

    # Build lookup table for included relationship names
    included_names: dict[str, str] = {}
    for inc in response.get("included", []):
        inc_id = inc.get("id", "")
        inc_name = inc.get("attributes", {}).get("name", "")
        if inc_id and inc_name:
            included_names[inc_id] = inc_name

    results = []
    for item in response.get("data", []):
        flat: dict = {"id": item["id"]}
        flat.update(item.get("attributes", {}))
        # Resolve relationship labels
        for rel_name, rel_data in item.get("relationships", {}).items():
            if isinstance(rel_data.get("data"), dict):
                rel_id = rel_data["data"].get("id", "")
                if rel_id in included_names:
                    flat[f"{rel_name}_name"] = included_names[rel_id]
        results.append(flat)

    return results


# ---------------------------------------------------------------------------
# Tool: get_tree
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_tree(id: str) -> dict:
    """Get a single Tree asset by its UUID.

    Args:
        id: The UUID of the Tree asset.

    Returns:
        Flat dict of all attributes with resolved relationship names.
        Raises ToolError if not found (404).
    """
    path = f"/jsonapi/asset/tree/{id}"
    params = {"include": "species,stratum,succession_stage,health_status"}
    data = await _client.get_single(path, params=params)

    flat: dict = {"id": data["id"]}
    flat.update(data.get("attributes", {}))
    return flat


# ---------------------------------------------------------------------------
# Tool: list_infrastructure
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_infrastructure(
    condition: str | None = None,
    infrastructure_type: str | None = None,
) -> list[dict]:
    """List Infrastructure assets with optional filters.

    Args:
        condition: Filter by condition ('new', 'good', 'fair', 'needs_repair',
                   'decommissioned').
        infrastructure_type: Filter by infrastructure type name.

    Returns:
        List of flat attribute dicts.
    """
    params: dict = {"include": "infrastructure_type"}

    if condition:
        params["filter[condition]"] = condition
    if infrastructure_type:
        params["filter[infrastructure_type.name]"] = infrastructure_type

    response = await _client.get("/jsonapi/asset/infrastructure", params=params)

    included_names: dict[str, str] = {}
    for inc in response.get("included", []):
        inc_id = inc.get("id", "")
        inc_name = inc.get("attributes", {}).get("name", "")
        if inc_id and inc_name:
            included_names[inc_id] = inc_name

    results = []
    for item in response.get("data", []):
        flat: dict = {"id": item["id"]}
        flat.update(item.get("attributes", {}))
        infra_rel = item.get("relationships", {}).get("infrastructure_type", {})
        if isinstance(infra_rel.get("data"), dict):
            rel_id = infra_rel["data"].get("id", "")
            if rel_id in included_names:
                flat["infrastructure_type_name"] = included_names[rel_id]
        results.append(flat)

    return results


# ---------------------------------------------------------------------------
# Tool: spatial_query  (PostGIS mirror — Sprint 5)
# ---------------------------------------------------------------------------

@mcp.tool()
def spatial_query(
    asset_type: str,
    lat: float,
    lon: float,
    within_m: float | None = None,
    limit: int = 20,
) -> list[dict]:
    """Find assets near a point using the PostGIS spatial mirror.

    Answers questions like "what trees are within 30m of the well?" or
    "the 5 nearest infrastructure items to this spot". Results are ordered
    nearest-first and include `distance_m` (metres).

    Args:
        asset_type: One of 'trees', 'infrastructure', 'plantings', 'land_areas'.
        lat: Latitude of the query point (WGS84).
        lon: Longitude of the query point (WGS84).
        within_m: Optional radius in metres (ST_DWithin). Omit for nearest-N.
        limit: Max results (default 20, ordered by distance).

    Returns:
        List of asset dicts with a `distance_m` field, nearest first.

    Requires POSTGIS_DSN to be set (the farmOS→PostGIS ETL must have run).
    """
    import spatial

    dsn = os.environ.get("POSTGIS_DSN")
    if not dsn:
        raise ToolError(
            "Spatial queries need the PostGIS mirror. Set POSTGIS_DSN (and run "
            "the farmOS→PostGIS ETL) to enable spatial_query."
        )
    if asset_type not in spatial.ASSET_TYPES:
        raise ToolError(
            f"unknown asset_type {asset_type!r}; expected one of "
            f"{', '.join(spatial.ASSET_TYPES)}"
        )
    try:
        return spatial.run_spatial_query(dsn, asset_type, lat, lon, within_m, limit)
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface DB/connection errors plainly
        raise ToolError(f"spatial query failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Tools: list_harvests / harvest_summary  (Sprint 6 — yield tracking)
# ---------------------------------------------------------------------------

_HARVEST_INCLUDE = "asset,quantity,quantity.units"


@mcp.tool()
async def list_harvests(
    asset_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List harvest logs with their harvested assets and quantities.

    Args:
        asset_id: Filter to harvests referencing this asset UUID.
        since: ISO date/datetime — only harvests at or after this timestamp.
        until: ISO date/datetime — only harvests at or before this timestamp.
        limit: Max records (clamped to 500).

    Returns:
        List of harvest dicts: {id, name, timestamp, status, notes,
        assets: [names], quantities: [{value, units, measure, label}]}.

    Use for "what did we harvest from the Apple tree?" or "harvests since June".
    """
    import harvest

    params: dict = {
        "include": _HARVEST_INCLUDE,
        "page[limit]": str(min(limit, 500)),
        "sort": "-timestamp",
    }
    if asset_id:
        params["filter[asset.id]"] = asset_id
    if since:
        params["filter[ts-since][path]"] = "timestamp"
        params["filter[ts-since][value]"] = since
        params["filter[ts-since][operator]"] = ">="
    if until:
        params["filter[ts-until][path]"] = "timestamp"
        params["filter[ts-until][value]"] = until
        params["filter[ts-until][operator]"] = "<="

    response = await _client.get("/jsonapi/log/harvest", params=params)
    return harvest.flatten_harvests(response)


@mcp.tool()
async def harvest_summary(group_by: str = "asset") -> list[dict]:
    """Aggregate harvest quantities by a dimension.

    Args:
        group_by: 'asset' (per harvested asset), 'month' (per YYYY-MM), or
                  'measure' (per quantity measure: count, weight, …).

    Returns:
        List of {group, total_value, harvest_count}, sorted by group.

    Use for "how much have we harvested per species/month this season?".
    """
    import harvest

    if group_by not in ("asset", "month", "measure"):
        raise ToolError("group_by must be one of: asset, month, measure")

    response = await _client.get(
        "/jsonapi/log/harvest",
        params={"include": _HARVEST_INCLUDE, "page[limit]": "500"},
    )
    harvests = harvest.flatten_harvests(response)
    return harvest.summarize(harvests, group_by)
