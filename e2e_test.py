#!/usr/bin/env python3
"""
End-to-end pipeline test: Odoo transfer → farmOS Tree → GeoJSON → QGIS layer.

This is the Sprint 4 E2E acceptance check. It drives the *real* pipeline code
from both packages across all four stages and asserts the data contract holds
at every seam:

    1. Odoo stock move        (mapping.Transfer)
    2. → farmOS Tree asset     (mapping.build_tree_attributes / determine_tenure)
    3. → JSON:API asset record (the shape the sync writes + a placed geometry)
    4. → GeoJSON feature        (export_geojson.to_features)
    5. → QGIS load script       (load_qgis_layers.build_load_script)

Two modes:

  • default (simulated): no live services needed — proves the data flows
    coherently through the actual transform functions of both packages.
    This is what CI runs.

  • --live: runs the genuine integration against a running Odoo + farmOS +
    sync service. See the runbook in the docstring of run_live().

Run:
    python e2e_test.py            # simulated, exits non-zero on any failed seam
    python e2e_test.py --live     # against the live stack (see run_live docstring)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Both packages live as flat modules in their own dirs; put them on the path.
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "sync-service"))
sys.path.insert(0, str(_ROOT / "mcp-server"))

import mapping            # noqa: E402  (sync-service)
import export_geojson     # noqa: E402  (mcp-server)
import load_qgis_layers   # noqa: E402  (mcp-server)


class SeamError(AssertionError):
    """Raised when a pipeline seam fails its contract."""


def _check(label: str, condition: bool, detail: str = "") -> None:
    mark = "✓" if condition else "✗"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SeamError(f"{label}: {detail or 'assertion failed'}")


def run_simulated() -> None:
    """Drive the real transform code through all four stages with sample data."""
    print("E2E (simulated) — Odoo transfer → farmOS Tree → GeoJSON → QGIS\n")

    # ---- Stage 1: an Odoo move INTO the Orchard ---------------------------
    print("Stage 1: Odoo stock move (nursery → Orchard)")
    transfer = mapping.Transfer(
        lot="SW-2026-A1",
        direction="in",
        product_name="Eastern Redbud",
        category_name="Plants / Nursery Stock",
        species="Eastern Redbud",
        variety="Eastern Redbud",
        source="At the Grove Nursery",
        move_line_id=42,
        date="2026-06-08 09:00:00",
    )
    _check("transfer parsed", transfer.lot == "SW-2026-A1", f"lot={transfer.lot}")

    # ---- Stage 2: map to farmOS Tree attributes ---------------------------
    print("Stage 2: map → farmOS Tree attributes")
    tenure = mapping.determine_tenure(transfer.category_name, {"Plants / Nursery Stock"})
    attrs = mapping.build_tree_attributes(transfer, tenure)
    _check("tenure classified nursery_stock", tenure == "nursery_stock", tenure)
    _check("odoo_lot carried", attrs["odoo_lot"] == "SW-2026-A1")
    _check("geometry omitted at creation", "intrinsic_geometry" not in attrs)
    _check("status active", attrs["status"] == "active")

    # ---- Stage 3: the JSON:API asset record (sync writes this; later a GPS
    #              point is recorded when the tree is physically placed) -----
    print("Stage 3: farmOS JSON:API asset record (after placement)")
    asset_record = {
        "id": "tree-uuid-001",
        "attributes": {
            **attrs,
            # Wes records the trunk GPS once the tree is in the ground:
            "intrinsic_geometry": {"value": "POINT (-80.795540 38.301230)"},
        },
        "relationships": {
            "species": {"data": {"id": "term-redbud"}},
        },
    }
    name_lookup = {"term-redbud": "Eastern Redbud"}
    _check("asset has geometry post-placement",
           asset_record["attributes"]["intrinsic_geometry"]["value"].startswith("POINT"))

    # ---- Stage 4: export to GeoJSON via the real exporter -----------------
    print("Stage 4: export → GeoJSON feature")
    spec = export_geojson.EXPORT_SPECS["tree"]
    features, skipped = export_geojson.to_features([asset_record], name_lookup, spec)
    _check("one feature exported, none skipped", len(features) == 1 and skipped == 0)
    feat = features[0]
    _check("GeoJSON geometry is a Point", feat["geometry"]["type"] == "Point",
           str(feat["geometry"]["coordinates"]))
    _check("tenure survives to map property", feat["properties"].get("tenure") == "nursery_stock")
    _check("species resolved to name", feat["properties"].get("species_name") == "Eastern Redbud")
    _check("odoo_lot traceable on feature", feat["properties"].get("odoo_lot") == "SW-2026-A1")

    # Coordinates round-trip WKT(lon lat) → GeoJSON [lon, lat]
    lon, lat = feat["geometry"]["coordinates"]
    _check("coords are lon/lat WGS84", -81 < lon < -80 and 38 < lat < 39, f"[{lon}, {lat}]")

    # ---- Stage 5: QGIS load script ---------------------------------------
    print("Stage 5: QGIS load script generation")
    script = load_qgis_layers.build_load_script(str(_ROOT / "mcp-server" / "qgis_layers"))
    _check("load script references trees layer", "trees.geojson" in script and "[farmOS] Trees" in script)
    _check("load script is valid Python", _is_valid_python(script))

    print("\n✅ E2E simulated pipeline PASSED — all 5 stages, data contract intact.")


def _is_valid_python(src: str) -> bool:
    import ast
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def run_live() -> None:
    """Run the genuine integration against a live stack.

    Runbook (all services must be up):
      1. Odoo running with the WH/Orchard location + lot-tracked tree products.
      2. farmOS running with farm_syntropic enabled (incl. the `tenure` field):
           cd docker && docker compose -f docker-compose.development.yml \\
             -f docker-compose.farm-syntropic.yml up -d
           drush en farm_syntropic -y && drush cr
      3. sync-service configured (.env) and reachable to both.

    Steps:
      a. Create an internal transfer in Odoo (Nursery → Orchard) for a
         lot-tracked tree product.
      b. Run one sync pass:  python sync-service/sync.py --once
      c. Assert a Tree asset now exists in farmOS with the matching odoo_lot,
         species, variety, and tenure.
      d. Record a GPS point on the new tree (or via Wes's workflow).
      e. Export:  python mcp-server/export_geojson.py
      f. Assert trees.geojson contains a feature with that odoo_lot + geometry.
      g. Load into QGIS via load_qgis_layers and confirm it renders.
    """
    print("Live E2E requires running Odoo + farmOS + sync-service.")
    print("farmOS is not currently up (its base compose file was removed in PR #11).")
    print("See run_live.__doc__ for the full runbook once the stack is restored.")
    raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sprint 4 E2E pipeline test.")
    parser.add_argument("--live", action="store_true",
                        help="Run against the live Odoo+farmOS+sync stack (see run_live docstring).")
    args = parser.parse_args()
    if args.live:
        run_live()
    else:
        try:
            run_simulated()
        except SeamError as exc:
            print(f"\n❌ E2E FAILED at a seam: {exc}")
            raise SystemExit(1)


if __name__ == "__main__":
    main()
