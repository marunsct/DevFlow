"""Quality tests for the notes-api benchmarks: the brief's requirements at their edges (LR.25).

Scored apart from the hidden tests (`quality_passed` / `quality_total`), so the headline hidden score stays
comparable across runs. Each test holds the product to something the brief already says that the hidden tests do not
reach - invalid input refused without storing anything, a server error never answered for a client's mistake, notes
written at once all kept - and every benchmark reference passes every one.
"""

from concurrent.futures import ThreadPoolExecutor

import httpx


def _refused(code):
    return code in (400, 422)


def _count(api):
    return len(api.get("/notes").json())


def test_malformed_json_is_refused_not_a_server_error(api):
    before = _count(api)
    answer = api.post("/notes", content=b"{not json", headers={"Content-Type": "application/json"})
    assert _refused(answer.status_code)
    assert _count(api) == before


def test_a_null_or_blank_title_is_refused_and_nothing_is_stored(api):
    """A title that is missing or empty is refused, and nothing is stored: null and only spaces are both."""
    before = _count(api)
    assert _refused(api.post("/notes", json={"title": None, "body": "x"}).status_code)
    assert _refused(api.post("/notes", json={"title": "   ", "body": "x"}).status_code)
    assert _count(api) == before


def test_an_update_without_a_title_is_refused_and_the_note_is_unchanged(api):
    note = api.post("/notes", json={"title": "keep", "body": "as is"}).json()
    assert _refused(api.put(f"/notes/{note['id']}", json={"body": "new"}).status_code)
    assert api.get(f"/notes/{note['id']}").json() == note


def test_an_update_of_a_note_that_is_not_there_creates_nothing(api):
    before = _count(api)
    assert api.put("/notes/987654321", json={"title": "t", "body": "b"}).status_code == 404
    assert _count(api) == before


def test_a_note_deleted_twice_is_404_the_second_time(api):
    note = api.post("/notes", json={"title": "gone", "body": ""}).json()
    assert api.delete(f"/notes/{note['id']}").status_code == 204
    assert api.delete(f"/notes/{note['id']}").status_code == 404
    assert api.get(f"/notes/{note['id']}").status_code == 404


def test_an_id_that_is_not_a_number_is_never_a_server_error(api):
    for answer in (api.get("/notes/abc"), api.put("/notes/abc", json={"title": "t", "body": "b"}),
                   api.delete("/notes/abc")):
        assert answer.status_code in (400, 404, 422)


def test_notes_written_at_once_are_all_kept_with_their_own_ids(api, service):
    before = _count(api)

    def write(n):
        with httpx.Client(base_url=service.url, timeout=20) as client:
            return client.post("/notes", json={"title": f"at once {n}", "body": str(n)})

    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(write, range(16)))
    assert all(answer.status_code == 201 for answer in answers)
    ids = [answer.json()["id"] for answer in answers]
    assert len(set(ids)) == 16
    assert _count(api) == before + 16


def test_a_long_body_is_kept_whole(api):
    body = "line of text\n" * 2000
    note = api.post("/notes", json={"title": "long", "body": body}).json()
    assert api.get(f"/notes/{note['id']}").json()["body"] == body
