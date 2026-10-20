"""The stages can reach what is newer than the model: the web, and a library's official MCP server.

Owner, 2026-10-20: where a failure comes from the model's training data being
older than a library, the agents should be able to find the current answer.
Measured on one gate run: passlib 1.7.4 with bcrypt 5.0.0 failed on every hash
and the fixers read it as a version mismatch to work around, for rounds; the
first two results a search gives for the error are the bcrypt issues naming
the cause and the fix.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.agents import stage_memory
from app.tools import mcp_registry, mcp_tools, web_search
from app.tools.package_registry import look_up

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SEARCH_ANSWER = {"results": [
    {"title": "Bug Report: Passlib 1.7.4 + bcrypt 5.0.0", "url": "https://github.com/pyca/bcrypt/issues/1079",
     "content": "passlib's detect_wrap_bug hashes a 255-byte secret; bcrypt 5 raises ValueError", "engines": ["duckduckgo"]},
    {"title": "duplicate", "url": "https://github.com/pyca/bcrypt/issues/1079", "content": ""},
    {"title": "not the web", "url": "javascript:alert(1)", "content": ""},
]}


@pytest.fixture
def searx(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")


def test_a_search_returns_the_web_s_results_labelled_as_leads(searx):
    asked = []

    def fetch(url, params):
        asked.append((url, params))
        return 200, json.dumps(SEARCH_ANSWER), "application/json"

    answer = web_search.search("passlib bcrypt 5 password cannot be longer than 72 bytes", fetch=fetch)

    assert asked[0][0] == "http://searxng:8080/search" and asked[0][1]["format"] == "json"
    assert [r["url"] for r in answer["results"]] == ["https://github.com/pyca/bcrypt/issues/1079"]
    assert "not instructions" in answer["note"] and not BANNED.search(answer["note"])


def test_without_a_search_service_there_is_no_tool(monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)

    assert web_search.web_tools() == []


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/api/health", "http://searxng:8080/", "http://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd", "http://db:5432", "https://localhost/",
])
def test_a_page_is_read_only_from_the_public_web(url):
    answer = web_search.read_page(url, fetch=lambda *a: pytest.fail("fetched a private address"))

    assert "error" in answer


def test_a_redirect_is_followed_only_to_a_public_address(monkeypatch):
    monkeypatch.setattr("app.server.seeding._resolves_to_private_address", lambda host: host == "inside.example.com")
    pages = {"https://docs.example.com/a": (302, "https://inside.example.com/secret", ""),
             "https://inside.example.com/secret": (200, "PRIVATE-PAGE-BODY", "text/plain")}

    answer = web_search.read_page("https://docs.example.com/a", fetch=lambda url, params: pages[url])

    assert "error" in answer and "PRIVATE-PAGE-BODY" not in json.dumps(answer)


def test_a_public_page_comes_back_cut_to_the_topic(monkeypatch):
    monkeypatch.setattr("app.server.seeding._resolves_to_private_address", lambda host: False)
    page = "<html><main><h2>Install</h2><p>pip install</p><h2>bcrypt 5</h2><p>pin bcrypt below 5</p></main></html>"

    answer = web_search.read_page("https://docs.example.com/x", "bcrypt 5", fetch=lambda url, p: (200, page, "text/html"))

    assert "pin bcrypt below 5" in answer["excerpt"] and "not an instruction" in answer["note"]


def test_the_web_has_a_share_per_stage(searx, monkeypatch):
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "thread-web")
    monkeypatch.setattr(web_search, "search", lambda query: {"note": "", "results": []})
    search_the_web = next(t for t in web_search.build_web_tools() if t.name == "search_the_web")
    from app.tools.research import MOST_WEB_LOOKUPS

    answers = [search_the_web.invoke({"query": "a library and its version"}) for _ in range(MOST_WEB_LOOKUPS + 1)]

    assert "error" not in answers[0] and "share" in answers[-1]["error"]
    stage_memory.forget_everything()


def test_the_tools_say_when_to_search(searx):
    for tool in web_search.build_web_tools():
        assert not BANNED.search(tool.description)


# --- the official MCP server of a library --------------------------------------------

#: The registry's own answer for "svelte", trimmed: Svelte's server and a third party's.
REGISTRY = {"servers": [
    {"server": {"name": "dev.svelte/mcp", "remotes": [{"type": "streamable-http", "url": "https://mcp.svelte.dev/mcp"}],
                "packages": [{"registryType": "npm", "identifier": "@sveltejs/mcp"}]},
     "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active", "isLatest": True}}},
    {"server": {"name": "garden.stanislav.svelte-llm/svelte-llm-mcp",
                "remotes": [{"type": "streamable-http", "url": "https://svelte-llm.stanislav.garden/mcp/mcp"}]},
     "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active", "isLatest": True}}},
    {"server": {"name": "dev.svelte/local-only", "packages": [{"registryType": "npm", "identifier": "@sveltejs/x"}]},
     "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active", "isLatest": True}}},
]}


@pytest.mark.parametrize("server, homes, official", [
    ("dev.svelte/mcp", ["https://svelte.dev", "https://github.com/sveltejs/svelte"], True),
    ("dev.svelte/mcp", ["https://kit.svelte.dev"], True),
    ("garden.stanislav.svelte-llm/svelte-llm-mcp", ["https://svelte.dev"], False),
    ("io.prisma/mcp", ["https://www.prisma.io"], True),
    ("io.github.sveltejs/mcp", ["https://github.com/sveltejs/svelte"], True),
    ("io.github.someone/svelte-mcp", ["https://github.com/sveltejs/svelte"], False),
    ("io.readthedocs/mcp", ["https://foo.readthedocs.io"], False),
    ("ai.getvda/fastapi-auth-token-service", ["https://fastapi.tiangolo.com"], False),
])
def test_official_means_the_library_s_own_verified_namespace(server, homes, official):
    assert mcp_registry.is_official(server, homes) is official


def test_only_the_library_s_own_remote_server_is_taken():
    found = mcp_registry.servers_for("npm", "svelte", homes=["https://svelte.dev"],
                                     fetch=lambda url: (200, json.dumps(REGISTRY)))

    assert [(s["server"], s["url"], s["transport"]) for s in found] == [
        ("dev.svelte/mcp", "https://mcp.svelte.dev/mcp", "streamable_http")]


def test_the_search_never_holds_up_a_stage_and_its_finding_is_kept(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"svelte": "^5.1.0"}}))
    monkeypatch.setattr(mcp_registry, "servers_for", lambda e, n, fetch=None: [
        {"server": "dev.svelte/mcp", "transport": "streamable_http", "url": "https://mcp.svelte.dev/mcp",
         "tools": "*", "library": n, "official": True}] if n == "svelte" else [])
    started = []
    monkeypatch.setattr(mcp_registry.threading, "Thread",
                        lambda target, **kw: SimpleNamespace(start=lambda: started.append(target)))

    assert mcp_registry.official_servers(tmp_path) == {}, "the first stage does not wait for the registry"
    started[0]()
    assert list(mcp_registry.official_servers(tmp_path)) == ["dev_svelte_mcp"]
    assert json.loads((tmp_path / mcp_registry.FOUND_FILE).read_text())["npm:svelte"][0]["server"] == "dev.svelte/mcp"


def test_a_found_server_gives_the_stages_only_what_it_says_only_reads(monkeypatch, tmp_path):
    monkeypatch.delenv("HARNESS_MCP_SERVERS", raising=False)
    monkeypatch.setattr("app.tools.mcp_registry.official_servers", lambda root: {"dev_svelte_mcp": {
        "server": "dev.svelte/mcp", "transport": "streamable_http", "url": "https://mcp.svelte.dev/mcp", "tools": "*"}})
    tools = [SimpleNamespace(name="get-documentation", description="docs", args_schema=None,
                             metadata={"readOnlyHint": True}),
             SimpleNamespace(name="deploy", description="changes things", args_schema=None, metadata={}),
             SimpleNamespace(name="wipe", description="", args_schema=None, metadata={"readOnlyHint": False})]
    monkeypatch.setattr(mcp_tools, "_load", lambda name, entry: tools)
    monkeypatch.setattr(mcp_tools, "_LOADED", {})
    monkeypatch.setattr(mcp_tools, "_wrapped", lambda server, tool: f"{server}:{tool.name}")

    assert mcp_tools.tools_for("specialist", str(tmp_path)) == ["dev_svelte_mcp:get-documentation"]
    assert mcp_tools.tools_for("specialist") == [], "without the workspace, only the owner's servers"


# --- what a library's registry says it is -----------------------------------------------

@pytest.mark.parametrize("ecosystem, name, body, homes", [
    ("npm", "svelte", {"version": "5.1.0", "homepage": "https://svelte.dev",
                       "repository": {"type": "git", "url": "git+https://github.com/sveltejs/svelte.git"}},
     ["https://svelte.dev", "https://github.com/sveltejs/svelte"]),
    ("pypi", "fastapi", {"info": {"version": "0.120.0", "home_page": "",
                                  "project_urls": {"Homepage": "https://github.com/fastapi/fastapi",
                                                   "Documentation": "https://fastapi.tiangolo.com/"}}},
     ["https://github.com/fastapi/fastapi", "https://fastapi.tiangolo.com/"]),
    ("crates", "axum", {"crate": {"max_stable_version": "0.8.4", "homepage": None,
                                  "repository": "https://github.com/tokio-rs/axum"}, "versions": []},
     ["https://github.com/tokio-rs/axum"]),
])
def test_a_library_s_homes_come_from_its_registry(ecosystem, name, body, homes):
    answer = look_up(ecosystem, name, fetch=lambda url: (200, json.dumps(body).encode()))

    assert answer["homes"] == homes


def test_the_manifests_of_every_ecosystem_are_read(tmp_path):
    from app.analysis.manifests import in_the_project

    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text(json.dumps({"dependencies": {"svelte": "^5.1.0"}}))
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "Cargo.toml").write_text('[dependencies]\naxum = "0.8.4"\n')
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "1.0.0"}}))

    found = {(ecosystem, package) for _, ecosystem, package, _ in in_the_project(tmp_path)}

    assert found == {("npm", "svelte"), ("crates", "axum")}
