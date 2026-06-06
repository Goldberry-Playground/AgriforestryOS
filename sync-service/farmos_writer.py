"""
farmOS JSON:API write client for the sync service.

Unlike the read-only MCP-server client, this one creates and archives Tree
assets. It also resolves (or auto-creates) the `plant_type` taxonomy term
for a tree's species, since JSON:API relationships must reference a term
UUID rather than a bare name.

Auth: HTTP basic (FARMOS_USERNAME / FARMOS_PASSWORD), matching the rest of
the project. OAuth2 client-credentials is a Sprint 5 migration.
"""
from __future__ import annotations

import httpx

_JSONAPI = "application/vnd.api+json"


class FarmOSWriteError(RuntimeError):
    """Raised on unreachable farmOS or a 4xx/5xx write response."""


class FarmOSWriter:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        if not all([base_url, username, password]):
            raise ValueError("base_url, username, password are all required")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            auth=httpx.BasicAuth(username, password),
            headers={"Accept": _JSONAPI, "Content-Type": _JSONAPI},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FarmOSWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        url = self._base_url + path
        try:
            resp = self._client.request(method, url, json=json)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as exc:
            raise FarmOSWriteError(f"farmOS is unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise FarmOSWriteError(
                f"farmOS {method} {path} → HTTP {resp.status_code}: {resp.text[:300]}"
            )
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ------------------------------------------------------------------
    # Lookups (idempotency)
    # ------------------------------------------------------------------

    def find_tree_by_lot(self, lot: str, status: str | None = None) -> dict | None:
        """Return the first Tree asset matching odoo_lot (optionally by status)."""
        params = f"?filter[odoo_lot]={httpx.QueryParams({'v': lot})['v']}"
        if status:
            params += f"&filter[status]={status}"
        body = self._request("GET", f"/jsonapi/asset/tree{params}")
        data = body.get("data", [])
        return data[0] if data else None

    def resolve_or_create_term(self, vocabulary: str, name: str) -> str:
        """Return the UUID of a taxonomy term by name, creating it if absent.

        Mirrors farmOS's auto_create behaviour, which JSON:API can't trigger
        through a relationship write — the term must exist first.
        """
        params = f"?filter[name]={httpx.QueryParams({'v': name})['v']}"
        body = self._request("GET", f"/jsonapi/taxonomy_term/{vocabulary}{params}")
        data = body.get("data", [])
        if data:
            return data[0]["id"]
        created = self._request(
            "POST", f"/jsonapi/taxonomy_term/{vocabulary}",
            json={"data": {"type": f"taxonomy_term--{vocabulary}",
                           "attributes": {"name": name}}},
        )
        return created["data"]["id"]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create_tree(self, attributes: dict, species_name: str | None = None) -> dict:
        """Create a Tree asset; attach the species relationship if given."""
        payload: dict = {"data": {"type": "asset--tree", "attributes": attributes}}
        if species_name:
            term_id = self.resolve_or_create_term("plant_type", species_name)
            payload["data"]["relationships"] = {
                "species": {"data": {"type": "taxonomy_term--plant_type", "id": term_id}}
            }
        body = self._request("POST", "/jsonapi/asset/tree", json=payload)
        return body.get("data", {})

    def archive_tree(self, asset_id: str) -> dict:
        """Archive a Tree asset (status=archived). Keeps history; drops off the active map."""
        payload = {"data": {"type": "asset--tree", "id": asset_id,
                            "attributes": {"status": "archived"}}}
        body = self._request("PATCH", f"/jsonapi/asset/tree/{asset_id}", json=payload)
        return body.get("data", {})
