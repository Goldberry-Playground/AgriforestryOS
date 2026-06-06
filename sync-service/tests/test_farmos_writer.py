"""HTTP-mocked tests for FarmOSWriter (create, archive, term resolution)."""
import pytest
from pytest_httpx import HTTPXMock

from farmos_writer import FarmOSWriter, FarmOSWriteError


@pytest.fixture
def writer():
    w = FarmOSWriter("http://farmos.local", "admin", "admin")
    yield w
    w.close()


def test_find_tree_by_lot_returns_first(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(json={"data": [{"id": "t-1", "attributes": {"odoo_lot": "L1"}}]})
    tree = writer.find_tree_by_lot("L1")
    assert tree["id"] == "t-1"


def test_find_tree_by_lot_none_when_empty(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(json={"data": []})
    assert writer.find_tree_by_lot("L1") is None


def test_resolve_term_returns_existing(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(json={"data": [{"id": "term-7"}]})
    assert writer.resolve_or_create_term("plant_type", "Apple") == "term-7"


def test_resolve_term_creates_when_missing(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(json={"data": []})                       # lookup miss
    httpx_mock.add_response(json={"data": {"id": "term-new"}})       # create
    assert writer.resolve_or_create_term("plant_type", "Pawpaw") == "term-new"


def test_create_tree_attaches_species_relationship(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(json={"data": [{"id": "term-3"}]})       # species lookup
    httpx_mock.add_response(json={"data": {"id": "tree-1"}})         # create tree
    result = writer.create_tree(
        {"name": "Redbud [L1]", "odoo_lot": "L1", "tenure": "nursery_stock"},
        species_name="Eastern Redbud",
    )
    assert result["id"] == "tree-1"
    # Verify the POST body wired the species relationship.
    create_req = httpx_mock.get_requests()[-1]
    assert b"term-3" in create_req.content
    assert b"relationships" in create_req.content


def test_create_tree_without_species_has_no_relationship(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(json={"data": {"id": "tree-2"}})
    writer.create_tree({"name": "X", "odoo_lot": "L2", "tenure": "permanent"})
    req = httpx_mock.get_requests()[-1]
    assert b"relationships" not in req.content


def test_archive_tree_patches_status(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(json={"data": {"id": "tree-1", "attributes": {"status": "archived"}}})
    writer.archive_tree("tree-1")
    req = httpx_mock.get_requests()[-1]
    assert req.method == "PATCH"
    assert b"archived" in req.content


def test_http_error_raises(httpx_mock: HTTPXMock, writer):
    httpx_mock.add_response(status_code=403, text="Forbidden")
    with pytest.raises(FarmOSWriteError) as exc:
        writer.find_tree_by_lot("L1")
    assert "403" in str(exc.value)
