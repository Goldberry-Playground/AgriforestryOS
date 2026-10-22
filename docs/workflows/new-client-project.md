# New client QGIS project (`scripts/new_client_project.py`)

Consult phase 2 E (GOL-3577). One AgriforestryOS instance serves every consult
client (spec ruling: no per-client instances); each client gets a QGIS project
of their own, cloned from the home-farm base plan. The clone keeps the layer
**groups**, the CRS, the print layouts and the styling conventions, and drops
the home-farm **layers** — our parcel, ponds, trees, grids — so a client plan
never starts with Goldberry Grove's data in it. Phase 3 fills the empty groups
from the client's PostGIS schema, DEM, soils and rows.

## Usage

```bash
# see what the base plan contains
python3 scripts/new_client_project.py --base "Permaculture Plans/Layouts/GoldberryGrove_BasePlan.qgz" --list

# make the client project (dry run first)
python3 scripts/new_client_project.py \
  --base "Permaculture Plans/Layouts/GoldberryGrove_BasePlan.qgz" \
  --opportunity "142 Smith Hollow" \
  --out-dir "Permaculture Plans/Clients" --dry-run
# then for real
python3 scripts/new_client_project.py --base ... --opportunity "142 Smith Hollow" --out-dir "Permaculture Plans/Clients"
# -> Permaculture Plans/Clients/142-smith-hollow.qgz
```

Stdlib only — runs anywhere Python 3.11+ is, no QGIS install needed.

| Flag | Meaning |
|---|---|
| `--opportunity "<crm.lead id> <lead name>"` | Becomes the project title; slugified (`142-smith-hollow`) it is the file name. **Use the same string as the Spaces export prefix `consult/<opportunity>/`** so one key finds the client in Odoo, on Spaces and in QGIS. |
| `--keep GLOB` (repeatable) | Keep a home-farm layer by name or id glob, e.g. `--keep 'Contours*'` for a regional contour set that applies to the client too. |
| `--no-basemaps` | Also drop the XYZ / WMS / vector-tile basemaps (kept by default — they are not farm data). |
| `--list` | Print groups and layers of the base plan and exit. |
| `--dry-run` | Print the report, write nothing. |
| `--force` | Overwrite an existing `<slug>.qgz`. Refused otherwise. |

## What "removes the home-farm layers" means exactly

Every map layer except basemaps and `--keep` matches is deleted from **all**
the places a QGIS project references a layer: the layer tree, `projectlayers`,
the legacy `<legend>`, `layerorder`, `custom-order`, snapping settings,
visibility presets and print-layout map `LayerSet`s. The result opens with no
"unavailable layer" prompts. Empty groups (and nested groups) stay, in the
base plan's order. The project title is set in all three places QGIS keeps it.

The `.qgd` auxiliary-storage sidecar is not copied: it only holds per-layer
label/diagram overrides for layers that no longer exist, and QGIS recreates it
on first save.

## Where the base plan lives

`GoldberryGrove_BasePlan.qgz` is in `Permaculture Plans/Layouts/` on the
operator machine (see the README's base-plan table for its groups and
layers). It is not in this repo. Client projects go in a sibling
`Permaculture Plans/Clients/` folder; the phase-4 export bundle copies the
`.qgz` to Spaces under `consult/<opportunity>/`.

## Tests

```bash
python3 -m pytest scripts/tests -v
```

The tests build a synthetic `.qgz` with the real QGIS 3.x element shapes and
assert that no removed id survives anywhere, groups and basemaps survive, the
`--keep` glob works, and the CLI names the output and refuses to overwrite.
