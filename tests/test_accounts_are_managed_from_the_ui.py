"""People's accounts are managed from the UI: change your own password; an administrator adds and disables users (LR.36).

Found in the launch review: accounts were made and passwords reset only from the command line inside the container.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


def test_an_administrator_adds_lists_and_disables_a_user(client):
    name = f"u{uuid.uuid4().hex[:8]}"
    added = client.post("/api/users", json={"username": name, "role": "viewer"})
    assert added.status_code == 201 and len(added.json()["password"]) >= 12
    assert client.post("/api/users", json={"username": name}).status_code == 409
    assert {"username": name, "role": "viewer", "disabled": False} in client.get("/api/users").json()
    assert client.patch(f"/api/users/{name}", json={"disabled": True}).status_code == 200
    assert {"username": name, "role": "viewer", "disabled": True} in client.get("/api/users").json()
    assert client.patch("/api/users/testuser", json={"disabled": True}).status_code == 409


@pytest.fixture
def as_a_person(setup_db):
    from app.server.api import create_app
    from app.server.auth import UserInDB, get_current_active_user, get_password_hash
    from app.server.users_api import _set_password

    name = f"p{uuid.uuid4().hex[:8]}"
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (username, hashed_password, disabled, role, tenant_id) VALUES (%s, %s, FALSE, 'operator', 'default')",
                        (name, get_password_hash("first-password-1")))
        conn.commit()
    app = create_app()

    async def person():
        from app.server.auth import get_user

        return get_user(name)

    app.dependency_overrides[get_current_active_user] = person
    with TestClient(app) as test_client:
        yield test_client, name


def test_a_person_changes_their_own_password_only_with_the_current_one(as_a_person):
    from app.server.auth import get_user, verify_password

    client, name = as_a_person
    assert client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "second-password-2"}).status_code == 403
    assert client.post("/api/auth/password", json={"current_password": "first-password-1", "new_password": "short"}).status_code == 422
    assert client.post("/api/auth/password", json={"current_password": "first-password-1", "new_password": "second-password-2"}).status_code == 200
    assert verify_password("second-password-2", get_user(name).hashed_password)


def test_a_viewer_cannot_manage_users(setup_db):
    from app.server.api import create_app
    from app.server.auth import UserInDB, get_current_active_user

    app = create_app()

    async def viewer():
        return UserInDB(username="reader", hashed_password="x", disabled=False, role="viewer", tenant_id="default")

    app.dependency_overrides[get_current_active_user] = viewer
    with TestClient(app) as client:
        assert client.get("/api/users").status_code == 403
