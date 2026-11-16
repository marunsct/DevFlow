"""Quality tests for the tasks-api benchmark: the brief's requirements at their edges.

Scored apart from the hidden tests (`quality_passed` / `quality_total`), so the
headline hidden score stays comparable across runs. Each test holds the
product to something the brief already says that the hidden tests do not
reach, and the benchmark's reference passes every one: a product can pass every hidden test and still store a
password as given, answer 500 to a malformed request, or lose items written at
once.
"""

import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from conftest import sign_up_and_in


def _status_ok_or_refused(code):
    return code in (400, 404, 422)


def test_a_password_is_never_stored_as_given(api, service):
    """Technical constraint: passwords are never stored as given."""
    secret = f"plain-{uuid.uuid4().hex}"
    sign_up_and_in(api, password=secret)
    for path in Path(service.data_dir).rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes(), f"{path.name} holds the password as given"


def test_a_title_of_only_spaces_is_refused_and_nothing_is_stored(api):
    """A missing or empty title is refused, and nothing is stored."""
    who = sign_up_and_in(api)
    before = api.get("/items", headers=who).json()
    assert _status_ok_or_refused(api.post("/items", json={"title": "   "}, headers=who).status_code)
    assert api.get("/items", headers=who).json() == before


def test_a_missing_field_is_refused_not_a_server_error(api):
    who = sign_up_and_in(api)
    assert api.post("/signup", json={"password": "x-pass-1"}).status_code in (400, 422)
    assert api.post("/items", json={}, headers=who).status_code in (400, 422)
    assert api.post("/items", content=b"not json", headers={**who, "Content-Type": "application/json"}).status_code in (400, 422)


def test_marking_done_with_a_value_that_is_not_true_or_false_changes_nothing(api):
    """`done` is a boolean; anything else is invalid input, refused without storing anything."""
    who = sign_up_and_in(api)
    item = api.post("/items", json={"title": "keep me"}, headers=who).json()
    answer = api.patch(f"/items/{item['id']}", json={"done": "maybe"}, headers=who)
    assert answer.status_code in (400, 422)
    stored = [i for i in api.get("/items", headers=who).json() if i["id"] == item["id"]]
    assert stored and stored[0]["done"] is False


def test_an_id_that_is_not_one_of_yours_is_never_a_server_error(api):
    who = sign_up_and_in(api)
    assert api.patch("/items/999999", json={"done": True}, headers=who).status_code == 404
    assert api.delete("/items/999999", headers=who).status_code == 404
    assert api.delete("/items/not-a-number", headers=who).status_code in (404, 422)


def test_a_long_title_is_kept_whole_or_refused_never_a_server_error(api):
    who = sign_up_and_in(api)
    title = "t" * 5000
    made = api.post("/items", json={"title": title}, headers=who)
    assert made.status_code in (201, 400, 422)
    if made.status_code == 201:
        assert made.json()["title"] == title


def test_items_created_at_once_are_all_kept_with_their_own_ids(api, service):
    """Twenty items written side by side: none lost, none sharing an id."""
    who = sign_up_and_in(api)

    def create(n):
        with httpx.Client(base_url=service.url, timeout=20) as client:
            return client.post("/items", json={"title": f"parallel {n}"}, headers=who)

    with ThreadPoolExecutor(max_workers=10) as pool:
        answers = list(pool.map(create, range(20)))
    assert all(a.status_code == 201 for a in answers), [a.status_code for a in answers]
    ids = {a.json()["id"] for a in answers}
    listed = {i["id"] for i in api.get("/items", headers=who).json()}
    assert len(ids) == 20 and ids <= listed
