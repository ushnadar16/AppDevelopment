import os
import sys

os.environ.setdefault("DAY1_SALT", "demo-salt")
os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/audit/v1/reset", json={})
        yield c
