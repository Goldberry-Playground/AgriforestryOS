"""
Minimal farmOS JSON:API read client for the PostGIS ETL.

Self-contained (httpx + basic auth) so the ETL package has no dependency on
the MCP server. Only what the ETL needs: paginated GET of an asset
collection with included relationships.
"""
from __future__ import annotations

import httpx

_JSONAPI = "application/vnd.api+json"


class FarmOSReadError(RuntimeError):
    """Unreachable farmOS or a 4xx/5xx response."""


class FarmOSReadClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        if not all([base_url, username, password]):
            raise ValueError("base_url, username, password are all required")
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            auth=httpx.BasicAuth(username, password),
            headers={"Accept": _JSONAPI},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FarmOSReadClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, url: str, params: dict | None = None) -> dict:
        try:
            resp = self._client.get(url, params=params)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as exc:
            raise FarmOSReadError(f"farmOS is unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise FarmOSReadError(
                f"farmOS GET {url} → HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    def fetch_all(self, endpoint: str, include: list[str] | None = None) -> dict:
        """Fetch every page of a JSON:API collection.

        Returns {"data": [...all records...], "included": [...all included...]}.
        Follows links.next until exhausted.
        """
        params: dict = {"page[limit]": "50"}
        if include:
            params["include"] = ",".join(include)
        url = self._base_url + endpoint

        data: list = []
        included: list = []
        while True:
            body = self._get(url, params=params)
            data.extend(body.get("data", []))
            included.extend(body.get("included", []))
            nxt = body.get("links", {}).get("next", {})
            href = nxt.get("href") if isinstance(nxt, dict) else None
            if not href:
                break
            url, params = href, None  # next href is fully-formed
        return {"data": data, "included": included}
