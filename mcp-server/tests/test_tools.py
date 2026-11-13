"""
Tests for the AgriforestryOS MCP server tools.

All HTTP calls are intercepted by pytest-httpx — no live farmOS required.
The monkeypatch fixture injects env vars so server.py can import cleanly.
"""
import pytest
import httpx
from pytest_httpx import HTTPXMock
from client import FarmOSClient
from fastmcp.exceptions import ToolError


# ---------------------------------------------------------------------------
# client.py error handling tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_validation_error_surfaces_plain_text(
    httpx_mock: HTTPXMock, load_fixture
):
    fixture = load_fixture("validation_error_dbh_too_high.json")
    httpx_mock.add_response(
        method="GET",
        url="http://farmos.local/jsonapi/asset/tree",
        status_code=422,
        headers={"Content-Type": "application/vnd.api+json"},
        json=fixture,
    )
    client = FarmOSClient("http://farmos.local", "admin", "admin")
    with pytest.raises(ToolError) as exc_info:
        await client.get("/jsonapi/asset/tree")
    assert "farmOS rejected the request" in str(exc_info.value)
    assert "dbh_cm" in str(exc_info.value)


@pytest.mark.asyncio
async def test_client_unreachable_farmos(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
    client = FarmOSClient("http://farmos.local", "admin", "admin")
    with pytest.raises(ToolError) as exc_info:
        await client.get("/jsonapi/asset/tree")
    assert "farmOS is unreachable" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tool tests — each uses monkeypatch for env vars and httpx_mock for HTTP
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    monkeypatch.setenv("FARMOS_BASE_URL", "http://farmos.local")
    monkeypatch.setenv("FARMOS_USERNAME", "admin")
    monkeypatch.setenv("FARMOS_PASSWORD", "admin")


@pytest.mark.asyncio
async def test_list_asset_types(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("asset_types.json")
    httpx_mock.add_response(
        method="GET",
        url="http://farmos.local/jsonapi/asset_type/asset_type",
        json=fixture,
    )
    from server import list_asset_types
    result = await list_asset_types()
    assert isinstance(result, list)
    assert len(result) >= 2
    assert any(item["id"] == "tree" for item in result)
    assert all("id" in item and "label" in item for item in result)


@pytest.mark.asyncio
async def test_count_trees_no_filter(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("trees_collection.json")
    httpx_mock.add_response(method="GET", json=fixture)
    from server import count_trees
    result = await count_trees()
    assert result["count"] == 1
    assert result["filters_applied"] == {}


@pytest.mark.asyncio
async def test_count_trees_by_species(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("trees_filtered_by_species.json")
    httpx_mock.add_response(method="GET", json=fixture)
    from server import count_trees
    result = await count_trees(species="American Chestnut")
    assert result["count"] == 1
    assert result["filters_applied"].get("species") == "American Chestnut"


@pytest.mark.asyncio
async def test_query_trees_default_fields_url(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("trees_collection.json")
    httpx_mock.add_response(method="GET", json=fixture)
    from server import query_trees
    await query_trees()
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    url_str = str(requests[0].url)
    assert "name" in url_str
    assert "dbh_cm" in url_str


@pytest.mark.asyncio
async def test_query_trees_limit_caps_at_500(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("trees_collection.json")
    httpx_mock.add_response(method="GET", json=fixture)
    from server import query_trees
    await query_trees(limit=999)
    requests = httpx_mock.get_requests()
    url_str = str(requests[0].url)
    assert "500" in url_str
    assert "999" not in url_str


@pytest.mark.asyncio
async def test_query_trees_sparse_fields_override(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("trees_collection.json")
    httpx_mock.add_response(method="GET", json=fixture)
    from server import query_trees
    await query_trees(fields=["id", "name"])
    requests = httpx_mock.get_requests()
    url_str = str(requests[0].url)
    assert "name" in url_str
    assert "height_m" not in url_str


@pytest.mark.asyncio
async def test_get_tree_by_uuid(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("tree_single.json")
    tree_uuid = fixture["data"]["id"]
    httpx_mock.add_response(method="GET", json=fixture)
    from server import get_tree
    result = await get_tree(id=tree_uuid)
    assert result["id"] == tree_uuid
    assert "name" in result
    assert "dbh_cm" in result


@pytest.mark.asyncio
async def test_get_tree_404(httpx_mock: HTTPXMock):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    httpx_mock.add_response(
        method="GET",
        status_code=404,
        headers={"Content-Type": "application/vnd.api+json"},
        json={"errors": [{"title": "Not Found", "detail": "The requested entity was not found.", "source": {"pointer": "/data"}}]},
    )
    from server import get_tree
    with pytest.raises(ToolError) as exc_info:
        await get_tree(id=fake_uuid)
    assert "farmOS rejected the request" in str(exc_info.value)


@pytest.mark.asyncio
async def test_list_infrastructure_no_filter(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("infrastructure_needs_repair.json")
    httpx_mock.add_response(method="GET", json=fixture)
    from server import list_infrastructure
    result = await list_infrastructure()
    assert isinstance(result, list)
    assert all("id" in item and "name" in item for item in result)


@pytest.mark.asyncio
async def test_list_infrastructure_condition_filter(httpx_mock: HTTPXMock, load_fixture):
    fixture = load_fixture("infrastructure_needs_repair.json")
    httpx_mock.add_response(method="GET", json=fixture)
    from server import list_infrastructure
    result = await list_infrastructure(condition="needs_repair")
    assert isinstance(result, list)
