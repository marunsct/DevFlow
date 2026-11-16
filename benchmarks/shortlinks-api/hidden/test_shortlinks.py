"""Hidden acceptance tests for the shortlinks-api benchmark, written from brief.md's Interface (held out: LR.41)."""

import re
import uuid


def _make(api, url="https://example.com/a/long/path", code=None):
    body = {"url": url} if code is None else {"url": url, "code": code}
    return api.post("/links", json=body)


def test_shortens_an_address_with_a_six_character_code(api):
    answer = _make(api)
    assert answer.status_code == 201
    link = answer.json()
    assert re.fullmatch(r"[A-Za-z0-9]{6}", link["code"]) and link["url"] == "https://example.com/a/long/path"
    assert link["visits"] == 0


def test_a_chosen_code_is_used_and_cannot_be_taken_twice(api):
    code = f"c{uuid.uuid4().hex[:7]}"
    assert _make(api, code=code).json()["code"] == code
    assert _make(api, url="https://other.example", code=code).status_code == 409


def test_following_a_code_redirects_and_counts_the_visit(api):
    link = _make(api, url="https://example.org/target").json()
    for _ in range(2):
        answer = api.get(f"/r/{link['code']}", follow_redirects=False)
        assert answer.status_code == 302 and answer.headers["location"] == "https://example.org/target"
    assert api.get(f"/links/{link['code']}").json()["visits"] == 2


def test_an_unknown_code_is_404_everywhere(api):
    for answer in (api.get("/r/zzzzzz9", follow_redirects=False), api.get("/links/zzzzzz9"), api.delete("/links/zzzzzz9")):
        assert answer.status_code == 404


def test_lists_every_link(api):
    made = {_make(api, url=f"https://example.com/{n}").json()["code"] for n in range(3)}
    listed = {link["code"] for link in api.get("/links").json()}
    assert made <= listed


def test_refuses_an_address_that_is_not_web_and_stores_nothing(api):
    before = len(api.get("/links").json())
    for url in ("ftp://example.com/f", "example.com", ""):
        assert _make(api, url=url).status_code in (400, 422)
    assert len(api.get("/links").json()) == before


def test_deletes_a_link(api):
    link = _make(api).json()
    assert api.delete(f"/links/{link['code']}").status_code == 204
    assert api.get(f"/links/{link['code']}").status_code == 404


def test_links_and_visits_survive_a_restart(service, api):
    link = _make(api, url="https://example.net/keep").json()
    api.get(f"/r/{link['code']}", follow_redirects=False)
    service.restart()
    import httpx

    with httpx.Client(base_url=service.url, timeout=10) as fresh:
        kept = fresh.get(f"/links/{link['code']}").json()
    assert kept["url"] == "https://example.net/keep" and kept["visits"] == 1
