"""Quality tests for the shortlinks-api benchmark: the brief's interface at its edges (held out: LR.41)."""

from concurrent.futures import ThreadPoolExecutor

import httpx


def test_malformed_json_is_refused_not_a_server_error(api):
    answer = api.post("/links", content=b"{not json", headers={"Content-Type": "application/json"})
    assert answer.status_code in (400, 422)


def test_visits_made_at_once_are_all_counted(api, service):
    code = api.post("/links", json={"url": "https://example.com/busy"}).json()["code"]

    def follow(_):
        with httpx.Client(base_url=service.url, timeout=20) as client:
            return client.get(f"/r/{code}", follow_redirects=False).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(follow, range(16))) == {302}
    assert api.get(f"/links/{code}").json()["visits"] == 16


def test_links_made_at_once_all_get_their_own_codes(api, service):
    def make(n):
        with httpx.Client(base_url=service.url, timeout=20) as client:
            return client.post("/links", json={"url": f"https://example.com/{n}"}).json()["code"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(make, range(16)))
    assert len(set(codes)) == 16


def test_a_deleted_link_no_longer_redirects(api):
    code = api.post("/links", json={"url": "https://example.com/gone"}).json()["code"]
    api.delete(f"/links/{code}")
    assert api.get(f"/r/{code}", follow_redirects=False).status_code == 404
