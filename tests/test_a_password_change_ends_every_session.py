"""A password change, a sign-out everywhere, or disabling a person ends every session they have (LR.36).

Found in the launch review: refresh tokens lasted seven days with no revocation; a password reset left every token
already issued working, so a stolen one stayed good until it expired.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def person(setup_db):
    from app.server.api import create_app
    from app.server.auth import get_db_connection, get_password_hash

    name = f"s{uuid.uuid4().hex[:8]}"
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (username, hashed_password, disabled, role, tenant_id) "
                        "VALUES (%s, %s, FALSE, 'operator', 'default')", (name, get_password_hash("first-password-1")))
        conn.commit()
    with TestClient(create_app()) as client:
        yield client, name


def _sign_in(client, name, password="first-password-1"):
    answer = client.post("/api/auth/token", data={"username": name, "password": password})
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_password_change_ends_the_old_tokens_and_the_new_password_signs_in(person):
    client, name = person
    old = _sign_in(client, name)
    headers = {"Authorization": f"Bearer {old['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/password", headers=headers,
                       json={"current_password": "first-password-1", "new_password": "second-password-2"}).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401
    fresh = _sign_in(client, name, "second-password-2")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh['access_token']}"}).status_code == 200


def test_signing_out_everywhere_ends_every_session(person):
    client, name = person
    one, two = _sign_in(client, name), _sign_in(client, name)
    assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {one['access_token']}"}).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {two['access_token']}"}).status_code == 401
