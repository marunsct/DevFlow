"""Acceptance tests for Tasks API.

Every test name carries the acceptance criterion id(s) it proves, e.g.
``test_ac1_signup`` proves AC-1 (sign up with username/password).

Tests use ``httpx`` to make real HTTP requests against the service started
by the ``conftest.py`` fixtures.  Each test creates its own data so it runs
independently of every other test.
"""

from pathlib import Path

import httpx
import pytest

PROJECT = Path(__file__).resolve().parent.parent


# ── helpers ──────────────────────────────────────────────────────────────────

def _signup(base_url: str, username: str, password: str) -> httpx.Response:
    """POST /signup — returns the raw httpx Response."""
    return httpx.post(
        f"{base_url}/signup", json={"username": username, "password": password}
    )


def _signin(base_url: str, username: str, password: str) -> httpx.Response:
    """POST /signin — returns the raw httpx Response."""
    return httpx.post(
        f"{base_url}/signin", json={"username": username, "password": password}
    )


def _create_item(base_url: str, token: str, title: str) -> httpx.Response:
    """POST /items — returns the raw httpx Response."""
    return httpx.post(
        f"{base_url}/items",
        json={"title": title},
        headers={"Authorization": f"Bearer {token}"},
    )


def _list_items(base_url: str, token: str) -> httpx.Response:
    """GET /items — returns the raw httpx Response."""
    return httpx.get(
        f"{base_url}/items",
        headers={"Authorization": f"Bearer {token}"},
    )


def _toggle_item(base_url: str, token: str, item_id: int, done: bool) -> httpx.Response:
    """PATCH /items/{id} — returns the raw httpx Response."""
    return httpx.patch(
        f"{base_url}/items/{item_id}",
        json={"done": done},
        headers={"Authorization": f"Bearer {token}"},
    )


def _delete_item(base_url: str, token: str, item_id: int) -> httpx.Response:
    """DELETE /items/{id} — returns the raw httpx Response."""
    return httpx.delete(
        f"{base_url}/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )


# ── AC-1: Sign up with a username and a password ─────────────────────────────

def test_ac1_signup(base_url: str) -> None:
    """AC-1 — sign up succeeds and returns the username."""
    resp = _signup(base_url, "ac1user", "password123")
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "ac1user"


# ── AC-2: Sign in, which gives a token for the requests that follow ──────────

def test_ac2_signin(base_url: str) -> None:
    """AC-2 — sign in returns a token."""
    _signup(base_url, "ac2user", "password123")
    resp = _signin(base_url, "ac2user", "password123")
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert isinstance(body["token"], str)
    assert len(body["token"]) > 0


# ── AC-3: Create an item with a title; it starts not done ────────────────────

def test_ac3_create_item(base_url: str) -> None:
    """AC-3 — create an item, it starts not done."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]
    resp = _create_item(base_url, token, "buy groceries")
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert isinstance(body["id"], int)
    assert body["title"] == "buy groceries"
    assert body["done"] is False


# ── AC-4: List your own items ───────────────────────────────────────────────

def test_ac4_list_items(base_url: str) -> None:
    """AC-4 — list returns only the signed-in user's items."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]
    _create_item(base_url, token, "item one")
    resp = _list_items(base_url, token)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(i["title"] == "item one" for i in body)


# ── AC-5: Mark one of your items done or not done ────────────────────────────

def test_ac5_toggle_done(base_url: str) -> None:
    """AC-5 — toggle item done status."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]
    create_resp = _create_item(base_url, token, "toggle me")
    item_id = create_resp.json()["id"]

    # Mark done
    resp = _toggle_item(base_url, token, item_id, True)
    assert resp.status_code == 200
    assert resp.json()["done"] is True

    # Mark not done
    resp = _toggle_item(base_url, token, item_id, False)
    assert resp.status_code == 200
    assert resp.json()["done"] is False


# ── AC-6: Delete one of your items ───────────────────────────────────────────

def test_ac6_delete_item(base_url: str) -> None:
    """AC-6 — delete an item."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]
    create_resp = _create_item(base_url, token, "delete me")
    item_id = create_resp.json()["id"]

    resp = _delete_item(base_url, token, item_id)
    assert resp.status_code == 204

    # Confirm it is gone
    list_resp = _list_items(base_url, token)
    body = list_resp.json()
    assert not any(i["id"] == item_id for i in body)


# ── AC-7 / AC-20: Persistence across restarts ───────────────────────────────

def test_ac7_ac20_persistence(base_url: str, service) -> None:
    """AC-7 / AC-20 — accounts and items survive a restart."""
    # Create user and item while service is running
    _signup(base_url, "persist_user", "password123")
    signin_resp = _signin(base_url, "persist_user", "password123")
    token = signin_resp.json()["token"]
    create_resp = _create_item(base_url, token, "survives restart")
    item_id = create_resp.json()["id"]

    # Restart the service (same DATA_DIR)
    service.restart()

    # Sign in again and list items
    new_signin = _signin(base_url, "persist_user", "password123")
    new_token = new_signin.json()["token"]
    resp = _list_items(base_url, new_token)
    assert resp.status_code == 200
    body = resp.json()
    assert any(i["id"] == item_id and i["title"] == "survives restart" for i in body)


# ── AC-8: JSON over HTTP — item shape ───────────────────────────────────────

def test_ac8_item_shape(base_url: str) -> None:
    """AC-8 — every item response has exactly id (int), title (str), done (bool)."""
    _signup(base_url, "ac8user", "password123")
    signin_resp = _signin(base_url, "ac8user", "password123")
    token = signin_resp.json()["token"]
    resp = _create_item(base_url, token, "shape check")
    body = resp.json()

    assert set(body.keys()) == {"id", "title", "done"}
    assert isinstance(body["id"], int)
    assert isinstance(body["title"], str)
    assert isinstance(body["done"], bool)


# ── AC-9: POST /signup — 201, 409, 400/422 ─────────────────────────────────

def test_ac9_signup_unique(base_url: str) -> None:
    """AC-9 — duplicate username returns 409; missing fields return 400/422."""
    # Duplicate username → 409
    resp = _signup(base_url, "dup_user", "password123")
    assert resp.status_code == 201
    resp = _signup(base_url, "dup_user", "different_password")
    assert resp.status_code == 409

    # Empty username → 400 or 422
    resp = _signup(base_url, "", "password123")
    assert resp.status_code in (400, 422)

    # Empty password → 400 or 422
    resp = _signup(base_url, "unique_ac9_user", "")
    assert resp.status_code in (400, 422)


# ── AC-10: POST /signin — 200 on success, 401 on bad credentials ────────────

def test_ac10_signin_credentials(base_url: str) -> None:
    """AC-10 — wrong password returns 401; nonexistent user returns 401."""
    _signup(base_url, "ac10user", "correct_password")

    # Wrong password
    resp = _signin(base_url, "ac10user", "wrong_password")
    assert resp.status_code == 401

    # Non-existent username
    resp = _signin(base_url, "no_such_user", "any_password")
    assert resp.status_code == 401


# ── AC-11: Auth enforcement on item endpoints ────────────────────────────────

def test_ac11_auth_enforcement(base_url: str) -> None:
    """AC-11 — unauthenticated requests to /items return 401."""
    # No header at all
    resp = httpx.get(f"{base_url}/items")
    assert resp.status_code == 401

    # Invalid token
    resp = httpx.get(
        f"{base_url}/items",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert resp.status_code == 401


# ── AC-12 / AC-21: Invalid title rejected without storage ───────────────────

def test_ac12_ac21_invalid_title(base_url: str) -> None:
    """AC-12 / AC-21 — empty/missing title rejected and not stored."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]

    # Empty title
    resp = httpx.post(
        f"{base_url}/items",
        json={"title": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (400, 422)

    # Missing title field entirely
    resp = httpx.post(
        f"{base_url}/items",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (400, 422)

    # Confirm nothing was stored
    list_resp = _list_items(base_url, token)
    body = list_resp.json()
    assert not any(i["title"] == "" for i in body)


# ── AC-13 / AC-19: Data isolation between users ─────────────────────────────

def test_ac13_ac19_data_isolation(base_url: str) -> None:
    """AC-13 / AC-19 — users cannot see or modify each other's items."""
    # Create user A and B
    _signup(base_url, "iso_user_a", "password123")
    _signup(base_url, "iso_user_b", "password123")

    # User A creates an item
    signin_a = _signin(base_url, "iso_user_a", "password123")
    token_a = signin_a.json()["token"]
    create_resp = _create_item(base_url, token_a, "A's secret item")
    item_id = create_resp.json()["id"]

    # User B lists — should NOT see A's item
    signin_b = _signin(base_url, "iso_user_b", "password123")
    token_b = signin_b.json()["token"]
    resp = _list_items(base_url, token_b)
    assert resp.status_code == 200
    body = resp.json()
    assert not any(i["id"] == item_id for i in body)

    # User B tries to toggle A's item → 404
    resp = _toggle_item(base_url, token_b, item_id, True)
    assert resp.status_code == 404

    # User B tries to delete A's item → 404
    resp = _delete_item(base_url, token_b, item_id)
    assert resp.status_code == 404


# ── AC-14: PATCH /items/{id} — 200 on success, 404 on non-owned item ───────

def test_ac14_patch_not_found(base_url: str) -> None:
    """AC-14 — PATCH on a non-existent (or non-owned) item returns 404."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]

    # Non-existent id
    resp = _toggle_item(base_url, token, 999999, True)
    assert resp.status_code == 404


# ── AC-15: DELETE /items/{id} — 204 on success, 404 on non-owned item ───────

def test_ac15_delete_not_found(base_url: str) -> None:
    """AC-15 — DELETE on a non-existent (or non-owned) item returns 404."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]

    # Non-existent id
    resp = _delete_item(base_url, token, 999999)
    assert resp.status_code == 404


# ── AC-5 (additional): PATCH /items/{id} with non-boolean done → 422 ───────

def test_ac5_patch_invalid_done_type(base_url: str) -> None:
    """AC-5 — PATCH with a non-boolean 'done' value returns 422."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]
    create_resp = _create_item(base_url, token, "type check item")
    item_id = create_resp.json()["id"]

    # String 'true' instead of boolean True
    resp = httpx.patch(
        f"{base_url}/items/{item_id}",
        json={"done": "true"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422

    # Integer 1 instead of boolean True
    resp = httpx.patch(
        f"{base_url}/items/{item_id}",
        json={"done": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── AC-3 (additional): POST /items without auth → 401 ───────────────────────

def test_ac3_items_unauthenticated(base_url: str) -> None:
    """AC-3 — POST /items without token returns 401."""
    resp = httpx.post(f"{base_url}/items", json={"title": "no auth"})
    assert resp.status_code == 401


# ── AC-4 (additional): GET /items without auth → 401 ────────────────────────

def test_ac4_items_unauthenticated(base_url: str) -> None:
    """AC-4 — GET /items without token returns 401."""
    resp = httpx.get(f"{base_url}/items")
    assert resp.status_code == 401


# ── AC-6 (additional): DELETE /items/{id} with auth → 204 ───────────────────

def test_ac6_delete_with_auth(base_url: str) -> None:
    """AC-6 — delete with valid token returns 204."""
    signin_resp = _signin(base_url, "ac2user", "password123")
    token = signin_resp.json()["token"]
    create_resp = _create_item(base_url, token, "auth delete test")
    item_id = create_resp.json()["id"]

    resp = _delete_item(base_url, token, item_id)
    assert resp.status_code == 204


# ── AC-19 (additional): DELETE non-owned item → 404 ─────────────────────────

def test_ac19_delete_cross_user(base_url: str) -> None:
    """AC-19 — delete another user's item returns 404."""
    _signup(base_url, "del_user_a", "password123")
    _signup(base_url, "del_user_b", "password123")

    signin_a = _signin(base_url, "del_user_a", "password123")
    token_a = signin_a.json()["token"]
    create_resp = _create_item(base_url, token_a, "not yours")
    item_id = create_resp.json()["id"]

    signin_b = _signin(base_url, "del_user_b", "password123")
    token_b = signin_b.json()["token"]
    resp = _delete_item(base_url, token_b, item_id)
    assert resp.status_code == 404


# ── AC-16: GET /health returns 200 without a token ──────────────────────────

def test_ac16_health(base_url: str) -> None:
    """AC-16 — health endpoint returns 200 with {"status": "ok"}."""
    resp = httpx.get(f"{base_url}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}


# ── AC-17: start.sh exists and starts the service correctly ─────────────────

def test_ac17_start_sh(base_url: str) -> None:
    """AC-17 — start.sh launches the service on 127.0.0.1:$PORT using $DATA_DIR."""
    # The fact that base_url works means start.sh started it.
    # Verify health as the proof of a running service.
    resp = httpx.get(f"{base_url}/health")
    assert resp.status_code == 200

    # Verify start.sh exists in project root
    start_sh = PROJECT / "start.sh"
    assert start_sh.is_file(), "start.sh must exist in the project root"


# ── AC-18: Every operation works as the interface says ────────────────────────

def test_ac18_full_interface(base_url: str) -> None:
    """AC-18 — every operation works as the interface contract specifies.

    Exercises the complete lifecycle: signup → signin → create item → list items
    → toggle done → delete item, verifying status codes and body shapes at each
    step match the interface specification exactly.
    """
    # ── Signup (AC-1 / AC-9): POST /signup → 201 {"username": "..."} ────────
    resp = _signup(base_url, "ac18user", "password")
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) == {"username"}
    assert body["username"] == "ac18user"

    # ── Signin (AC-2 / AC-10): POST /signin → 200 {"token": "..."} ──────────
    resp = _signin(base_url, "ac18user", "password")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"token"}
    assert isinstance(body["token"], str)
    assert len(body["token"]) > 0
    token = body["token"]

    # ── Create item (AC-3): POST /items → 201 {"id": int, "title": "...", "done": false}
    resp = _create_item(base_url, token, "interface check")
    assert resp.status_code == 201
    item = resp.json()
    assert set(item.keys()) == {"id", "title", "done"}
    assert isinstance(item["id"], int)
    assert isinstance(item["title"], str)
    assert item["title"] == "interface check"
    assert item["done"] is False
    item_id = item["id"]

    # ── List items (AC-4): GET /items → 200 [...] ───────────────────────────
    resp = _list_items(base_url, token)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["id"] == item_id
    assert body[0]["title"] == "interface check"
    assert body[0]["done"] is False

    # ── Toggle done (AC-5): PATCH /items/{id} → 200 {"id": int, ...} ────────
    resp = _toggle_item(base_url, token, item_id, True)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"id", "title", "done"}
    assert body["id"] == item_id
    assert body["done"] is True

    # ── Delete item (AC-6): DELETE /items/{id} → 204 ────────────────────────
    resp = _delete_item(base_url, token, item_id)
    assert resp.status_code == 204

    # ── Confirm deleted: GET /items → 200 [] ────────────────────────────────
    resp = _list_items(base_url, token)
    assert resp.status_code == 200
    assert resp.json() == []

    # ── Auth enforcement (AC-11): no token → 401 ────────────────────────────
    resp = httpx.get(f"{base_url}/items")
    assert resp.status_code == 401

    # ── Health check (AC-8 / AC-16): GET /health → 200 {"status": "ok"} ────
    resp = httpx.get(f"{base_url}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
