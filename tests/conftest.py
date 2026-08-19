"""Shared fixtures. These tests run against the real dev stack.

Isolation is the thing under test, so nothing here is mocked — a
mocked Qdrant would prove only that the mock was written correctly.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.db import postgres as db
from app.db.qdrant import ensure_collection

PASSWORD = "testpass123"


@pytest.fixture(scope="session", autouse=True)
def stack():
    """Open the pool and make sure the schema and collection exist."""
    db.pool.open()
    db.apply_schema()
    ensure_collection()
    yield
    db.pool.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def make_tenant(client):
    """Register a brand new tenant and return its admin's details."""
    created = []

    def _make() -> dict:
        email = f"admin-{uuid.uuid4().hex[:12]}@example.test"
        response = client.post(
            "/auth/register", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 201, response.text
        token = response.json()["access_token"]

        me = client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        created.append(me["tenant_id"])

        return {
            "email": email,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
            "tenant_id": me["tenant_id"],
            "user_id": me["user_id"],
        }

    yield _make

    for tenant_id in created:
        db.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant_id,))
