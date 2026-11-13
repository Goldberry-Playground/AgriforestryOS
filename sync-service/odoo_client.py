"""
Odoo XML-RPC client for the AgriforestryOS sync service.

Thin wrapper over Odoo's external API (xmlrpc) that surfaces the one thing
the sync needs: stock move lines into and out of the Orchard location,
normalized into `Transfer` objects with species/variety resolved from the
product where available.
"""
from __future__ import annotations

import xmlrpc.client

from mapping import Transfer


class OdooError(RuntimeError):
    """Raised on authentication failure or XML-RPC transport errors."""


class OdooClient:
    """Minimal Odoo external-API client scoped to stock-move queries."""

    def __init__(self, url: str, db: str, username: str, password: str) -> None:
        if not all([url, db, username, password]):
            raise ValueError("url, db, username, password are all required")
        self._url = url.rstrip("/")
        self._db = db
        self._username = username
        self._password = password
        self._uid: int | None = None
        # Allow dependency injection of proxies for testing.
        self._common = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")

    def authenticate(self) -> int:
        """Authenticate and cache the uid. Raises OdooError on failure."""
        try:
            uid = self._common.authenticate(self._db, self._username, self._password, {})
        except (xmlrpc.client.Fault, OSError) as exc:
            raise OdooError(f"Odoo connection failed: {exc}") from exc
        if not uid:
            raise OdooError("Odoo authentication failed: bad credentials or db")
        self._uid = uid
        return uid

    def _execute(self, model: str, method: str, *args, **kwargs):
        if self._uid is None:
            self.authenticate()
        try:
            return self._models.execute_kw(
                self._db, self._uid, self._password, model, method, list(args), kwargs
            )
        except (xmlrpc.client.Fault, OSError) as exc:
            raise OdooError(f"Odoo {model}.{method} failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Location lookup
    # ------------------------------------------------------------------

    def find_location_id(self, name: str) -> int | None:
        """Resolve a stock.location id by exact name (e.g. 'Orchard')."""
        ids = self._execute(
            "stock.location", "search",
            [["name", "=", name], ["usage", "=", "internal"]],
        )
        return ids[0] if ids else None

    # ------------------------------------------------------------------
    # Move-line queries
    # ------------------------------------------------------------------

    def _read_transfers(self, domain: list, direction: str) -> list[Transfer]:
        """Run a stock.move.line query and normalize results to Transfers."""
        lines = self._execute(
            "stock.move.line", "search_read", domain,
            fields=["id", "product_id", "lot_id", "date", "location_id", "location_dest_id"],
        )
        if not lines:
            return []

        # Batch-resolve product → category, variety best-effort.
        product_ids = sorted({l["product_id"][0] for l in lines if l.get("product_id")})
        products = {
            p["id"]: p
            for p in self._execute(
                "product.product", "read", product_ids,
                fields=["name", "categ_id", "default_code"],
            )
        } if product_ids else {}

        transfers: list[Transfer] = []
        for line in lines:
            lot = line["lot_id"][1] if line.get("lot_id") else ""
            if not lot:
                # Trees are lot-tracked; a move line with no lot can't be a
                # tree we should sync. Skip rather than create an unkeyed asset.
                continue
            prod = products.get(line["product_id"][0], {}) if line.get("product_id") else {}
            category = prod.get("categ_id")[1] if prod.get("categ_id") else None
            transfers.append(Transfer(
                lot=lot,
                direction=direction,
                product_name=prod.get("name") or (line["product_id"][1] if line.get("product_id") else "Unknown"),
                category_name=category,
                variety=prod.get("name"),  # product name doubles as variety hint
                source="At the Grove Nursery",
                move_line_id=line["id"],
                date=line.get("date"),
            ))
        return transfers

    def moves_into_orchard(self, orchard_location_id: int, since: str | None = None) -> list[Transfer]:
        """Completed move lines whose destination is the Orchard."""
        domain = [
            ["location_dest_id", "=", orchard_location_id],
            ["state", "=", "done"],
        ]
        if since:
            domain.append(["date", ">", since])
        return self._read_transfers(domain, direction="in")

    def moves_out_of_orchard(self, orchard_location_id: int, since: str | None = None) -> list[Transfer]:
        """Completed move lines whose source is the Orchard (sale/removal)."""
        domain = [
            ["location_id", "=", orchard_location_id],
            ["state", "=", "done"],
        ]
        if since:
            domain.append(["date", ">", since])
        return self._read_transfers(domain, direction="out")

    # ------------------------------------------------------------------
    # Harvest receipts (farmOS harvest → Odoo production move)
    # ------------------------------------------------------------------

    def find_product_id(self, name: str) -> int | None:
        """Best-effort product lookup by (case-insensitive) name."""
        if not name:
            return None
        ids = self._execute("product.product", "search", [["name", "ilike", name]])
        return ids[0] if ids else None

    def harvest_receipt_exists(self, origin: str) -> bool:
        """True if a stock.move already carries this farmOS-harvest origin (dedup key)."""
        ids = self._execute("stock.move", "search", [["origin", "=", origin]])
        return bool(ids)

    def create_harvest_receipt(self, product_id: int, quantity: float,
                               date: str | None, origin: str) -> int:
        """Record a harvest as an Odoo production move (Production → Stock).

        A harvest creates new goods, so we model it as an incoming `stock.move`
        from the virtual Production location into the company's stock location,
        increasing on-hand qty of the harvested product. `origin` carries the
        farmOS log UUID for traceability + idempotency.
        """
        prod_loc = self._virtual_location("production")
        stock_loc = self._stock_location()
        product = self._execute("product.product", "read", [product_id],
                                fields=["name", "uom_id"])[0]
        move = {
            "name": product["name"],
            "product_id": product_id,
            "product_uom": product["uom_id"][0],
            "product_uom_qty": quantity,
            "location_id": prod_loc,
            "location_dest_id": stock_loc,
            "origin": origin,
        }
        if date:
            move["date"] = date.replace("T", " ")[:19]
        move_id = self._execute("stock.move", "create", [move])
        # Confirm + mark done so on-hand stock actually increases.
        self._execute("stock.move", "_action_confirm", [move_id])
        self._execute("stock.move", "_action_done", [move_id])
        return move_id

    def _virtual_location(self, kind: str) -> int:
        """Resolve a virtual location id by usage ('production', 'inventory')."""
        ids = self._execute("stock.location", "search", [["usage", "=", kind]])
        if not ids:
            raise OdooError(f"no virtual stock.location with usage={kind!r}")
        return ids[0]

    def _stock_location(self) -> int:
        ids = self._execute("stock.location", "search",
                            [["usage", "=", "internal"]])
        if not ids:
            raise OdooError("no internal stock.location found")
        return ids[0]
