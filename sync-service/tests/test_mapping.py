"""Pure-function tests for the Odoo → farmOS mapping rules."""
from mapping import Transfer, build_tree_attributes, determine_tenure


# ---------------------------------------------------------------------------
# determine_tenure
# ---------------------------------------------------------------------------

def test_tenure_defaults_to_permanent():
    assert determine_tenure("Plants / Trees", {"Plants / Nursery Stock"}) == "permanent"


def test_tenure_nursery_stock_when_category_matches():
    cats = {"Plants / Nursery Stock"}
    assert determine_tenure("Plants / Nursery Stock", cats) == "nursery_stock"


def test_tenure_permanent_when_category_none():
    assert determine_tenure(None, {"Plants / Nursery Stock"}) == "permanent"


def test_tenure_permanent_when_no_nursery_categories_configured():
    assert determine_tenure("Anything", set()) == "permanent"


# ---------------------------------------------------------------------------
# build_tree_attributes
# ---------------------------------------------------------------------------

def _transfer(**kw) -> Transfer:
    base = dict(lot="LOT-001", direction="in", product_name="Eastern Redbud")
    base.update(kw)
    return Transfer(**base)


def test_build_attributes_core_fields():
    attrs = build_tree_attributes(_transfer(), "nursery_stock")
    assert attrs["name"] == "Eastern Redbud [LOT-001]"
    assert attrs["status"] == "active"
    assert attrs["odoo_lot"] == "LOT-001"
    assert attrs["tenure"] == "nursery_stock"


def test_build_attributes_omits_geometry():
    # A freshly transferred tree has no GPS until placed — no geometry key.
    attrs = build_tree_attributes(_transfer(), "permanent")
    assert "intrinsic_geometry" not in attrs
    assert "geometry" not in attrs


def test_build_attributes_includes_optional_variety_and_source():
    attrs = build_tree_attributes(
        _transfer(variety="Honeycrisp", source="At the Grove Nursery"), "permanent"
    )
    assert attrs["variety"] == "Honeycrisp"
    assert attrs["source"] == "At the Grove Nursery"


def test_build_attributes_name_without_lot():
    attrs = build_tree_attributes(_transfer(lot=""), "permanent")
    assert attrs["name"] == "Eastern Redbud"
