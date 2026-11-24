"""The web tools a model is offered follow what the model diagnosis measured it to do (plan HK.11, LF.1307).

Measured before it: the web search and the page reader were offered to every model on every stage that reads
documentation when a run chose "Always" - about 3,300 characters of tool schema a request - and the local model called
them 0 times in 24 runs. Now the diagnosis asks whether a model, given a file to write against a release newer than its
training and a lookup, calls the lookup and uses its answer, and keeps the verdict with the model's capabilities. A
model that does is offered one `research(question)` tool whose answer is a short checked note, never pages or raw
leads; a model that never does is offered no web tool (behind `WEB_TOOLS_BY_MEASURED_TIER`, off until measured); a
model not yet measured is offered what it was before. The run's Internet lookups choice still decides whether anything
leaves.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import switches
from app.models import capabilities
from app.tools import lookups

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
MODEL = "measured-model"


# --- the diagnosis's check ------------------------------------------------------------------------------------------

def _call(name: str, arguments: dict, call_id: str = "c1") -> dict:
    return {"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}}]}


def _text(content: str) -> dict:
    return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}


class Server:
    """A model server whose model, offered a lookup, does as `asks` and `writes` say; any other probe gets text.

    `asks`: it asks the lookup before writing. `writes`: the store line it writes once it has (or has not) asked."""

    def __init__(self, asks: bool, writes: str):
        self.asks, self.writes, self.sent = asks, writes, []

    def create(self, **payload):
        self.sent.append(payload)
        names = {tool["function"]["name"] for tool in payload.get("tools") or []}
        if "research" not in names:
            return _text("Hello.")
        answered = payload["messages"][-1]["role"] == "tool"
        if self.asks and not answered:
            return _call("research", {"question": "tidewell 4.0 how is a store opened"})
        return _call("write_artifact", {"relative_path": "orders-svc/store.py",
                                        "content": f"import os\nimport tidewell\n\nstore = {self.writes}\n"}, "c2")


class Restarting:
    def create(self, **payload):
        raise ConnectionError("Connection error.")


def _model(server) -> SimpleNamespace:
    return SimpleNamespace(model_name=MODEL, root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.models import model_guidance

    monkeypatch.setattr(model_guidance, "served_now", lambda: MODEL)
    monkeypatch.setattr("app.models.model_pin.pinned_snapshot", lambda: None)
    monkeypatch.delenv("WEB_TOOLS_BY_MEASURED_TIER", raising=False)


def test_a_model_that_asks_and_uses_the_answer_is_measured_as_one_that_looks_things_up():
    found = capabilities.measure(_model(Server(asks=True, writes='tidewell.attach_store(os.environ["STORE_URL"])')))

    assert found["researches"]["value"] is True
    assert "called it 3/3" in found["researches"]["note"] and "used the answer 3/3" in found["researches"]["note"]


@pytest.mark.parametrize("asks, writes, called", [
    (False, 'tidewell.open(os.environ["STORE_URL"])', "called it 0/3"),
    (True, 'tidewell.open(os.environ["STORE_URL"])', "called it 3/3"),
])
def test_a_model_that_never_asks_or_ignores_the_answer_is_measured_as_one_that_does_not(asks, writes, called):
    found = capabilities.measure(_model(Server(asks=asks, writes=writes)))

    assert found["researches"]["value"] is False
    assert called in found["researches"]["note"] and "used the answer 0/3" in found["researches"]["note"]


def test_a_server_that_does_not_answer_leaves_the_verdict_unknown():
    assert "researches" not in capabilities.measure(_model(Restarting()))


def test_the_check_offers_the_lookup_a_stage_is_offered_and_its_words_carry_no_banned_word():
    server = Server(asks=True, writes="tidewell.attach_store(url)")

    capabilities.measure(_model(server))

    from app.tools.research_tool import build_research_tool

    stage_tool = build_research_tool(".")
    offered = [tool for p in server.sent for tool in p.get("tools") or [] if tool["function"]["name"] == "research"]
    assert offered and offered[0]["function"]["description"] == stage_tool.description
    sent = json.dumps([p["messages"] for p in server.sent if p.get("tools")]) + json.dumps(offered[0])
    assert not BANNED.search(sent)


def test_the_verdict_is_kept_with_the_model_s_capabilities_and_measured_once():
    from app.models import research_check

    server = Server(asks=True, writes="tidewell.attach_store(url)")
    first = research_check.measure_if_new(_model(server), MODEL)
    asked = len(server.sent)

    again = research_check.measure_if_new(_model(server), MODEL)

    row = next(r for r in capabilities.resolved(MODEL) if r["key"] == "researches")
    assert first is True and again is True and len(server.sent) == asked
    assert row["value"] is True and row["source"] == "measured"


# --- what a stage is offered -----------------------------------------------------------------------------------------

class _Runs:
    def __init__(self):
        self.overrides: dict[str, dict[str, bool]] = {}

    def switch_overrides(self, run_id):
        return dict(self.overrides.get(run_id, {}))


@pytest.fixture
def a_run(monkeypatch):
    """Inside a run whose record holds its own Internet lookups choice; a search service is configured."""
    from app.internet_lookups import switches_for

    runs = _Runs()
    monkeypatch.setenv("SWITCH_OVERRIDES_FROM_SETTINGS", "on")
    monkeypatch.setenv("SEARXNG_URL", "http://search.invalid")
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
    monkeypatch.setattr("app.server.run_store.RunStore.shared", classmethod(lambda cls: runs))
    monkeypatch.setattr(switches, "stored", lambda name: None)
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-tiered")
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001

    def started_with(choice: str) -> None:
        runs.overrides["run-tiered"] = switches_for(choice)

    yield started_with
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001


def _measured(verdict: bool) -> None:
    from app.models import _runtime_settings
    from app.models.registry import merge_into_fitness

    for name in {MODEL, str(_runtime_settings().model_name or "")} - {""}:
        merge_into_fitness(name, {"capabilities_found": {"researches": {"value": verdict, "source": "measured"}}})


def _offered() -> set[str]:
    from app.tools import web_search

    return {tool.name for tool in web_search.web_tools()}


def test_a_model_measured_to_look_things_up_is_offered_one_research_tool_in_place_of_the_web_tools(a_run):
    a_run("always")
    _measured(True)

    assert _offered() == {"research"}


@pytest.mark.parametrize("switch, offered", [("on", set()), ("off", {"search_the_web", "read_web_page"})])
def test_a_model_measured_never_to_look_things_up_is_offered_no_web_tool_with_the_switch_on(a_run, monkeypatch,
                                                                                           switch, offered):
    monkeypatch.setenv("WEB_TOOLS_BY_MEASURED_TIER", switch)
    a_run("always")
    _measured(False)

    assert _offered() == offered


def test_a_model_not_yet_measured_is_offered_what_it_was_before(a_run, monkeypatch):
    monkeypatch.setenv("WEB_TOOLS_BY_MEASURED_TIER", "on")
    a_run("always")

    assert _offered() == {"search_the_web", "read_web_page"}


@pytest.mark.parametrize("choice", ["off", "when_stuck"])
def test_a_run_whose_choice_is_not_always_is_offered_no_lookup_whatever_the_model(a_run, choice):
    a_run(choice)
    _measured(True)

    assert _offered() == set()


# --- what the research tool answers ----------------------------------------------------------------------------------

STUCK = ("error[E0599]: no method named `fetch_optional` found for struct `sqlx::query::QueryAs` in the current "
         "scope")
ISSUE_LEAD = {"items": [{"title": "E0599 on fetch_optional", "state": "closed", "comments": 4,
                         "html_url": "https://github.com/launchbadge/sqlx/issues/3",
                         "closed_at": "2026-03-02T10:00:00Z", "body": "I get E0599 when I call fetch_optional."}]}
ISSUE = {"title": "E0599 on fetch_optional", "state": "closed", "closed_at": "2026-03-02T10:00:00Z",
         "created_at": "2026-03-01T09:00:00Z", "html_url": "https://github.com/launchbadge/sqlx/issues/3",
         "user": {"login": "reporter"}, "body": "I get E0599 when I call fetch_optional."}
COMMENTS = [{"body": "Bring the `Executor` trait into scope; fixed in 0.8.3.", "author_association": "MEMBER",
             "created_at": "2026-03-02T09:58:00Z", "user": {"login": "maintainer"}}]


class Condenser:
    """The build model: answers the condensing request with `reply`."""

    def __init__(self, reply: str):
        self.reply, self.asked = reply, []

    def invoke(self, messages, **_kwargs):
        from langchain_core.messages import AIMessage

        self.asked.append(messages)
        return AIMessage(content=self.reply)


@pytest.fixture
def a_project_with_a_lead(tmp_path, monkeypatch):
    """A Rust project on sqlx 0.8.2 whose tracker holds an issue on the error, with the maintainer's resolution."""
    monkeypatch.delenv("STUCK_LOOKUP_CONDENSED", raising=False)
    for variable in ("STACKEXCHANGE_KEY", "GITHUB_TOKEN", "LOOKUP_ORDER", "LOOKUP_DAILY_CAPS"):
        monkeypatch.delenv(variable, raising=False)
    answers = {"search/issues": ISSUE_LEAD, "/repos/launchbadge/sqlx/issues/3/comments": COMMENTS,
               "/repos/launchbadge/sqlx/issues/3": ISSUE}

    def sites(url, headers, body=None):
        for marker, answer in answers.items():
            if marker in url:
                return 200, json.dumps(answer), {}
        return 200, json.dumps({"items": []}), {}

    monkeypatch.setattr(lookups, "_get", sites)
    workspace = tmp_path / "workspace-r"
    (workspace / ".harness").mkdir(parents=True)
    (workspace / ".harness" / "dependency-gate.json").write_text(json.dumps({"crates:sqlx": {"verdict": "allowed"}}))
    (workspace / ".harness" / "stack-facts.json").write_text(json.dumps({"dependencies": [
        {"name": "sqlx", "version": "0.8.2", "released": "2025-07-05", "homes": ["https://github.com/launchbadge/sqlx"]}]}))
    return workspace


def test_the_research_tool_answers_with_a_checked_note_never_the_raw_leads(a_project_with_a_lead):
    from app.tools.research_tool import build_research_tool

    condenser = Condenser(json.dumps({"applies": True, "cause": "The `Executor` trait is not in scope.",
                                      "change": "Add `use sqlx::Executor;` where the query runs.",
                                      "versions": "sqlx 0.7", "source": "1"}))

    answer = build_research_tool(a_project_with_a_lead, model=condenser).invoke({"question": STUCK})

    note = answer["note"]
    assert len(condenser.asked) == 1, "condensed although STUCK_LOOKUP_CONDENSED is off"
    assert "Change: Add `use sqlx::Executor;` where the query runs." in note
    assert "another release line (0.7)" in note and "0.8.2" in note
    assert "Resolution (maintainer" not in note and "I get E0599" not in note
    kept = [json.loads(line) for line in
            (Path(a_project_with_a_lead) / ".harness/research/notes.jsonl").read_text().splitlines()]
    assert kept[-1]["trigger"] == "research tool" and kept[-1]["verdict"] == "applies"


def test_when_nothing_is_condensed_the_research_tool_says_so_and_hands_over_no_lead(a_project_with_a_lead):
    from app.tools.research_tool import build_research_tool

    answer = build_research_tool(a_project_with_a_lead, model=Condenser("I could not say.")).invoke(
        {"question": STUCK})

    assert "Nothing checked was found" in answer["note"]
    assert "github.com" not in answer["note"] and "Executor" not in answer["note"]
    assert not BANNED.search(answer["note"])
