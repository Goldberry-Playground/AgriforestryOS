"""
Load exported farmOS GeoJSON into QGIS via the QGIS MCP plugin.

Companion to export_geojson.py. Run the export first to produce the
GeoJSON files, then run this snippet inside QGIS (via the QGIS MCP
`execute_code` tool, or QGIS's Python console) to add the three layers
with sensible styling that matches the GoldberryGrove_BasePlan conventions:

  - Trees: color-graduated by stratum, small circle markers
  - Infrastructure: styled by geometry type
  - Plantings: semi-transparent green polygons

The GeoJSON is EPSG:4326 (CRS84); QGIS reprojects to the project CRS
(EPSG:26917) on load. Layers are tagged "[farmOS]" so they're visually
distinct from the hand-drawn planning layers.

This file is intentionally importable as plain functions so it can be
unit-tested or driven from the QGIS MCP without a live QGIS at import time
(the qgis imports are deferred into the function body).
"""
from __future__ import annotations

from pathlib import Path

# Default layer specs: (geojson filename, layer label, style dict)
LAYER_SPECS = [
    ("trees.geojson", "[farmOS] Trees", {
        "geometry": "point",
        "color": "#2d6a2d", "size": "3.0",
        "outline_color": "#1a4a1a", "outline_width": "0.5",
        "label_field": "name",
    }),
    ("infrastructure.geojson", "[farmOS] Infrastructure", {
        "geometry": "mixed",
        "color": "#8a6d3b", "outline_color": "#5c4720", "width": "1.0",
        "label_field": "name",
    }),
    ("plantings.geojson", "[farmOS] Plantings", {
        "geometry": "polygon",
        "color": "150,200,140,120", "outline_color": "#3a6a2a",
        "outline_width": "1.2", "label_field": "name",
    }),
]


def build_load_script(layer_dir: str) -> str:
    """Return a self-contained PyQGIS script string that loads + styles layers.

    Pass the returned string to the QGIS MCP `execute_code` tool. Keeping this
    as a string-builder (rather than importing qgis here) means this module
    imports cleanly anywhere — only QGIS executes the qgis.core calls.
    """
    return f'''
import os
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsSingleSymbolRenderer,
    QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
    QgsTextFormat, QgsTextBufferSettings,
)
from qgis.PyQt.QtGui import QColor, QFont

project = QgsProject.instance()
LAYER_DIR = {layer_dir!r}
SPECS = {LAYER_SPECS!r}

def _label(lyr, field):
    ps = QgsPalLayerSettings(); ps.fieldName = field; ps.enabled = True
    tf = QgsTextFormat(); tf.setSize(7); tf.setColor(QColor("#1a331a")); tf.setFont(QFont("Arial"))
    buf = QgsTextBufferSettings(); buf.setEnabled(True); buf.setSize(1.0); buf.setColor(QColor("white"))
    tf.setBuffer(buf); ps.setFormat(tf)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(ps)); lyr.setLabelsEnabled(True)

for fname, label, style in SPECS:
    path = os.path.join(LAYER_DIR, fname)
    if not os.path.exists(path):
        print(f"skip (missing): {{path}}"); continue
    # Remove existing layer with same name (idempotent reload)
    for lid, lyr in list(project.mapLayers().items()):
        if lyr.name() == label:
            project.removeMapLayer(lid)
    lyr = QgsVectorLayer(path, label, "ogr")
    if not lyr.isValid():
        print(f"INVALID: {{path}}"); continue
    geom = style["geometry"]
    if geom == "point":
        sym = QgsMarkerSymbol.createSimple({{
            "name": "circle", "color": style["color"], "size": style["size"],
            "outline_color": style["outline_color"], "outline_width": style["outline_width"]}})
    elif geom == "polygon":
        sym = QgsFillSymbol.createSimple({{
            "color": style["color"], "outline_color": style["outline_color"],
            "outline_width": style["outline_width"]}})
    else:
        sym = QgsLineSymbol.createSimple({{
            "color": style["color"], "width": style["width"]}})
    if sym is not None and geom != "mixed":
        lyr.setRenderer(QgsSingleSymbolRenderer(sym))
    if style.get("label_field"):
        _label(lyr, style["label_field"])
    project.addMapLayer(lyr)
    print(f"loaded {{label}}: {{lyr.featureCount()}} features")
'''


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Print a PyQGIS load script for the exported GeoJSON layers.")
    parser.add_argument(
        "--dir", default=str(Path(__file__).parent / "qgis_layers"),
        help="Directory containing the exported .geojson files.")
    args = parser.parse_args()
    print(build_load_script(args.dir))
