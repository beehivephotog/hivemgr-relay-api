import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import app
from app.security import hash_api_key, new_api_key
from app.store import InMemoryStore


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def shop_and_key(store):
    raw_key = new_api_key()
    shop = store.create_shop("Test Sign Co", hash_api_key(raw_key), "TEST-0001", "active")
    return shop, raw_key


@pytest.fixture
def auth_headers(shop_and_key):
    _, raw_key = shop_and_key
    return {"X-HiveMGR-Key": raw_key}
