"""
farmOS → GeoJSON export for QGIS layer loading (Sprint 4).

Fetches Tree, Infrastructure, and Tree Planting assets from the farmOS
JSON:API, converts each asset's `intrinsic_geometry` (WKT, WGS84) into
GeoJSON, flattens JSON:API relationship indirection (species / stratum /
health / infrastructure_type) into flat feature properties, and writes one
GeoJSON FeatureCollection per asset type.

The output files are EPSG:4326 (the CRS farmOS geofields store) and are
designed to drop straight into the QGIS project template via the QGIS MCP
`add_vector_layer` tool. QGIS reprojects to the project CRS (EPSG:26917) on
the fly.

Run:
    uv run --env-file .env python export_geojson.py
    uv run --env-file .env python export_geojson.py --out /path/to/dir

Reuses FARMOS_BASE_URL / FARMOS_USERNAME / FARMOS_PASSWORD (same basic-auth
env vars as the MCP server).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from client import FarmOSClient

# ---------------------------------------------------------------------------
# Asset-type export specs
# ---------------------------------------------------------------------------
# Each spec drives one FeatureCollection. `include` resolves taxonomy/asset
# relationships to names; `properties` is the flat attribute set carried into
# each GeoJSON feature (id + name are always included).

EXPORT_SPECS = {
    "tree": {
        "endpoint": "/jsonapi/asset/tree",
        "include": ["species", "stratum", "succession_stage", "health_status", "parent_planting"],
        "properties": [
            "variety", "dbh_cm", "height_m", "canopy_radius_m",
            "rootstock", "graft_variety", "planting_date", "source", "odoo_lot",
        ],
        "out_file": "trees.geojson",
    },
    "infrastructure": {
        "endpoint": "/jsonapi/asset/infrastructure",
        "include": ["infrastructure_type"],
        "properties": [
            "material", "capacity", "installation_date",
            "condition", "specifications",
        ],
        "out_file": "infrastructure.geojson",
    },
    "tree_planting": {
        "endpoint": "/jsonapi/asset/tree_planting",
        "include": ["planting_type", "succession_stage"],
        "properties": ["planting_type", "succession_stage", "design_notes"],
        "out_file": "plantings.geojson",
    },
}

# farmOS exposes the asset's own geometry as `intrinsic_geometry`; the
# computed `geometry` field is a fallback (includes location-log geometry).
_GEOM_FIELDS = ("intrinsic_geometry", "geometry")


# ---------------------------------------------------------------------------
# WKT → GeoJSON geometry
# ---------------------------------------------------------------------------

def wkt_to_geojson(wkt: str) -> dict | None:
    """Convert a WKT string to a GeoJSON geometry dict.

    Supports POINT, LINESTRING, POLYGON and their MULTI* variants —
    the geometry types farmOS geofields produce. Returns None for empty
    or unparseable input rather than raising, so one bad asset can't abort
    a whole export.
    """
    if not wkt or not isinstance(wkt, str):
        return None
    wkt = wkt.strip()
    m = re.match(r"^\s*([A-Za-z]+)\s*(Z|M|ZM)?\s*\((.*)\)\s*$", wkt, re.DOTALL)
    if not m:
        return None
    gtype = m.group(1).upper()
    body = m.group(3).strip()

    def parse_pt(s: str) -> list[float]:
        # Keep only X Y (drop Z/M); WKT is "lon lat [z [m]]"
        nums = s.split()
        return [float(nums[0]), float(nums[1])]

    def parse_ring(s: str) -> list[list[float]]:
        return [parse_pt(p.strip()) for p in s.split(",") if p.strip()]

    def parse_polys(s: str) -> list:
        # s = "(ring),(ring)" -> list of rings
        rings = re.findall(r"\(([^()]*)\)", s)
        return [parse_ring(r) for r in rings]

    try:
        if gtype == "POINT":
            return {"type": "Point", "coordinates": parse_pt(body)}
        if gtype == "LINESTRING":
            return {"type": "LineString", "coordinates": parse_ring(body)}
        if gtype == "POLYGON":
            return {"type": "Polygon", "coordinates": parse_polys(body)}
        if gtype == "MULTIPOINT":
            # MULTIPOINT can be "(x y),(x y)" or "x y, x y"
            pts = re.findall(r"\(([^()]*)\)", body)
            if pts:
                coords = [parse_pt(p) for p in pts]
            else:
                coords = parse_ring(body)
            return {"type": "MultiPoint", "coordinates": coords}
        if gtype == "MULTILINESTRING":
            lines = re.findall(r"\(([^()]*)\)", body)
            return {"type": "MultiLineString",
                    "coordinates": [parse_ring(l) for l in lines]}
        if gtype == "MULTIPOLYGON":
            # body = "((ring),(ring)),((ring))" — split on top-level ")),"
            polys = re.findall(r"\(\((.*?)\)\)", body)
            return {"type": "MultiPolygon",
                    "coordinates": [parse_polys("(" + p + ")") for p in polys]}
    except (ValueError, IndexError):
        return None
    return None


def extract_geometry(attributes: dict) -> dict | None:
    """Pull a GeoJSON geometry from an asset's attributes.

    Tries `intrinsic_geometry` then `geometry`; each is a geofield dict with
    a `.value` WKT member.
    """
    for field in _GEOM_FIELDS:
        geo = attributes.get(field)
        if isinstance(geo, dict) and geo.get("value"):
            g = wkt_to_geojson(geo["value"])
            if g:
                return g
    return None


# ---------------------------------------------------------------------------
# JSON:API fetch + flatten
# ---------------------------------------------------------------------------

async def fetch_all(client: FarmOSClient, endpoint: str, include: list[str]) -> dict:
    """Fetch every page of a JSON:API collection.

    Returns {"data": [...all records...], "included": [...all included...]}.
    Follows links.next until exhausted. Geometry fields are always requested
    by NOT restricting the sparse fieldset (farmOS returns all attributes by
    default, which includes intrinsic_geometry).
    """
    params: dict = {"page[limit]": "50"}
    if include:
        params["include"] = ",".join(include)

    all_data: list = []
    all_included: list = []
    path = endpoint

    while True:
        body = await client.get(path, params=params)
        all_data.extend(body.get("data", []))
        all_included.extend(body.get("included", []))
        next_link = body.get("links", {}).get("next", {})
        next_href = next_link.get("href") if isinstance(next_link, dict) else None
        if not next_href:
            break
        # Subsequent pages: use the absolute next href, drop our params
        path = next_href[len(client._base_url):] if next_href.startswith(client._base_url) else next_href
        params = None

    return {"data": all_data, "included": all_included}


def build_name_lookup(included: list) -> dict[str, str]:
    """Map included-resource UUID → its display name (taxonomy term or asset)."""
    lookup: dict[str, str] = {}
    for inc in included:
        inc_id = inc.get("id", "")
        name = inc.get("attributes", {}).get("name", "")
        if inc_id and name:
            lookup[inc_id] = name
    return lookup


def to_features(records: list, name_lookup: dict, spec: dict) -> tuple[list, int]:
    """Convert JSON:API asset records to GeoJSON features.

    Returns (features, skipped_count). Records with no usable geometry are
    skipped and counted (a planting may have no geometry yet, etc.).
    """
    features = []
    skipped = 0
    for rec in records:
        attrs = rec.get("attributes", {})
        geom = extract_geometry(attrs)
        if geom is None:
            skipped += 1
            continue

        props: dict = {
            "id": rec.get("id"),
            "name": attrs.get("name"),
        }
        for key in spec["properties"]:
            if key in attrs:
                props[key] = attrs[key]

        # Resolve relationship UUIDs → names as flat *_name props
        for rel_name, rel in rec.get("relationships", {}).items():
            data = rel.get("data")
            if isinstance(data, dict) and data.get("id") in name_lookup:
                props[f"{rel_name}_name"] = name_lookup[data["id"]]

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props,
        })
    return features, skipped


def feature_collection(features: list) -> dict:
    """Wrap features in a FeatureCollection with an explicit WGS84 CRS."""
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def export(out_dir: Path) -> dict:
    """Run all exports; return a summary dict {asset_type: {count, skipped, path}}."""
    required = ["FARMOS_BASE_URL", "FARMOS_USERNAME", "FARMOS_PASSWORD"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing env vars: {', '.join(missing)}. "
            "Run: uv run --env-file .env python export_geojson.py"
        )

    client = FarmOSClient(
        base_url=os.environ["FARMOS_BASE_URL"],
        username=os.environ["FARMOS_USERNAME"],
        password=os.environ["FARMOS_PASSWORD"],
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {}

    for asset_type, spec in EXPORT_SPECS.items():
        body = await fetch_all(client, spec["endpoint"], spec["include"])
        name_lookup = build_name_lookup(body["included"])
        features, skipped = to_features(body["data"], name_lookup, spec)

        out_path = out_dir / spec["out_file"]
        out_path.write_text(json.dumps(feature_collection(features), indent=2))
        summary[asset_type] = {
            "count": len(features),
            "skipped_no_geometry": skipped,
            "path": str(out_path),
        }

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export farmOS assets to GeoJSON for QGIS.")
    parser.add_argument(
        "--out", default=None,
        help="Output directory (default: ./qgis_layers next to this script).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else Path(__file__).parent / "qgis_layers"
    summary = asyncio.run(export(out_dir))

    print(f"farmOS → GeoJSON export complete → {out_dir}")
    for asset_type, info in summary.items():
        skip = f" ({info['skipped_no_geometry']} skipped, no geometry)" if info["skipped_no_geometry"] else ""
        print(f"  {asset_type:15} {info['count']:4} features{skip}  → {Path(info['path']).name}")


if __name__ == "__main__":
    sys.exit(main())
