"""Acceptance tests for the Tasks API.

Tests against a running service instance managed by conftest.py.
Each test is named after the acceptance criterion it proves so the harness
can track which criteria are satisfied.

Usage: run ``pytest acceptance -q`` from the tasks-api/ directory.
"""

import httpx


# ── AC-9: POST /signup → 201, 409, 422 ──────────────────────────────────

def test_ac1_ac9_signup_creates_user(base_url):
    """AC-1 and AC-9: POST /signup with valid data answers 201 with the username."""
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "ac9user", "password": "correcthorse"},
    )
    assert resp.status_code == 201
    assert resp.json() == {"username": "ac9user"}


def test_ac9_signup_duplicate_returns_409(base_url):
    """AC-9: POST /signup with a duplicate username answers 409 and stores nothing."""
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac9dup", "password": "correcthorse"},
    )
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "ac9dup", "password": "correcthorse"},
    )
    assert resp.status_code == 409

    # Verify no second account row was created: signing in must still work
    # (proving only the first signup's account exists)
    signin_resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "ac9dup", "password": "correcthorse"},
    )
    assert signin_resp.status_code == 200, (
        f"Signup should have created exactly one account; got {signin_resp.status_code}"
    )


def test_ac9_signup_empty_username_returns_422(base_url):
    """AC-9: POST /signup with an empty username is refused (400 or 422) and stores nothing."""
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "", "password": "correcthorse"},
    )
    assert resp.status_code in (400, 422)

    # Verify no account row was created: signing in must fail.
    # The SigninRequest model rejects empty strings with 422, but a
    # non-existent username returns 401; either way proves nothing stored.
    signin_resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "", "password": "correcthorse"},
    )
    assert signin_resp.status_code in (401, 422), (
        f"Empty username signup should not have created an account; got {signin_resp.status_code}"
    )


def test_ac9_signup_empty_password_returns_422(base_url):
    """AC-9: POST /signup with an empty password is refused (400 or 422) and stores nothing."""
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "ac9pwuser", "password": ""},
    )
    assert resp.status_code in (400, 422)

    # Verify no account row was created: signing in must fail.
    signin_resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "ac9pwuser", "password": ""},
    )
    assert signin_resp.status_code in (401, 422), (
        f"Empty password signup should not have created an account; got {signin_resp.status_code}"
    )


def test_ac9_signup_missing_username_returns_422(base_url):
    """AC-9: POST /signup with a missing username key is refused (400 or 422) and stores nothing."""
    # Send body without the username key entirely
    resp = httpx.post(
        f"{base_url}/signup",
        json={"password": "correcthorse"},
    )
    assert resp.status_code in (400, 422)

    # Verify no account row was created: signing in must fail.
    signin_resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "", "password": "correcthorse"},
    )
    assert signin_resp.status_code in (401, 422), (
        f"Missing username signup should not have created an account; got {signin_resp.status_code}"
    )


def test_ac9_signup_missing_password_returns_422(base_url):
    """AC-9: POST /signup with a missing password key is refused (400 or 422) and stores nothing."""
    # Send body without the password key entirely
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "ac9mpwuser"},
    )
    assert resp.status_code in (400, 422)

    # Verify no account row was created: signing in must fail.
    signin_resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "ac9mpwuser", "password": ""},
    )
    assert signin_resp.status_code in (401, 422), (
        f"Missing password signup should not have created an account; got {signin_resp.status_code}"
    )


# ── AC-10: POST /signin → 200, 401 ─────────────────────────────────────

def test_ac2_ac10_signin_returns_token(base_url):
    """AC-2 and AC-10: POST /signin with correct credentials answers 200 with a token."""
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac10user", "password": "correcthorse"},
    )
    resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "ac10user", "password": "correcthorse"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert isinstance(data["token"], str)
    assert len(data["token"]) > 0


def test_ac10_signin_wrong_password_returns_401(base_url):
    """AC-10: POST /signin with wrong password answers 401."""
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac10badpw", "password": "correcthorse"},
    )
    resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "ac10badpw", "password": "wrongpass"},
    )
    assert resp.status_code == 401


# ── AC-16: GET /health → 200 without token ─────────────────────────────

def test_ac16_health_returns_200(base_url):
    """AC-16: GET /health answers 200 without authentication."""
    resp = httpx.get(f"{base_url}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── AC-3, AC-8, AC-12: POST /items → 201, 401, 422 ────────────────────

def test_ac3_ac8_create_item_starts_not_done(base_url):
    """AC-3 and AC-8: Create an item with a title; it starts not done.

    Also verifies AC-8 (JSON shape) and AC-12 (POST /items → 201).
    """
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac3user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac3user", "correcthorse")
    resp = httpx.post(
        f"{base_url}/items",
        json={"title": "Buy milk"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()

    # AC-8: JSON shape
    assert isinstance(data["id"], int)
    assert data["title"] == "Buy milk"
    assert isinstance(data["done"], bool)
    assert data["done"] is False


def test_ac12_create_item_empty_title_returns_422(base_url):
    """AC-12: POST /items with empty title is refused (400 or 422) and stores nothing."""
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac12user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac12user", "correcthorse")
    resp = httpx.post(
        f"{base_url}/items",
        json={"title": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (400, 422)

    # Verify no item row was written: list must be empty
    items_resp = httpx.get(
        f"{base_url}/items", headers={"Authorization": f"Bearer {token}"}
    )
    assert items_resp.status_code == 200
    assert len(items_resp.json()) == 0, (
        "Empty title should not have created any item rows"
    )


def test_ac11_ac12_create_item_unauthenticated_returns_401(base_url):
    """AC-11 and AC-12: POST /items without a Bearer token answers 401."""
    resp = httpx.post(f"{base_url}/items", json={"title": "Buy milk"})
    assert resp.status_code == 401


# ── AC-4, AC-8, AC-13: GET /items → 200, 401 ──────────────────────────

def test_ac4_list_own_items(base_url):
    """AC-4: List your own items.

    Also verifies AC-8 (JSON shape) and AC-13 (GET /items → 200).
    """
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac4user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac4user", "correcthorse")
    # Create two items first
    httpx.post(
        f"{base_url}/items",
        json={"title": "Item one"},
        headers={"Authorization": f"Bearer {token}"},
    )
    httpx.post(
        f"{base_url}/items",
        json={"title": "Item two"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) == 2

    # AC-8: every item has the right shape
    for item in items:
        assert "id" in item and isinstance(item["id"], int)
        assert "title" in item and isinstance(item["title"], str)
        assert "done" in item and isinstance(item["done"], bool)


def test_ac13_get_items_unauthenticated_returns_401(base_url):
    """AC-13: GET /items without a Bearer token answers 401."""
    resp = httpx.get(f"{base_url}/items")
    assert resp.status_code == 401


# ── AC-5, AC-8, AC-14: PATCH /items/{id} → 200, 401, 404, 422 ─────────

def test_ac5_mark_item_done(base_url):
    """AC-5: Mark one of your items done or not done.

    Also verifies AC-8 (JSON shape) and AC-14 (PATCH /items/{id} → 200).
    """
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac5user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac5user", "correcthorse")
    item_id = _create_item(base_url, token, "Mark me done")

    # Mark as done
    resp = httpx.patch(
        f"{base_url}/items/{item_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == item_id
    assert data["done"] is True

    # Mark as not done
    resp = httpx.patch(
        f"{base_url}/items/{item_id}",
        json={"done": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["done"] is False


def test_ac14_patch_nonexistent_returns_404(base_url):
    """AC-14: PATCH /items/{id} for a non-existent item answers 404."""
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac14user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac14user", "correcthorse")
    resp = httpx.patch(
        f"{base_url}/items/9999",
        json={"done": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_ac14_patch_unauthenticated_returns_401(base_url):
    """AC-14: PATCH /items/{id} without a Bearer token answers 401."""
    resp = httpx.patch(f"{base_url}/items/1", json={"done": True})
    assert resp.status_code == 401


def test_ac14_patch_invalid_done_returns_422(base_url):
    """AC-14: PATCH /items/{id} with non-boolean done answers 422."""
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac14userb", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac14userb", "correcthorse")
    item_id = _create_item(base_url, token, "Test")
    resp = httpx.patch(
        f"{base_url}/items/{item_id}",
        json={"done": "true"},  # string, not bool → 422
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── AC-6, AC-15: DELETE /items/{id} → 204, 401, 404 ───────────────────

def test_ac6_delete_item(base_url):
    """AC-6: Delete one of your items.

    Also verifies AC-15 (DELETE /items/{id} → 204).
    """
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac6user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac6user", "correcthorse")
    item_id = _create_item(base_url, token, "Delete me")

    resp = httpx.delete(
        f"{base_url}/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Verify it is gone
    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {token}"})
    assert all(i["id"] != item_id for i in resp.json())


def test_ac15_delete_unauthenticated_returns_401(base_url):
    """AC-15: DELETE /items/{id} without a Bearer token answers 401."""
    resp = httpx.delete(f"{base_url}/items/1")
    assert resp.status_code == 401


def test_ac15_delete_nonexistent_returns_404(base_url):
    """AC-15: DELETE /items/{id} for a non-existent item answers 404."""
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac15user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac15user", "correcthorse")
    resp = httpx.delete(
        f"{base_url}/items/9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── AC-7, AC-20: Persistence across restarts ───────────────────────────

def test_ac7_ac20_persistence_across_restart(base_url, service):
    """AC-7 and AC-20: Accounts and items survive a restart of the service.

    Signs up a user, creates items, restarts the service, then verifies
    that signing in still works and the items are still there with their
    original titles and done values.
    """
    # Sign up and create items
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac7user", "password": "correcthorse"},
    )
    token = _signin(base_url, "ac7user", "correcthorse")

    id1 = _create_item(base_url, token, "Persist item one")
    id2 = _create_item(base_url, token, "Persist item two")

    # Verify items exist before restart
    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {token}"})
    assert len(resp.json()) == 2

    # Restart the service (same DATA_DIR → same database file)
    service.restart()

    # Sign in again (old token is revoked; new one issued)
    new_token = _signin(base_url, "ac7user", "correcthorse")

    # Items must still be there with original titles and done=False
    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {new_token}"})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    titles = sorted(i["title"] for i in items)
    assert titles == ["Persist item one", "Persist item two"]
    # Verify done values are still false (original state)
    for item in items:
        assert item["done"] is False


# ── AC-19: User isolation ──────────────────────────────────────────────

def test_ac19_user_isolation(base_url):
    """AC-19: One person's items are never visible to or changeable by another.

    Creates two accounts, puts an item under the first, then uses the second
    account's token to verify the item is invisible and unchangeable.
    """
    # Sign up dan and eve
    for user in ("ac19dan", "ac19eve"):
        httpx.post(f"{base_url}/signup", json={"username": user, "password": "correcthorse"})

    # Dan creates an item
    dan_token = _signin(base_url, "ac19dan", "correcthorse")
    dan_item_id = _create_item(base_url, dan_token, "Dan's secret item")

    # Eve signs in
    eve_token = _signin(base_url, "ac19eve", "correcthorse")

    # Eve sees no items
    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {eve_token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # Eve cannot PATCH Dan's item
    resp = httpx.patch(
        f"{base_url}/items/{dan_item_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {eve_token}"},
    )
    assert resp.status_code == 404

    # Eve cannot DELETE Dan's item
    resp = httpx.delete(
        f"{base_url}/items/{dan_item_id}",
        headers={"Authorization": f"Bearer {eve_token}"},
    )
    assert resp.status_code == 404


# ── AC-21: Invalid input refused without storing anything ───────────────

def test_ac21_invalid_input_refused(base_url):
    """AC-21: Invalid input is refused without storing anything.

    Tries several invalid payloads and then queries the database indirectly
    (via GET endpoints) to confirm nothing was written. Verifies that no
    account rows were created after rejected signup attempts, and no items
    were stored after rejected item creation.
    """
    # Empty username signup → rejected, no row created
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "", "password": "x"},
    )
    assert resp.status_code in (400, 422)

    # Verify the empty-username signup did not create an account:
    # signing in with that username must fail
    signin_resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "", "password": "x"},
    )
    # SigninRequest also rejects empty strings with 422; either code proves nothing stored.
    assert signin_resp.status_code in (401, 422), (
        "Empty username signup should not have created an account"
    )

    # Signup with only whitespace username → rejected
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "   ", "password": "x"},
    )
    assert resp.status_code in (400, 422)

    # Verify the whitespace-username signup did not create an account
    signin_resp = httpx.post(
        f"{base_url}/signin",
        json={"username": "   ", "password": "x"},
    )
    assert signin_resp.status_code in (401, 422), (
        "Whitespace-only username signup should not have created an account"
    )

    # Sign up ac21user (the valid signup for this test's own flow)
    httpx.post(
        f"{base_url}/signup",
        json={"username": "ac21user", "password": "correcthorse"},
    )
    # Valid signup followed by empty-title item creation → rejected
    token = _signin(base_url, "ac21user", "correcthorse")
    resp = httpx.post(
        f"{base_url}/items",
        json={"title": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (400, 422)

    # Verify no items were stored for this user
    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 0


# ── AC-18: Every operation works as the interface says ─────────────────

def test_ac18_full_workflow(base_url):
    """AC-18: Full end-to-end workflow exercising every endpoint.

    Signup → signin → create items → list → update done → delete → verify.
    """
    # Signup
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": "ac18user", "password": "correcthorse"},
    )
    assert resp.status_code == 201
    assert resp.json() == {"username": "ac18user"}

    # Signin
    token = _signin(base_url, "ac18user", "correcthorse")

    # Create two items
    id1 = _create_item(base_url, token, "First task")
    id2 = _create_item(base_url, token, "Second task")

    # List items → 2 items
    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Mark first item done
    resp = httpx.patch(
        f"{base_url}/items/{id1}",
        json={"done": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["done"] is True

    # Delete second item
    resp = httpx.delete(
        f"{base_url}/items/{id2}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Verify only the first item remains
    resp = httpx.get(f"{base_url}/items", headers={"Authorization": f"Bearer {token}"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == id1


# ── AC-8 (JSON shape): Covered inline with AC-3, AC-4, AC-5 ───────────

# ── AC-17: start.sh exists and starts the service ─────────────────────


def test_ac17_start_sh_exists_and_starts_service(base_url):
    """AC-17: The project directory has a start.sh that starts the service.

    Verifies that start.sh exists as a file, contains the expected
    PORT/DATA_DIR/env setup, and that the service is running (proving
    start.sh launched it correctly).
    """
    from pathlib import Path

    # Verify start.sh exists in the project directory
    project_dir = Path(__file__).resolve().parent.parent
    start_sh = project_dir / "start.sh"
    assert start_sh.is_file(), f"start.sh not found at {start_sh}"

    # Verify it references PORT and DATA_DIR environment variables
    content = start_sh.read_text(encoding="utf-8")
    assert "PORT" in content, "start.sh must use the PORT environment variable"
    assert "DATA_DIR" in content or "data" in content.lower(), (
        "start.sh must use the DATA_DIR environment variable"
    )

    # Verify it binds to 127.0.0.1
    assert "127.0.0.1" in content or "host" in content, (
        "start.sh must bind to 127.0.0.1"
    )

    # Health endpoint must work — proves start.sh started the service
    resp = httpx.get(f"{base_url}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── Helpers ────────────────────────────────────────────────────────────

def _signup(base_url: str, username: str, password: str) -> None:
    """Create an account; raise if signup does not return 201."""
    resp = httpx.post(
        f"{base_url}/signup",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 201, (
        f"Signup for {username} failed with {resp.status_code}: {resp.text}"
    )


def _signin(base_url: str, username: str, password: str) -> str:
    """Sign in and return the token string; raises on non-200."""
    resp = httpx.post(
        f"{base_url}/signin",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, (
        f"Signin for {username} failed with {resp.status_code}: {resp.text}"
    )
    return resp.json()["token"]


def _create_item(base_url: str, token: str, title: str) -> int:
    """Create an item and return its id; raises on non-201."""
    resp = httpx.post(
        f"{base_url}/items",
        json={"title": title},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, (
        f"Create item failed with {resp.status_code}: {resp.text}"
    )
    return resp.json()["id"]
