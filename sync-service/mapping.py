"""
Pure transforms: Odoo stock move → farmOS Tree asset attributes.

Kept free of I/O so the mapping rules are unit-testable in isolation. The
sync orchestrator (sync.py) wires these to the live Odoo and farmOS clients.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Transfer:
    """A normalized Odoo stock move line involving the Orchard location.

    Produced by OdooClient; consumed by the mapping functions below. `lot`
    is the dedup key (becomes farmOS odoo_lot). `direction` is "in" (into
    Orchard → create tree) or "out" (out of Orchard → archive tree).
    """
    lot: str
    direction: str            # "in" | "out"
    product_name: str
    category_name: str | None = None
    species: str | None = None
    variety: str | None = None
    source: str | None = None
    move_line_id: int | None = None
    date: str | None = None   # ISO8601 from Odoo


def determine_tenure(category_name: str | None, nursery_stock_categories: set[str]) -> str:
    """Classify a tree as permanent orchard planting vs. saleable nursery stock.

    A product whose category is in `nursery_stock_categories` (e.g.
    "Plants / Nursery Stock") is temporary alley-crop stock destined for
    sale. Everything else defaults to a permanent orchard planting — the
    safe default, since misclassifying permanent stock as saleable is worse
    than the reverse.
    """
    if category_name and category_name in nursery_stock_categories:
        return "nursery_stock"
    return "permanent"


def build_tree_attributes(transfer: Transfer, tenure: str) -> dict:
    """Build the farmOS Tree asset attribute dict for a move-in transfer.

    Geometry is intentionally omitted — a freshly transferred tree has no
    GPS location until it is physically placed and recorded. It appears in
    farmOS (and is styled distinctly on the map by tenure) but carries no
    point until coordinates are added.
    """
    name = transfer.product_name
    if transfer.lot:
        name = f"{name} [{transfer.lot}]"

    attrs: dict = {
        "name": name,
        "status": "active",
        "odoo_lot": transfer.lot,
        "tenure": tenure,
    }
    if transfer.variety:
        attrs["variety"] = transfer.variety
    if transfer.source:
        attrs["source"] = transfer.source
    return attrs
