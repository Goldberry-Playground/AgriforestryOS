"""Tests for the QGIS layer specs — client-tree split (consult phase 1 A).

load_qgis_layers imports no qgis at module scope (the qgis calls live inside
the generated script string), so these run without a live QGIS.
"""
import load_qgis_layers as lq


def _specs_for(fname):
    return [(f, label, style) for (f, label, style) in lq.LAYER_SPECS if f == fname]


def test_two_tree_layers_home_and_client():
    tree_specs = _specs_for("trees.geojson")
    labels = {label for (_f, label, _s) in tree_specs}
    assert labels == {"[farmOS] Trees", "[farmOS] Client Trees"}


def test_home_farm_trees_exclude_client_in_home_group():
    (_f, _label, style) = next(s for s in lq.LAYER_SPECS if s[1] == "[farmOS] Trees")
    assert style["group"] == lq.HOME_FARM_GROUP
    # Keeps NULL-tenure (hand-entered) trees, drops client.
    assert style["subset"] == "tenure IS NULL OR tenure <> 'client'"


def test_client_trees_own_symbol_separate_group_hidden():
    (_f, _label, style) = next(s for s in lq.LAYER_SPECS if s[1] == "[farmOS] Client Trees")
    assert style["group"] == lq.CLIENT_GROUP
    assert style["group"] != lq.HOME_FARM_GROUP
    assert style["subset"] == "tenure = 'client'"
    assert style["visible"] is False
    # A distinct marker from the home-farm green circle.
    assert style["marker"] == "diamond"
    assert style["color"] != "#2d6a2d"


def test_generated_script_applies_subset_and_groups():
    script = lq.build_load_script("/tmp/qgis_layers")
    assert "setSubsetString" in script
    assert "addGroup" in script
    assert "setItemVisibilityChecked" in script
    assert "addMapLayer(lyr, False)" in script
