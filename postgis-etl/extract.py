"""
Pure transforms: farmOS JSON:API asset records → PostGIS table rows.

No I/O — these functions are unit-tested in isolation. PostGIS ingests WKT
natively (ST_GeomFromText), so unlike the GeoJSON export this layer does no
geometry conversion: it carries the asset's `intrinsic_geometry` WKT straight
through, plus the flattened scalar/relationship attributes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# farmOS exposes the asset's own geometry as `intrinsic_geometry`; the
# computed `geometry` field is the fallback.
_GEOM_FIELDS = ("intrinsic_geometry", "geometry")


@dataclass
class AssetSpec:
    """Drives the mirror of one farmOS asset type into one PostGIS table."""
    asset_type: str
    endpoint: str
    table: str
    include: list[str]
    # mapping: PostGIS column -> farmOS attribute key (scalars)
    attr_columns: dict[str, str]
    # mapping: PostGIS column -> relationship name (resolved to its term/name)
    rel_columns: dict[str, str] = field(default_factory=dict)


ASSET_SPECS: list[AssetSpec] = [
    AssetSpec(
        asset_type="tree",
        endpoint="/jsonapi/asset/tree",
        table="trees",
        include=["species", "stratum", "succession_stage", "health_status"],
        attr_columns={
            "name": "name", "variety": "variety", "dbh_cm": "dbh_cm",
            "height_m": "height_m", "canopy_radius_m": "canopy_radius_m",
            "planting_date": "planting_date", "tenure": "tenure",
            "odoo_lot": "odoo_lot",
        },
        rel_columns={
            "species": "species", "stratum": "stratum",
            "succession_stage": "succession_stage", "health_status": "health_status",
        },
    ),
    AssetSpec(
        asset_type="infrastructure",
        endpoint="/jsonapi/asset/infrastructure",
        table="infrastructure",
        include=["infrastructure_type"],
        attr_columns={
            "name": "name", "condition": "condition",
            "material": "material", "capacity": "capacity",
        },
        rel_columns={"infrastructure_type": "infrastructure_type"},
    ),
    AssetSpec(
        asset_type="tree_planting",
        endpoint="/jsonapi/asset/tree_planting",
        table="plantings",
        include=["planting_type", "succession_stage"],
        attr_columns={"name": "name", "planting_type": "planting_type"},
        rel_columns={"succession_stage": "succession_stage"},
    ),
    AssetSpec(
        asset_type="land",
        endpoint="/jsonapi/asset/land",
        table="land_areas",
        include=["land_type"],
        attr_columns={"name": "name"},
        rel_columns={"land_type": "land_type"},
    ),
]


def build_name_lookup(included: list) -> dict[str, str]:
    """Map included-resource UUID → its display name (taxonomy term / asset)."""
    out: dict[str, str] = {}
    for inc in included:
        rid = inc.get("id", "")
        name = inc.get("attributes", {}).get("name", "")
        if rid and name:
            out[rid] = name
    return out


def extract_wkt(attributes: dict) -> str | None:
    """Return the asset's geometry as a WKT string, or None if absent/empty."""
    for fld in _GEOM_FIELDS:
        geo = attributes.get(fld)
        if isinstance(geo, dict) and geo.get("value"):
            return geo["value"]
    return None


def asset_to_row(record: dict, name_lookup: dict, spec: AssetSpec) -> dict | None:
    """Flatten one JSON:API asset record into a PostGIS row dict.

    Returns None if the asset has no usable geometry (skipped & counted by the
    caller). The row always includes `asset_uuid` and `wkt`; remaining keys are
    the spec's columns. `wkt` is the WGS84 WKT the DB layer reprojects on write.
    """
    attrs = record.get("attributes", {})
    wkt = extract_wkt(attrs)
    if wkt is None:
        return None

    row: dict = {"asset_uuid": record.get("id"), "wkt": wkt}
    for col, key in spec.attr_columns.items():
        row[col] = attrs.get(key)

    rels = record.get("relationships", {})
    for col, rel_name in spec.rel_columns.items():
        data = rels.get(rel_name, {}).get("data")
        row[col] = name_lookup.get(data["id"]) if isinstance(data, dict) and data else None

    return row
