"""The lookup service serves many runs and tenants (plan HK.12, the rest after KS.5; LF.1308).

Measured in the code before it: each source's only limit was a daily cap, so a burst of runs passed GitHub's ten
searches a minute and was refused for every run; the registries' and the documentation's answers were kept per
process, so every worker asked each registry again; a read page was read again by every run; the stuck lookup's
once-per-run record was a module dictionary, lost on a restart; a run whose Internet lookups choice was "off" still
read and wrote the shared answers; and a paid search's results were kept like any other, though its terms may forbid
storing them, and `LOOKUP_ORDER` could put it before the free official sources.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import internet_lookups
from app.tools import docs, lookup_service, lookup_store, lookups, package_registry, page_reader

ERROR = "TypeError: Cannot read properties of undefined (reading 'map') in the list view after an empty response"


@pytest.fixture(params=["shared store", "store unreachable"])
def store(request, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "machine-a"))
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    for variable in ("LOOKUP_ORDER", "LOOKUP_DAILY_CAPS", "LOOKUP_RATES", "LOOKUPS_FROZEN", "STACKEXCHANGE_KEY",
                     "GITHUB_TOKEN", "BRAVE_API_KEY", "TAVILY_API_KEY", "LOOKUP_PAID_RESULTS_KEPT"):
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


def _the_run_chose(monkeypatch, choice: str | None) -> None:
    """The run in progress was started with this Internet lookups choice (its record is the run store's)."""
    monkeypatch.setattr(internet_lookups, "chosen_for_the_run", lambda: choice)


class Upstream:
    """The lookup sources as the network shows them: each request recorded. Stack Exchange answers `advice`;
    Brave, when `brave` is set, answers one web result; every other source finds nothing."""

    def __init__(self, advice: str = "Return an empty list, not undefined.", brave: bool = False) -> None:
        self.sent: list[str] = []
        self.advice, self.brave = advice, brave
        self._lock = threading.Lock()

    def asked(self, host: str) -> int:
        return sum(host in url for url in self.sent)

    def __call__(self, url, headers, body=None):
        with self._lock:
            self.sent.append(url)
        if "search/advanced" in url and self.advice:
            return 200, json.dumps({"items": [{"title": "q1", "link": "https://stackoverflow.com/q/1",
                                               "accepted_answer_id": 1, "last_activity_date": 1_700_000_000}]})
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": 1, "body": f"<p>{self.advice}</p>"}]})
        if "api.search.brave.com" in url and self.brave:
            return 200, json.dumps({"web": {"results": [{
                "title": "Empty responses in list views", "url": "https://blog.example.org/empty-lists",
                "description": "Guard the list before mapping it. " * 12}]}})
        return 200, json.dumps({"items": [], "results": []})


# --- rates ----------------------------------------------------------------------------------------------------------

def test_a_source_s_rate_is_never_passed_by_requests_sent_at_once(store, monkeypatch):
    monkeypatch.setenv("LOOKUP_RATES", "github issues=5/m")
    monkeypatch.setenv("LOOKUP_MOST_WAIT", "0")
    upstream = Upstream()
    start = threading.Barrier(20)
    refused: list[str] = []

    def run():
        start.wait()
        try:
            lookups.guarded("github issues", upstream)("https://api.github.com/search/issues?q=x", {})
        except lookups.Capped as exc:
            refused.append(str(exc))

    threads = [threading.Thread(target=run) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(upstream.sent) == 5
    assert len(refused) == 15 and all("5 requests a minute" in why for why in refused)


def test_a_request_waits_a_moment_for_its_token_rather_than_being_refused(store, monkeypatch):
    monkeypatch.setenv("LOOKUP_RATES", "stack exchange=10/s")
    upstream = Upstream()
    send = lookups.guarded("stack exchange", upstream)

    for _ in range(12):
        send("https://api.stackexchange.com/2.3/info", {})

    assert len(upstream.sent) == 12


def test_the_tokens_one_machine_took_are_gone_for_another(shared, monkeypatch, tmp_path):
    monkeypatch.setenv("LOOKUP_RATES", "github issues=3/h")
    monkeypatch.setenv("LOOKUP_MOST_WAIT", "0")
    for _ in range(3):
        lookups.guarded("github issues", Upstream())("https://api.github.com/search/issues?q=x", {})
    _another_machine(monkeypatch, tmp_path)

    with pytest.raises(lookups.Capped):
        lookups.guarded("github issues", Upstream())("https://api.github.com/search/issues?q=x", {})


# --- the run's "off" choice -----------------------------------------------------------------------------------------

def test_a_run_whose_lookups_are_off_does_not_read_what_another_run_kept(store, monkeypatch):
    lookups.look_up(ERROR, "react 19", fetch=Upstream())
    _the_run_chose(monkeypatch, "off")
    upstream = Upstream("Asked afresh.")

    answer = lookups.look_up(ERROR, "react 19", fetch=upstream)

    assert upstream.asked("search/advanced") == 1
    assert "cached" not in answer and "Asked afresh." in answer["found"][0]["excerpt"]


def test_what_a_run_whose_lookups_are_off_asked_is_kept_for_no_other_run(store, monkeypatch):
    _the_run_chose(monkeypatch, "off")
    lookups.look_up(ERROR, "react 19", fetch=Upstream())
    _the_run_chose(monkeypatch, "when_stuck")
    upstream = Upstream()

    lookups.look_up(ERROR, "react 19", fetch=upstream)

    assert upstream.asked("search/advanced") == 1


def test_a_run_whose_lookups_are_off_reads_robots_txt_afresh(shared, monkeypatch):
    first, second = [], []
    monkeypatch.setattr(page_reader, "_fetch", _a_site(first))
    page_reader.read("https://docs.example.org/guide/one", resolve=lambda host: ["140.82.112.3"])
    _the_run_chose(monkeypatch, "off")
    monkeypatch.setattr(page_reader, "_fetch", _a_site(second))  # another worker

    page_reader.read("https://docs.example.org/guide/two", resolve=lambda host: ["140.82.112.3"])

    assert second == ["https://docs.example.org/robots.txt", "https://docs.example.org/guide/two"]


# --- paid sources ---------------------------------------------------------------------------------------------------

def test_a_paid_search_s_results_are_not_kept_unless_its_terms_allow(store, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "a-paid-key-for-the-test")
    lookups.look_up(ERROR, "react 19", fetch=Upstream(advice="", brave=True))
    upstream = Upstream(advice="", brave=True)

    answer = lookups.look_up(ERROR, "react 19", fetch=upstream)

    assert upstream.asked("api.search.brave.com") == 1, "asked again: its results were not stored"
    assert answer["found"][0]["url"] == "https://blog.example.org/empty-lists" and "cached" not in answer


def test_a_paid_search_whose_terms_allow_storing_is_kept(store, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "a-paid-key-for-the-test")
    monkeypatch.setenv("LOOKUP_PAID_RESULTS_KEPT", "brave")
    lookups.look_up(ERROR, "react 19", fetch=Upstream(advice="", brave=True))
    upstream = Upstream(advice="", brave=True)

    answer = lookups.look_up(ERROR, "react 19", fetch=upstream)

    assert upstream.sent == [] and answer["cached"]


def test_a_paid_search_is_asked_only_after_the_free_official_sources(store, monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "a-paid-key-for-the-test")
    monkeypatch.setenv("LOOKUP_ORDER", "brave,stack exchange")
    upstream = Upstream(advice="", brave=True)

    lookups.look_up(ERROR, "react 19", fetch=upstream)

    first_paid = next(i for i, url in enumerate(upstream.sent) if "api.search.brave.com" in url)
    assert upstream.asked("api.stackexchange.com") and upstream.asked("api.github.com")
    assert all("api.search.brave.com" not in url for url in upstream.sent[:first_paid])
    assert first_paid > max(i for i, url in enumerate(upstream.sent) if "api.github.com" in url)


# --- registries, documentation and pages ----------------------------------------------------------------------------

class Registry:
    """npm as the network shows it: each request recorded, answered after `slow` seconds."""

    def __init__(self, slow: float = 0.0) -> None:
        self.sent: list[str] = []
        self.slow = slow
        self._lock = threading.Lock()

    def __call__(self, url, most_bytes=0):
        with self._lock:
            self.sent.append(url)
        time.sleep(self.slow)
        return 200, json.dumps({"version": "1.3.0", "description": "String left pad"}).encode()


@pytest.fixture
def registry(store, monkeypatch):
    monkeypatch.setattr(package_registry, "runtime_here", lambda ecosystem: "v22.11.0")
    monkeypatch.setattr(package_registry, "_CACHE", {})


def _another_process() -> None:
    """A second worker starts: its own process keeps nothing yet."""
    package_registry._CACHE.clear()  # noqa: SLF001
    docs._CACHE.clear()  # noqa: SLF001


def test_ten_runs_asking_a_registry_about_one_package_at_once_make_one_request(registry, monkeypatch):
    upstream = Registry(slow=0.3)
    monkeypatch.setattr(package_registry, "_fetch", upstream)
    start = threading.Barrier(10)
    versions: list[str] = []

    def run():
        start.wait()
        versions.append(package_registry.look_up("npm", "left-pad")["version"])

    threads = [threading.Thread(target=run) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert upstream.sent == ["https://registry.npmjs.org/left-pad/latest"]
    assert versions == ["1.3.0"] * 10


def test_a_registry_answer_one_worker_read_is_not_asked_for_again_by_another(shared, registry, monkeypatch,
                                                                             tmp_path):
    monkeypatch.setattr(package_registry, "_fetch", Registry())
    package_registry.look_up("npm", "left-pad")
    _another_process()
    _another_machine(monkeypatch, tmp_path)
    upstream = Registry()
    monkeypatch.setattr(package_registry, "_fetch", upstream)

    answer = package_registry.look_up("npm", "left-pad")

    assert upstream.sent == [] and answer["version"] == "1.3.0"


def test_a_registry_answer_for_this_toolchain_is_not_given_to_another(shared, registry, monkeypatch):
    monkeypatch.setattr(package_registry, "_fetch", Registry())
    package_registry.look_up("npm", "left-pad")
    _another_process()
    monkeypatch.setattr(package_registry, "runtime_here", lambda ecosystem: "v18.20.0")
    upstream = Registry()
    monkeypatch.setattr(package_registry, "_fetch", upstream)

    answer = package_registry.look_up("npm", "left-pad")

    assert len(upstream.sent) == 1 and answer["this_environment_runs"] == "v18.20.0"


def test_a_documentation_page_one_worker_read_is_not_fetched_again_by_another(shared, monkeypatch):
    sent: list[str] = []

    def network(url):
        sent.append(url)
        return 200, "# Routing\nDeclare each route once.", "text/markdown"

    monkeypatch.setattr(docs, "_fetched", network)
    docs._fetch("https://hono.dev/llms.txt")  # noqa: SLF001
    _another_process()

    found = docs._fetch("https://hono.dev/llms.txt")  # noqa: SLF001

    assert sent == ["https://hono.dev/llms.txt"] and found[1].startswith("# Routing")


def _a_site(sent: list[str]):
    def fetch(url, address):
        sent.append(url)
        if url.endswith("/robots.txt"):
            return 200, {"content-type": "text/plain"}, b""
        return 200, {"content-type": "text/plain"}, f"The words at {url}.".encode()
    return fetch


def test_a_page_one_run_read_is_not_read_again_by_another(shared, monkeypatch):
    first, second = [], []
    monkeypatch.setattr(page_reader, "_fetch", _a_site(first))
    page_reader.read("https://docs.example.org/guide/routing", resolve=lambda host: ["140.82.112.3"])
    monkeypatch.setattr(page_reader, "_fetch", _a_site(second))

    answer = page_reader.read("https://docs.example.org/guide/routing", resolve=lambda host: ["140.82.112.3"])

    assert second == [] and answer["text"] == "The words at https://docs.example.org/guide/routing."


def _tenant_workspace(root: Path, tenant: str, project: str) -> Path:
    workspace = root / tenant / f"workspace-run-{tenant}"
    (workspace / ".harness").mkdir(parents=True)
    (workspace / ".harness" / "stack-pack.json").write_text(json.dumps({"project": project, "title": project}),
                                                            encoding="utf-8")
    return workspace


def test_a_page_whose_address_holds_a_tenant_s_words_is_not_served_to_another_tenant(shared, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    acme = _tenant_workspace(tmp_path / "workspaces", "acme", "Quillmark")
    globex = _tenant_workspace(tmp_path / "workspaces", "globex", "Harborview")
    address = "https://docs.example.org/quillmark/setup"
    first, second = [], []
    monkeypatch.setattr("app.tools.outbound._the_run_s_workspace", lambda: acme)
    monkeypatch.setattr(page_reader, "_fetch", _a_site(first))
    page_reader.read(address, resolve=lambda host: ["140.82.112.3"])
    monkeypatch.setattr("app.tools.outbound._the_run_s_workspace", lambda: globex)
    monkeypatch.setattr(page_reader, "_fetch", _a_site(second))

    page_reader.read(address, resolve=lambda host: ["140.82.112.3"])

    assert address in second


@pytest.mark.parametrize(("address", "days"), [
    ("https://github.com/owner/lib/releases/tag/v2.1.0", 7),
    ("https://github.com/owner/lib/blob/3f2a9c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f/CHANGELOG.md", 7),
    ("https://docs.example.org/guide/routing", 1 / 24),
])
def test_a_versioned_address_is_kept_a_week_and_any_other_an_hour(address, days):
    assert lookup_service.page_days(address) == days


# --- a run's own record ---------------------------------------------------------------------------------------------

def test_a_stuck_lookup_made_before_a_restart_is_not_made_again_after_it(store, monkeypatch, tmp_path):
    import importlib

    from app.graph import stuck_lookup

    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-restarted")
    asked: list[str] = []

    def look_up(error, stack_words="", private_words=(), **_k):  # the network's edge
        asked.append(error)
        return {"query": "OverflowError: Python int too large to convert to SQLite INTEGER", "asked": [
            "stack exchange"], "found": [{"source": "Stack Overflow, accepted answer", "title": "int too large",
                                          "date": "2024-01-01", "url": "https://stackoverflow.com/q/1",
                                          "excerpt": "Check the id against 2**63 - 1 first."}]}

    monkeypatch.setattr(lookups, "look_up", look_up)
    stack = SimpleNamespace(language="Python", framework="FastAPI")
    defect = SimpleNamespace(description="OverflowError: Python int too large to convert to SQLite INTEGER",
                             source="edge probe", owner="backend", id="d-1")
    workspace = tmp_path / "workspace"
    (workspace / ".harness").mkdir(parents=True)
    monkeypatch.setattr(stuck_lookup, "_stuck", lambda root, found: True)
    before = stuck_lookup.section(workspace, defect, stack)
    looked_up = len(asked)
    stuck_lookup = importlib.reload(stuck_lookup)  # the worker restarts after a deploy
    monkeypatch.setattr(stuck_lookup, "_stuck", lambda root, found: True)

    after = stuck_lookup.section(workspace, defect, stack)

    assert looked_up >= 1 and len(asked) == looked_up
    assert after == before and "2**63 - 1" in after


# --- room for the queue, and the probe ------------------------------------------------------------------------------

def test_nothing_more_is_written_to_the_store_once_half_its_memory_is_used(shared, monkeypatch, tmp_path):
    monkeypatch.setattr(lookup_store, "_ROOM", {}, raising=False)  # the last reading of the store's memory
    monkeypatch.setattr(lookup_store, "memory", lambda: {"used": 300 * 2**20, "most": 512 * 2**20,
                                                          "policy": "noeviction"}, raising=False)
    lookups.look_up(ERROR, "react 19", fetch=Upstream())
    _another_machine(monkeypatch, tmp_path)
    upstream = Upstream()

    lookups.look_up(ERROR, "react 19", fetch=upstream)

    assert upstream.asked("search/advanced") == 1, "kept on the first machine's files, not in the queue's store"


def test_the_probe_says_each_source_s_allowance_its_tokens_and_the_store_s_memory(shared, monkeypatch):
    monkeypatch.setenv("LOOKUP_RATES", "github issues=10/m")
    monkeypatch.setenv("LOOKUP_DAILY_CAPS", "github issues=500")
    for _ in range(4):
        lookups.guarded("github issues", Upstream())("https://api.github.com/search/issues?q=x", {})

    lines = lookup_service.probe_lines()

    assert "LOOKUPS allowance github issues: 4 of 500 requests today (496 left)" in lines
    assert "LOOKUPS rate github issues: 6 of 10 tokens (refilled 10 a minute)" in lines
    assert any(line.startswith("LOOKUPS store memory: ") and "lookup keys" in line for line in lines)
