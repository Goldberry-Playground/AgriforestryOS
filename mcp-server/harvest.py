"""
Harvest / yield flattening + aggregation (Sprint 6).

Pure, I/O-free transforms over the farmOS `log--harvest` JSON:API response,
backing the `list_harvests` and `harvest_summary` MCP tools. Kept separate
from server.py so the flatten/aggregate logic is unit-testable without a live
farmOS.

farmOS shape: a harvest log references harvested *assets* (multiple) and
*quantities* (multiple). Each quantity is a separate `quantity--standard`
resource with a `value` (a fraction: numerator/denominator), a `measure`
(count, weight, …), a `label`, and a `units` taxonomy term. All of these
arrive in the JSON:API `included` array.
"""
from __future__ import annotations

from collections import defaultdict


def quantity_value(attrs: dict) -> float | None:
    """Extract a numeric value from a farmOS quantity's `value` attribute.

    farmOS stores it as a fraction object {numerator, denominator}; older/other
    shapes may give a plain number or a decimal string. Returns None if absent.
    """
    v = attrs.get("value")
    if v is None:
        return None
    if isinstance(v, dict):
        # fraction form
        if "decimal" in v and v["decimal"] not in (None, ""):
            try:
                return float(v["decimal"])
            except (TypeError, ValueError):
                pass
        num, den = v.get("numerator"), v.get("denominator")
        if num is not None and den:
            try:
                return float(num) / float(den)
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _index_included(included: list) -> tuple[dict, dict]:
    """Return (resources_by_id, names_by_id) for the included array."""
    resources, names = {}, {}
    for inc in included:
        rid = inc.get("id", "")
        if not rid:
            continue
        resources[rid] = inc
        nm = inc.get("attributes", {}).get("name")
        if nm:
            names[rid] = nm
    return resources, names


def flatten_harvests(response: dict) -> list[dict]:
    """Flatten a JSON:API harvest-log collection into plain dicts.

    Each result: {id, name, timestamp, status, notes, assets: [names],
    quantities: [{value, units, measure, label}]}.
    """
    resources, names = _index_included(response.get("included", []))
    out: list[dict] = []
    for log in response.get("data", []):
        attrs = log.get("attributes", {})
        rels = log.get("relationships", {})

        asset_names = []
        for ref in _rel_list(rels.get("asset")):
            if ref["id"] in names:
                asset_names.append(names[ref["id"]])

        quantities = []
        for ref in _rel_list(rels.get("quantity")):
            q = resources.get(ref["id"])
            if not q:
                continue
            qa = q.get("attributes", {})
            unit_ref = q.get("relationships", {}).get("units", {}).get("data")
            quantities.append({
                "value": quantity_value(qa),
                "units": names.get(unit_ref["id"]) if isinstance(unit_ref, dict) and unit_ref else None,
                "measure": qa.get("measure"),
                "label": qa.get("label"),
            })

        out.append({
            "id": log.get("id"),
            "name": attrs.get("name"),
            "timestamp": attrs.get("timestamp"),
            "status": attrs.get("status"),
            "notes": (attrs.get("notes") or {}).get("value") if isinstance(attrs.get("notes"), dict) else attrs.get("notes"),
            "assets": asset_names,
            "quantities": quantities,
        })
    return out


def _rel_list(rel: dict | None) -> list[dict]:
    """Normalize a JSON:API relationship to a list of {type,id} refs."""
    if not rel:
        return []
    data = rel.get("data")
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def summarize(harvests: list[dict], group_by: str = "asset") -> list[dict]:
    """Aggregate harvest quantities by a dimension.

    group_by:
      - "asset"   → per harvested asset name
      - "month"   → per YYYY-MM of the timestamp
      - "measure" → per quantity measure (count, weight, …)

    Returns [{group, total_value, harvest_count}] sorted by group. Quantities
    with no numeric value are counted but contribute 0 to total_value.
    """
    if group_by not in ("asset", "month", "measure"):
        raise ValueError(f"group_by must be asset|month|measure, got {group_by!r}")

    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for h in harvests:
        keys = _group_keys(h, group_by)
        for q in h["quantities"] or [{}]:
            val = q.get("value") or 0.0
            for k in keys:
                totals[k] += val
        for k in keys:
            counts[k] += 1

    return [
        {"group": k, "total_value": round(totals[k], 3), "harvest_count": counts[k]}
        for k in sorted(totals)
    ]


def _group_keys(harvest: dict, group_by: str) -> list[str]:
    if group_by == "asset":
        return harvest["assets"] or ["(no asset)"]
    if group_by == "month":
        ts = harvest.get("timestamp") or ""
        return [ts[:7] if len(ts) >= 7 else "(undated)"]
    # measure
    measures = {q.get("measure") for q in (harvest["quantities"] or []) if q.get("measure")}
    return sorted(measures) or ["(no measure)"]
