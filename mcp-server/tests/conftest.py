from pathlib import Path
import json
import pytest
from client import FarmOSClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def load_fixture():
    def _load(name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())
    return _load

@pytest.fixture
def farm_client():
    return FarmOSClient("http://farmos.local", "admin", "admin")
