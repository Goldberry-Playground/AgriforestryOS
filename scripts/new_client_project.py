#!/usr/bin/env python3
"""
new_client_project.py — make a per-client QGIS project from the home-farm base plan.

Consult phase 2 E (GOL-3577; spec §E of grove-odoo-modules
docs/superpowers/specs/2026-10-22-consult-dashboard-design.md). One
AgriforestryOS instance serves every consult client; each client gets a QGIS
project of their own, cloned from `GoldberryGrove_BasePlan.qgz` so the layer
GROUPS (Terrain, Property, Water, Structures, Utilities, Access, Planning,
Planting grids, Trees, Soils), the CRS, the print layouts and the styling
conventions carry over, while the home-farm LAYERS (our parcel, our ponds, our
trees) do not. Phase 3 fills the empty groups with the client's PostGIS
schema, DEM, soils and rows.

    python3 scripts/new_client_project.py \
        --base "Permaculture Plans/Layouts/GoldberryGrove_BasePlan.qgz" \
        --opportunity "142 Smith Hollow" \
        --out-dir "Permaculture Plans/Clients"
    # -> Permaculture Plans/Clients/142-smith-hollow.qgz

The output name is the slugified opportunity, `<crm.lead id>-<lead name>`, the
same key the Spaces export prefix `consult/<opportunity>/` uses, so one string
finds a client in Odoo, on Spaces and in QGIS.

What is removed: every map layer in the base plan except basemaps (XYZ / WMS /
vector-tile / ArcGIS map services) and anything matched by --keep. Removal is
thorough — the layer tree, projectlayers, the legacy <legend>, layer order,
custom order, snapping settings, visibility presets and print-layout map
LayerSets all lose their references — so QGIS opens the clone with no
"unavailable layer" prompts. The .qgd auxiliary-storage sidecar is NOT copied
(it only holds per-layer overrides for layers that are gone; QGIS recreates it).

Stdlib only; no QGIS install needed. Pure functions so the tests run on a
synthetic project (scripts/tests/test_new_client_project.py).
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

# Providers whose layers are NOT home-farm data: tile/imagery services that any
# client project wants too. Everything else in the base plan is ours.
BASEMAP_PROVIDERS = frozenset({"wms", "vectortile", "arcgismapserver"})


# ── model ─────────────────────────────────────────────────────────────────────

@dataclass
class LayerInfo:
    id: str
    name: str
    provider: str
    group_path: tuple[str, ...]  # ("Water",) / () for root-level layers

    @property
    def is_basemap(self) -> bool:
        return self.provider in BASEMAP_PROVIDERS


@dataclass
class Report:
    opportunity: str
    slug: str
    groups: list[str] = field(default_factory=list)
    kept: list[LayerInfo] = field(default_factory=list)
    removed: list[LayerInfo] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"client project: {self.slug}  (title: {self.opportunity})"]
        lines.append(f"groups kept ({len(self.groups)}): " + ", ".join(self.groups))
        lines.append(f"layers kept ({len(self.kept)}):")
        for lay in self.kept:
            lines.append(f"  + {'/'.join(lay.group_path) or '<root>'} / {lay.name}  [{lay.provider}]")
        lines.append(f"layers removed ({len(self.removed)}):")
        for lay in self.removed:
            lines.append(f"  - {'/'.join(lay.group_path) or '<root>'} / {lay.name}  [{lay.provider}]")
        return "\n".join(lines)


# ── helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """'142 Smith Hollow' -> '142-smith-hollow'. Keeps digits so the lead id survives."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"opportunity {text!r} has no usable characters for a filename")
    return slug


def read_qgs(qgz_path: Path) -> tuple[str, bytes]:
    """Return (member name, bytes) of the .qgs project XML inside a .qgz archive."""
    with zipfile.ZipFile(qgz_path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".qgs")]
        if not members:
            raise ValueError(f"{qgz_path}: no .qgs project inside the archive")
        return members[0], zf.read(members[0])


def split_prolog(xml_bytes: bytes) -> tuple[str, bytes]:
    """QGIS writes a DOCTYPE line before <qgis>; ElementTree drops it. Keep it."""
    text = xml_bytes.decode("utf-8")
    idx = text.find("<qgis")
    if idx < 0:
        raise ValueError("not a QGIS project: no <qgis> root element")
    return text[:idx], text[idx:].encode("utf-8")


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def inventory(root: ET.Element) -> tuple[list[str], list[LayerInfo]]:
    """Walk the layer tree: (group names in tree order, layers with their group path)."""
    providers: dict[str, str] = {}
    names: dict[str, str] = {}
    for ml in root.iterfind("./projectlayers/maplayer"):
        lid = (ml.findtext("id") or "").strip()
        providers[lid] = (ml.findtext("provider") or "").strip()
        names[lid] = (ml.findtext("layername") or "").strip()

    groups: list[str] = []
    layers: list[LayerInfo] = []

    def walk(node: ET.Element, path: tuple[str, ...]) -> None:
        for child in node:
            if child.tag == "layer-tree-group":
                name = child.get("name", "")
                if name:
                    groups.append(name)
                walk(child, path + ((name,) if name else ()))
            elif child.tag == "layer-tree-layer":
                lid = child.get("id", "")
                layers.append(LayerInfo(
                    id=lid,
                    name=child.get("name") or names.get(lid, lid),
                    provider=child.get("providerKey") or providers.get(lid, ""),
                    group_path=path,
                ))

    tree = root.find("layer-tree-group")
    if tree is not None:
        walk(tree, ())

    # Layers registered in projectlayers but absent from the tree (rare, but a
    # stale reference would still prompt on open). Report them at root.
    seen = {lay.id for lay in layers}
    for lid, prov in providers.items():
        if lid not in seen:
            layers.append(LayerInfo(id=lid, name=names.get(lid, lid), provider=prov, group_path=()))
    return groups, layers


def select_removals(layers: Iterable[LayerInfo], keep: Iterable[str] = (), keep_basemaps: bool = True) -> set[str]:
    """Ids to remove: everything that is neither a basemap nor matched by a --keep glob."""
    patterns = list(keep)
    out: set[str] = set()
    for lay in layers:
        if keep_basemaps and lay.is_basemap:
            continue
        if any(fnmatch.fnmatchcase(lay.name, p) or fnmatch.fnmatchcase(lay.id, p) for p in patterns):
            continue
        out.add(lay.id)
    return out


def strip_layers(root: ET.Element, remove_ids: set[str]) -> int:
    """Delete every element that references a removed layer. Groups survive, even empty.

    Covers: <layer-tree-layer id>, <projectlayers>/<maplayer><id>, legacy
    <legend>/<legendlayer> (via <legendlayerfile layerid>), <layerorder>/<layer id>,
    <custom-order>/<item>, snapping <layer-setting id>, visibility-preset
    <layer id>, print-layout <LayerSet>/<Layer>text, plus any other element
    carrying an `id`/`layerid` attribute equal to a removed id.
    """
    if not remove_ids:
        return 0
    parents = _parent_map(root)
    doomed: list[ET.Element] = []

    for el in root.iter():
        if el.tag == "layer-tree-group" or el is root:
            continue  # never remove a group
        if el.tag == "maplayer" and (el.findtext("id") or "").strip() in remove_ids:
            doomed.append(el)
        elif el.get("id") in remove_ids or el.get("layerid") in remove_ids:
            doomed.append(el)
        elif el.tag in {"item", "Layer"} and (el.text or "").strip() in remove_ids:
            doomed.append(el)  # <custom-order><item>, <LayerSet><Layer>
        elif el.tag == "legendlayer" and any(
            f.get("layerid") in remove_ids for f in el.iter("legendlayerfile")
        ):
            doomed.append(el)

    # Drop nested doomed nodes whose ancestor is also doomed (removing the
    # ancestor takes them with it; removing them first would break the parent map).
    doomed_set = set(doomed)
    removed = 0
    for el in doomed:
        anc = parents.get(el)
        while anc is not None and anc not in doomed_set:
            anc = parents.get(anc)
        if anc is not None:
            continue
        parents[el].remove(el)
        removed += 1
    return removed


def retitle(root: ET.Element, title: str) -> None:
    root.set("projectname", title)
    t = root.find("title")
    if t is None:
        t = ET.SubElement(root, "title")
    t.text = title
    meta_title = root.find("./projectMetadata/title")
    if meta_title is not None:
        meta_title.text = title


# ── the one-call API ──────────────────────────────────────────────────────────

def build_client_project(
    base_xml: bytes,
    opportunity: str,
    keep: Iterable[str] = (),
    keep_basemaps: bool = True,
) -> tuple[bytes, Report]:
    """Return (new .qgs bytes, report) for a client clone of `base_xml`."""
    prolog, body = split_prolog(base_xml)
    root = ET.fromstring(body)
    groups, layers = inventory(root)
    remove_ids = select_removals(layers, keep=keep, keep_basemaps=keep_basemaps)

    report = Report(opportunity=opportunity, slug=slugify(opportunity), groups=groups)
    report.removed = [lay for lay in layers if lay.id in remove_ids]
    report.kept = [lay for lay in layers if lay.id not in remove_ids]

    strip_layers(root, remove_ids)
    retitle(root, opportunity)

    out = prolog.encode("utf-8") + ET.tostring(root, encoding="utf-8")
    return out, report


def write_qgz(out_path: Path, qgs_bytes: bytes) -> None:
    """Write a .qgz whose inner .qgs shares the archive's basename (QGIS convention)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(out_path.stem + ".qgs", qgs_bytes)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", required=True, type=Path, help="home-farm base plan (.qgz)")
    p.add_argument("--opportunity",
                   help="client opportunity, '<crm.lead id> <lead name>' (e.g. '142 Smith Hollow'); becomes the project title and, slugified, the file name")
    p.add_argument("--out-dir", type=Path, default=Path("."), help="where to write <slug>.qgz (default: cwd)")
    p.add_argument("--keep", action="append", default=[], metavar="GLOB",
                   help="layer name or id glob to keep in addition to basemaps (repeatable, e.g. --keep 'Contours*')")
    p.add_argument("--no-basemaps", action="store_true", help="also drop XYZ/WMS/vector-tile basemap layers")
    p.add_argument("--list", action="store_true", help="print the base plan's groups and layers and exit")
    p.add_argument("--dry-run", action="store_true", help="report what would be written, write nothing")
    p.add_argument("--force", action="store_true", help="overwrite an existing <slug>.qgz")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.base.is_file():
        print(f"error: base plan not found: {args.base}", file=sys.stderr)
        return 2
    _, base_xml = read_qgs(args.base)

    if args.list:
        _, body = split_prolog(base_xml)
        groups, layers = inventory(ET.fromstring(body))
        print(f"{args.base}: {len(groups)} groups, {len(layers)} layers")
        for lay in layers:
            print(f"  {'/'.join(lay.group_path) or '<root>'} / {lay.name}  [{lay.provider}]{'  (basemap)' if lay.is_basemap else ''}")
        return 0

    if not args.opportunity:
        print("error: --opportunity is required (unless --list)", file=sys.stderr)
        return 2
    qgs, report = build_client_project(base_xml, args.opportunity, keep=args.keep, keep_basemaps=not args.no_basemaps)
    out_path = args.out_dir / f"{report.slug}.qgz"
    print(report.render())
    if args.dry_run:
        print(f"dry run: would write {out_path}")
        return 0
    if out_path.exists() and not args.force:
        print(f"error: {out_path} exists (use --force to overwrite)", file=sys.stderr)
        return 1
    write_qgz(out_path, qgs)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
