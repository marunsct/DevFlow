"""Every query that leaves the machine passes one gate: the product's own words out, public identifiers kept, each one
recorded (plan HK.5, LF.1291).

Measured before it: a model's own `search_the_web` went out as the model wrote it, and the harness's lookups took out
only the folder, the project and the title - not the product's name from the intake nor the nouns its routes are named
by, which a stuck error quotes (`reading_lists.bookmark_id`). Nothing recorded what had been sent.
"""
from __future__ import annotations

import json
import re
import runpy
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.agents import stage_memory
from app.graph import stuck_lookup
from app.tools import lookups, package_registry, page_reader, web_search

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
RUN = "run-gate"
EFFECTS = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
#: The product's own words in the workspace below, in the ways code and prose spell them.
PRIVATE = re.compile(r"link\W?shelf|reading\W?lists?|bookmark", re.I)


def _workspace(root: Path) -> Path:
    """A run's workspace: its contract, intake and specification name the product and its routes; the project
    declares `events` and `sqlalchemy`, found in their registries."""
    workspace = root / "shared" / f"workspace-{RUN}"
    (workspace / ".harness").mkdir(parents=True)
    (workspace / "docs").mkdir()
    (workspace / ".harness" / "stack-pack.json").write_text(json.dumps(
        {"pack": "python-fastapi", "project": "link-shelf", "title": "Link Shelf"}), encoding="utf-8")
    (workspace / "docs" / "product_intake.md").write_text("# Product Intake — LinkShelf\n\n## Users\n- readers\n",
                                                          encoding="utf-8")
    (workspace / "docs" / "technical_specification.md").write_text(
        "## Interface contract\nAC-1 GET /api/bookmarks -> 200\nAC-2 POST /api/reading-lists -> 201\n"
        "AC-3 GET /api/events/{id} -> 200\nAC-4 POST /auth/login -> 200\n", encoding="utf-8")
    (workspace / ".harness" / "dependency-gate.json").write_text(json.dumps(
        {"npm:events": {"verdict": "allowed"}, "pypi:sqlalchemy": {"verdict": "allowed"}}), encoding="utf-8")
    return workspace


@pytest.fixture
def run(monkeypatch, tmp_path):
    """A run in progress, its workspace found from the run's id, its transcript kept under DATA_DIR."""
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: RUN)
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: "thread-gate")
    stuck_lookup._DONE.clear()  # noqa: SLF001
    yield _workspace(tmp_path / "workspaces")
    stage_memory.forget_everything()


def _outbound(data: Path) -> list[dict]:
    path = data / "transcripts" / f"{RUN}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return [r for r in map(json.loads, lines) if r.get("kind") == "outbound"]


def _searched_by_a_model(monkeypatch, query: str) -> list[str]:
    """What the private search was asked when a model searched for `query`."""
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    asked: list[str] = []

    def fetch(url, params=None):
        asked.append(str((params or {}).get("q")))
        return 200, json.dumps({"results": [{"title": "IntegrityError", "url": "https://github.com/x/y/issues/1",
                                             "content": "a lead"}]}), "application/json"

    monkeypatch.setattr(web_search, "_get", fetch)
    search_the_web = next(t for t in web_search.build_web_tools() if t.name == "search_the_web")
    search_the_web.invoke({"query": query})
    return asked


MODEL_QUERY = "LinkShelf sqlalchemy.exc.IntegrityError E1101 on ReadingList bookmark_tags 2.0.36"


def test_a_model_s_web_search_leaves_without_the_product_s_name_or_its_nouns(run, monkeypatch):
    asked = _searched_by_a_model(monkeypatch, MODEL_QUERY)

    assert asked and not PRIVATE.search(asked[0]), asked
    assert "sqlalchemy.exc.IntegrityError" in asked[0] and "E1101" in asked[0] and "2.0.36" in asked[0]


def test_a_model_s_web_search_is_recorded_as_it_was_sent(run, monkeypatch, tmp_path):
    asked = _searched_by_a_model(monkeypatch, MODEL_QUERY)

    records = _outbound(tmp_path / "data")
    assert [(r["channel"], r["sent"]) for r in records] == [("web search", asked[0])]
    assert records[0]["removed"] >= 3 and not PRIVATE.search(json.dumps(records))


def test_a_page_a_model_reads_is_asked_for_without_the_product_s_words_in_its_query_string(run, monkeypatch):
    asked: list[str] = []

    def fetch(url, address):
        asked.append(url)
        return (404, {}, b"") if url.endswith("/robots.txt") else (200, {"content-type": "text/plain"}, b"A page.")

    monkeypatch.setattr(page_reader, "_fetch", fetch)
    monkeypatch.setattr(page_reader, "_resolve", lambda host: ["93.184.215.14"])
    read_web_page = next(t for t in web_search.build_web_tools() if t.name == "read_web_page")

    read_web_page.invoke({"url": "https://forum.example.org/search?q=LinkShelf+reading+lists+IntegrityError&page=2"})

    page = next(u for u in asked if not u.endswith("/robots.txt"))
    query = parse_qs(urlsplit(page).query)
    assert urlsplit(page).netloc == "forum.example.org" and urlsplit(page).path == "/search"
    assert query["q"] == ["IntegrityError"] and query["page"] == ["2"], page


def _stuck(error: str) -> SimpleNamespace:
    return SimpleNamespace(description="The product does not start for the acceptance suite.", actual_behavior=error,
                           attempts=[{"stage": "defect_fix_1_0", "outcome": "left open"}])


def _looked_up_for_a_stuck_fixer(monkeypatch, workspace: Path, error: str) -> list[str]:
    """The queries the harness's lookup sent to Stack Exchange for a stuck defect stating `error`."""
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    sent: list[str] = []

    def fetch(url, headers, body=None):
        if "api.stackexchange.com" in url and "search/advanced" in url:
            sent.extend(parse_qs(urlsplit(url).query)["q"])
        return 404, ""

    monkeypatch.setattr(lookups, "_get", fetch)
    stuck_lookup.section(workspace, _stuck(error), SimpleNamespace(language="Python", framework="FastAPI"))
    return sent


def test_a_stuck_lookup_never_carries_the_product_s_nouns(run, monkeypatch):
    sent = _looked_up_for_a_stuck_fixer(
        monkeypatch, run,
        "sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) NOT NULL constraint failed: reading_lists.bookmark_id")

    assert sent and not any(PRIVATE.search(query) for query in sent), sent
    assert "sqlalchemy.exc.IntegrityError" in sent[0] and "NOT NULL constraint failed" in sent[0]


def test_a_declared_package_spelled_like_a_route_s_noun_and_an_error_code_stay_in_a_lookup(run, monkeypatch,
                                                                                           tmp_path):
    sent = _looked_up_for_a_stuck_fixer(
        monkeypatch, run, "Error: ERR_UNHANDLED_ERROR unhandled error in events 3.3.0 while saving a Bookmark")

    # Several short queries now (plan HK.3(b)): the code with the library, then the message's own words.
    assert sent and "ERR_UNHANDLED_ERROR" in sent[0] and "events" in sent[0], sent
    assert any("events 3.3.0" in query for query in sent), sent
    assert not any(PRIVATE.search(query) for query in sent), sent
    records = _outbound(tmp_path / "data")
    assert [r["sent"] for r in records if r["channel"] == "lookup"] == sent
    assert {r["channel"] for r in records} <= {"lookup", "registry"} and not PRIVATE.search(json.dumps(records))


def test_a_registry_is_never_asked_for_the_product_s_own_name(run):
    asked: list[str] = []

    def fetch(url):
        asked.append(url)
        return 200, json.dumps({"version": "1.0.0"}).encode()

    own = package_registry.look_up("npm", "@link-shelf/web", fetch=fetch)
    public = package_registry.look_up("npm", "events", fetch=fetch)

    assert asked == ["https://registry.npmjs.org/events/latest"] and public["version"] == "1.0.0"
    assert "not sent" in own["error"] and not BANNED.search(own["error"])


def test_the_effects_report_counts_what_left_and_what_was_cleaned():
    records = [{"kind": "outbound", "channel": "web search", "sent": "x", "removed": 2},
               {"kind": "outbound", "channel": "lookup", "sent": "y", "removed": 0},
               {"kind": "outbound", "channel": "registry", "sent": "", "refused": "the product's own name"}]

    lines = "\n".join(runpy.run_path(str(EFFECTS))["effects"](records, ""))

    assert "   2  LF.1291 outbound queries through the one gate (web search 1, lookup 1)" in lines
    assert "1 with the product's words taken out; 1 not sent" in lines
