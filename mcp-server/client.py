"""
farmOS JSON:API client for the AgriforestryOS MCP server.

Provides a thin async HTTP wrapper around the farmOS JSON:API with:
- Basic auth injection
- JSON:API Accept header
- Error envelope parsing (422, 4xx, 5xx → ToolError with human-readable messages)
"""
import httpx
from fastmcp.exceptions import ToolError


class FarmOSClient:
    """Async client for the farmOS JSON:API."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        if not base_url:
            raise ValueError("base_url must not be empty")
        if not username:
            raise ValueError("username must not be empty")
        if not password:
            raise ValueError("password must not be empty")
        self._base_url = base_url.rstrip("/")
        self._auth = httpx.BasicAuth(username, password)
        self._headers = {"Accept": "application/vnd.api+json"}

    async def get(self, path: str, params: dict | None = None) -> dict:
        """GET a JSON:API endpoint and return the full response body as a dict.

        Raises ToolError on any connection problem or HTTP 4xx/5xx.
        """
        url = self._base_url + path
        try:
            async with httpx.AsyncClient(
                auth=self._auth,
                headers=self._headers,
                timeout=30.0,
            ) as client:
                response = await client.get(url, params=params)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError) as exc:
            raise ToolError(f"farmOS is unreachable: {exc}") from exc

        if response.status_code >= 400:
            content_type = response.headers.get("content-type", "")
            if "application/vnd.api+json" in content_type:
                try:
                    body = response.json()
                    errors = body.get("errors", [])
                    parts = []
                    for err in errors:
                        title = err.get("title", "")
                        detail = err.get("detail", "")
                        pointer = err.get("source", {}).get("pointer", "")
                        parts.append(f"{title}: {detail} [{pointer}]".strip(": []"))
                    msg = "; ".join(parts) if parts else f"HTTP {response.status_code}"
                    raise ToolError(f"farmOS rejected the request: {msg}")
                except ToolError:
                    raise
                except Exception:
                    pass
            raise ToolError(
                f"farmOS returned HTTP {response.status_code}: {response.text[:200]}"
            )

        return response.json()

    async def get_single(self, path: str, params: dict | None = None) -> dict:
        """GET a single JSON:API resource and return the `data` member."""
        body = await self.get(path, params=params)
        return body["data"]
