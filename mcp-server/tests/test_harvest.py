"""Tests for harvest flattening + aggregation (Sprint 6)."""
import harvest


# A representative farmOS log--harvest JSON:API collection:
# two harvest logs, each referencing an asset + a quantity; quantities and
# units live in `included`.
_RESPONSE = {
    "data": [
        {
            "id": "log-1", "type": "log--harvest",
            "attributes": {"name": "Apple pick", "timestamp": "2026-09-15T12:00:00+00:00",
                           "status": "done", "notes": {"value": "first flush"}},
            "relationships": {
                "asset": {"data": [{"type": "asset--tree", "id": "tree-apple"}]},
                "quantity": {"data": [{"type": "quantity--standard", "id": "q1"}]},
            },
        },
        {
            "id": "log-2", "type": "log--harvest",
            "attributes": {"name": "Chestnut gather", "timestamp": "2026-10-02T12:00:00+00:00",
                           "status": "done", "notes": None},
            "relationships": {
                "asset": {"data": [{"type": "asset--tree", "id": "tree-chestnut"}]},
                "quantity": {"data": [{"type": "quantity--standard", "id": "q2"}]},
            },
        },
    ],
    "included": [
        {"type": "asset--tree", "id": "tree-apple", "attributes": {"name": "Apple Heritage"}},
        {"type": "asset--tree", "id": "tree-chestnut", "attributes": {"name": "Chestnut A1"}},
        {"type": "taxonomy_term--unit", "id": "u-kg", "attributes": {"name": "kg"}},
        {"type": "quantity--standard", "id": "q1",
         "attributes": {"measure": "weight", "label": "yield", "value": {"numerator": 12, "denominator": 1}},
         "relationships": {"units": {"data": {"type": "taxonomy_term--unit", "id": "u-kg"}}}},
        {"type": "quantity--standard", "id": "q2",
         "attributes": {"measure": "weight", "label": "yield", "value": {"numerator": 8, "denominator": 1}},
         "relationships": {"units": {"data": {"type": "taxonomy_term--unit", "id": "u-kg"}}}},
    ],
}


# --- quantity_value ---------------------------------------------------------

def test_quantity_value_fraction():
    assert harvest.quantity_value({"value": {"numerator": 12, "denominator": 1}}) == 12.0
    assert harvest.quantity_value({"value": {"numerator": 5, "denominator": 2}}) == 2.5

def test_quantity_value_decimal_field():
    assert harvest.quantity_value({"value": {"decimal": "3.5", "numerator": 7, "denominator": 2}}) == 3.5

def test_quantity_value_plain_and_missing():
    assert harvest.quantity_value({"value": "4.2"}) == 4.2
    assert harvest.quantity_value({}) is None
    assert harvest.quantity_value({"value": {"numerator": 1, "denominator": 0}}) is None


# --- flatten_harvests -------------------------------------------------------

def test_flatten_resolves_assets_quantities_units():
    flat = harvest.flatten_harvests(_RESPONSE)
    assert len(flat) == 2
    apple = next(h for h in flat if h["name"] == "Apple pick")
    assert apple["assets"] == ["Apple Heritage"]
    assert apple["timestamp"].startswith("2026-09-15")
    assert apple["notes"] == "first flush"  # extracted from {value:...}
    q = apple["quantities"][0]
    assert q == {"value": 12.0, "units": "kg", "measure": "weight", "label": "yield"}

def test_flatten_handles_null_notes():
    flat = harvest.flatten_harvests(_RESPONSE)
    chestnut = next(h for h in flat if h["name"] == "Chestnut gather")
    assert chestnut["notes"] is None

def test_flatten_empty():
    assert harvest.flatten_harvests({"data": [], "included": []}) == []


# --- summarize --------------------------------------------------------------

def test_summary_by_asset():
    s = harvest.summarize(harvest.flatten_harvests(_RESPONSE), "asset")
    by = {r["group"]: r for r in s}
    assert by["Apple Heritage"]["total_value"] == 12.0
    assert by["Chestnut A1"]["total_value"] == 8.0
    assert by["Apple Heritage"]["harvest_count"] == 1

def test_summary_by_month():
    s = harvest.summarize(harvest.flatten_harvests(_RESPONSE), "month")
    by = {r["group"]: r["total_value"] for r in s}
    assert by["2026-09"] == 12.0 and by["2026-10"] == 8.0

def test_summary_by_measure():
    s = harvest.summarize(harvest.flatten_harvests(_RESPONSE), "measure")
    assert len(s) == 1 and s[0]["group"] == "weight" and s[0]["total_value"] == 20.0

def test_summary_bad_group_by():
    import pytest
    with pytest.raises(ValueError, match="group_by"):
        harvest.summarize([], "color")
