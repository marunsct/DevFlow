"""Hidden acceptance tests for the tasks-api benchmark, written from brief.md's Interface."""

import uuid

from conftest import sign_up_and_in


def _item(api, who, title=None):
    made = api.post("/items", json={"title": title or f"item {uuid.uuid4().hex[:6]}"}, headers=who)
    assert made.status_code == 201, made.text
    return made.json()


def test_signs_up_and_refuses_a_taken_name(api):
    name = f"user{uuid.uuid4().hex[:8]}"
    first = api.post("/signup", json={"username": name, "password": "pw-one-123"})
    assert first.status_code == 201 and first.json()["username"] == name
    assert api.post("/signup", json={"username": name, "password": "other-pw-1"}).status_code == 409
    assert api.post("/signup", json={"username": "", "password": "x"}).status_code in (400, 422)


def test_signs_in_only_with_the_right_password(api):
    name = f"user{uuid.uuid4().hex[:8]}"
    api.post("/signup", json={"username": name, "password": "right-pass-1"})
    assert api.post("/signin", json={"username": name, "password": "wrong-pass"}).status_code == 401
    good = api.post("/signin", json={"username": name, "password": "right-pass-1"})
    assert good.status_code == 200 and isinstance(good.json()["token"], str) and good.json()["token"]


def test_items_need_a_token(api):
    assert api.get("/items").status_code == 401
    assert api.post("/items", json={"title": "x"}).status_code == 401
    assert api.get("/items", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    assert api.get("/health").status_code == 200


def test_creates_an_item_not_done(api):
    who = sign_up_and_in(api)
    item = _item(api, who, "Buy milk")
    assert isinstance(item["id"], int) and item["title"] == "Buy milk" and item["done"] is False


def test_lists_only_your_own_items(api):
    alice, bob = sign_up_and_in(api), sign_up_and_in(api)
    mine = _item(api, alice, "alice's")
    theirs = _item(api, bob, "bob's")
    listed = api.get("/items", headers=alice)
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()}
    assert mine["id"] in ids and theirs["id"] not in ids


def test_marks_an_item_done_and_not_done(api):
    who = sign_up_and_in(api)
    item = _item(api, who)
    done = api.patch(f"/items/{item['id']}", json={"done": True}, headers=who)
    assert done.status_code == 200 and done.json()["done"] is True
    undone = api.patch(f"/items/{item['id']}", json={"done": False}, headers=who)
    assert undone.status_code == 200 and undone.json()["done"] is False


def test_deletes_an_item(api):
    who = sign_up_and_in(api)
    item = _item(api, who)
    assert api.delete(f"/items/{item['id']}", headers=who).status_code == 204
    assert item["id"] not in {i["id"] for i in api.get("/items", headers=who).json()}
    assert api.delete(f"/items/{item['id']}", headers=who).status_code == 404


def test_another_person_cannot_change_or_delete_your_item(api):
    alice, bob = sign_up_and_in(api), sign_up_and_in(api)
    item = _item(api, alice)
    assert api.patch(f"/items/{item['id']}", json={"done": True}, headers=bob).status_code == 404
    assert api.delete(f"/items/{item['id']}", headers=bob).status_code == 404
    assert any(i["id"] == item["id"] and i["done"] is False for i in api.get("/items", headers=alice).json())


def test_refuses_an_empty_title_and_stores_nothing(api):
    who = sign_up_and_in(api)
    before = len(api.get("/items", headers=who).json())
    assert api.post("/items", json={"title": ""}, headers=who).status_code in (400, 422)
    assert api.post("/items", json={}, headers=who).status_code in (400, 422)
    assert len(api.get("/items", headers=who).json()) == before


def test_accounts_and_items_survive_a_restart(api, service):
    name = f"user{uuid.uuid4().hex[:8]}"
    who = sign_up_and_in(api, name, "keep-me-123")
    item = _item(api, who, "Still here")
    service.restart()
    signed = api.post("/signin", json={"username": name, "password": "keep-me-123"})
    assert signed.status_code == 200
    again = {"Authorization": f"Bearer {signed.json()['token']}"}
    assert any(i["id"] == item["id"] and i["title"] == "Still here" for i in api.get("/items", headers=again).json())
