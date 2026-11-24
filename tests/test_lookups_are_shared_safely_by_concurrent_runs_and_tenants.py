"""Lookups are shared safely by concurrent runs, machines and tenants (plan KS.5, the first slice of HK.12, LF.1304).

Measured before it (`reports/research/2026-11-25-open-source-web-search.md`, gap 8): the answer cache was one file per
query on one machine's disk, so another worker or machine asked again; a source's daily count was read, changed and
written back with no lock, so concurrent runs could pass its cap; two runs asking the same question at once both went
outward; a source held after a refusal was held on one host only; robots.txt was kept per transport. Each fact holds
on the deployment's shared store and, where it can, on this machine's files when the store does not answer.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from app.tools import lookups, page_reader, source_breaker

ERROR = "TypeError: Cannot read properties of undefined (reading 'map') in the list view after an empty response"


@pytest.fixture(params=["shared store", "store unreachable"])
def store(request, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "machine-a"))
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    for variable in ("LOOKUP_ORDER", "LOOKUP_DAILY_CAPS", "LOOKUPS_FROZEN", "STACKEXCHANGE_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(variable, raising=False)
    if request.param == "store unreachable":
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:9/0")
    return request.param


@pytest.fixture
def shared(store):
    if store != "shared store":
        pytest.skip("a fact of the shared store")
    return store


def _another_machine(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "machine-b"))


class Upstream:
    """Stack Exchange as the network shows it: each request recorded; its answer the `advice` of the moment."""

    def __init__(self, advice: str = "Return an empty list, not undefined.", slow: float = 0.0) -> None:
        self.sent: list[str] = []
        self.advice, self.slow = advice, slow
        self._lock = threading.Lock()

    def searches(self) -> int:
        return sum("search/advanced" in url for url in self.sent)

    def __call__(self, url, headers, body=None):
        with self._lock:
            self.sent.append(url)
        if "search/advanced" in url:
            time.sleep(self.slow)
            return 200, json.dumps({"items": [
                {"title": f"q{n}", "link": f"https://stackoverflow.com/q/{n}", "accepted_answer_id": n,
                 "last_activity_date": 1_700_000_000} for n in (1, 2, 3)]})
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": n, "body": f"<p>{self.advice}</p>"} for n in (1, 2, 3)]})
        return 200, json.dumps({"items": []})


def _advice(answer: dict) -> str:
    return answer["found"][0]["excerpt"]


def test_two_runs_asking_the_same_question_at_once_make_one_outward_request(store):
    upstream = Upstream(slow=0.3)
    start = threading.Barrier(2)
    answers: list[dict] = []

    def run():
        start.wait()
        answers.append(lookups.look_up(ERROR, "react 19", fetch=upstream))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert upstream.searches() == 1
    assert [_advice(a) for a in answers] == ["Return an empty list, not undefined."] * 2


def test_a_source_s_daily_cap_is_never_passed_by_requests_sent_at_once(store, monkeypatch):
    monkeypatch.setenv("LOOKUP_DAILY_CAPS", "stack exchange=5")
    upstream = Upstream()
    start = threading.Barrier(30)

    def run():
        start.wait()
        try:
            lookups.guarded("stack exchange", upstream)("https://api.stackexchange.com/2.3/info", {})
        except lookups.Capped:
            pass

    threads = [threading.Thread(target=run) for _ in range(30)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(upstream.sent) == 5
    assert lookups.requests_today()["stack exchange"] == 5


def test_a_tenant_whose_daily_budget_is_spent_is_refused_while_another_tenant_asks(store, monkeypatch):
    from app.tools import lookup_store

    monkeypatch.setenv("LOOKUP_TENANT_DAILY_CAP", "3")
    for _ in range(3):
        assert lookup_store.reserve("github", 100, who="tenant-a") == ""

    refused = lookup_store.reserve("github", 100, who="tenant-a")
    other = lookup_store.reserve("github", 100, who="tenant-b")

    assert "budget of 3" in refused and other == ""


def test_an_answer_one_machine_found_is_not_asked_for_again_by_another(shared, monkeypatch, tmp_path):
    lookups.look_up(ERROR, "react 19", fetch=Upstream())
    _another_machine(monkeypatch, tmp_path)
    upstream = Upstream()

    answer = lookups.look_up(ERROR, "react 19", fetch=upstream)

    assert upstream.sent == []
    assert answer["cached"] and _advice(answer) == "Return an empty list, not undefined."


def test_a_source_that_refused_one_machine_is_held_on_another(shared, monkeypatch, tmp_path):
    def refusing(url, headers, body=None):
        return 429, "", {"retry-after": "600"}

    with pytest.raises(source_breaker.Refused):
        lookups.guarded("github issues", refusing)("https://api.github.com/search/issues?q=x", {})
    _another_machine(monkeypatch, tmp_path)

    assert source_breaker.held_until("github issues") > time.time() + 500


def _tenant_workspace(root: Path, tenant: str, project: str) -> Path:
    workspace = root / tenant / f"workspace-run-{tenant}"
    (workspace / ".harness").mkdir(parents=True)
    (workspace / ".harness" / "stack-pack.json").write_text(json.dumps({"project": project, "title": project}),
                                                            encoding="utf-8")
    return workspace


@pytest.fixture
def tenants(store, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    return (_tenant_workspace(tmp_path / "workspaces", "acme", "Quillmark"),
            _tenant_workspace(tmp_path / "workspaces", "globex", "Harborview"))


class Asked:
    """A lookup's outward work: how often it was done."""

    def __init__(self, advice: str) -> None:
        self.times, self.advice = 0, advice

    def __call__(self) -> dict:
        self.times += 1
        return {"found": [{"excerpt": self.advice}]}


def test_a_query_holding_a_tenant_s_own_words_is_never_served_to_another_tenant(tenants):
    from app.tools import lookup_store

    acme, globex = tenants
    query = "Quillmark exited: address already in use"
    lookup_store.remembered(lookup_store.LOOKUP, query, Asked("acme's answer"), days=lambda _: 7, repo_root=acme)
    for_globex, again_for_acme = Asked("globex's answer"), Asked("acme again")

    answer, kept = lookup_store.remembered(lookup_store.LOOKUP, query, for_globex, days=lambda _: 7, repo_root=globex)
    lookup_store.remembered(lookup_store.LOOKUP, query, again_for_acme, days=lambda _: 7, repo_root=acme)

    assert (for_globex.times, kept, answer["found"][0]["excerpt"]) == (1, False, "globex's answer")
    assert again_for_acme.times == 0, "the tenant's own query is still kept for that tenant"


def test_a_public_query_one_tenant_asked_is_answered_for_another_from_the_store(tenants):
    from app.tools import lookup_store

    acme, globex = tenants
    query = "EADDRINUSE address already in use node 22"
    lookup_store.remembered(lookup_store.LOOKUP, query, Asked("free the port"), days=lambda _: 7, repo_root=acme)
    for_globex = Asked("asked again")

    answer, kept = lookup_store.remembered(lookup_store.LOOKUP, query, for_globex, days=lambda _: 7, repo_root=globex)

    assert (for_globex.times, kept, answer["found"][0]["excerpt"]) == (0, True, "free the port")


def test_both_arms_of_a_measure_pair_read_the_answer_the_first_arm_read(store, monkeypatch):
    monkeypatch.setenv("LOOKUPS_FROZEN", "pair-2026-11-25")
    first_arm = lookups.look_up(ERROR, "react 19", fetch=Upstream("Return an empty list, not undefined."))
    eight_days_later = time.time() + 8 * 86_400
    monkeypatch.setattr(time, "time", lambda: eight_days_later)
    monkeypatch.delenv("LOOKUPS_FROZEN")
    lookups.look_up(ERROR, "react 19", fetch=Upstream("Upgrade to the next major."))  # the live store moved on
    monkeypatch.setenv("LOOKUPS_FROZEN", "pair-2026-11-25")
    upstream = Upstream("Upgrade to the next major.")

    second_arm = lookups.look_up(ERROR, "react 19", fetch=upstream)

    assert upstream.sent == []
    assert _advice(second_arm) == _advice(first_arm) == "Return an empty list, not undefined."


def test_a_site_s_robots_txt_one_process_read_is_not_fetched_again_by_another(shared, monkeypatch):
    def a_process(sent: list[str]):
        def fetch(url, address):
            sent.append(url)
            if url.endswith("/robots.txt"):
                return 200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /private/\n"
            return 200, {"content-type": "text/plain"}, b"The page's own words."
        return fetch

    first, second = [], []
    monkeypatch.setattr(page_reader, "_fetch", a_process(first))
    page_reader.read("https://docs.example.org/guide/one", resolve=lambda host: ["140.82.112.3"])
    monkeypatch.setattr(page_reader, "_fetch", a_process(second))

    answer = page_reader.read("https://docs.example.org/guide/two", resolve=lambda host: ["140.82.112.3"])

    assert first.count("https://docs.example.org/robots.txt") == 1
    assert second == ["https://docs.example.org/guide/two"] and answer["text"] == "The page's own words."
