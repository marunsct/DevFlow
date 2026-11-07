"""Hidden acceptance tests for the notes-api benchmark, written from brief.md's Interface."""

import uuid


def _new(api, title=None, body="text"):
    title = title or f"note {uuid.uuid4().hex[:8]}"
    response = api.post("/notes", json={"title": title, "body": body})
    assert response.status_code == 201, response.text
    return response.json()


def test_creates_a_note(api):
    note = _new(api, "Groceries", "milk, eggs")
    assert isinstance(note["id"], int)
    assert note["title"] == "Groceries" and note["body"] == "milk, eggs"


def test_lists_every_note(api):
    first, second = _new(api), _new(api)
    listed = api.get("/notes")
    assert listed.status_code == 200
    ids = {note["id"] for note in listed.json()}
    assert {first["id"], second["id"]} <= ids


def test_fetches_one_note(api):
    note = _new(api, "Fetch me")
    fetched = api.get(f"/notes/{note['id']}")
    assert fetched.status_code == 200 and fetched.json()["title"] == "Fetch me"


def test_a_missing_note_is_404(api):
    assert api.get("/notes/999999").status_code == 404
    assert api.put("/notes/999999", json={"title": "x", "body": "y"}).status_code == 404
    assert api.delete("/notes/999999").status_code == 404


def test_updates_a_note(api):
    note = _new(api, "Before", "old")
    updated = api.put(f"/notes/{note['id']}", json={"title": "After", "body": "new"})
    assert updated.status_code == 200 and updated.json()["title"] == "After"
    assert api.get(f"/notes/{note['id']}").json()["body"] == "new"


def test_deletes_a_note(api):
    note = _new(api)
    assert api.delete(f"/notes/{note['id']}").status_code == 204
    assert api.get(f"/notes/{note['id']}").status_code == 404
    assert note["id"] not in {n["id"] for n in api.get("/notes").json()}


def test_refuses_a_note_without_a_title(api):
    before = len(api.get("/notes").json())
    for payload in ({"body": "no title"}, {"title": "", "body": "empty title"}):
        assert api.post("/notes", json=payload).status_code in (400, 422)
    assert len(api.get("/notes").json()) == before


def test_refuses_an_update_that_empties_the_title(api):
    note = _new(api, "Keep this title")
    assert api.put(f"/notes/{note['id']}", json={"title": "", "body": "b"}).status_code in (400, 422)
    assert api.get(f"/notes/{note['id']}").json()["title"] == "Keep this title"


def test_notes_survive_a_restart(service, api):
    note = _new(api, "Durable", "still here")
    service.restart()
    import httpx

    with httpx.Client(base_url=service.url, timeout=10) as fresh:
        fetched = fresh.get(f"/notes/{note['id']}")
    assert fetched.status_code == 200 and fetched.json()["body"] == "still here"
