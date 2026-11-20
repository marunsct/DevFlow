"""A fixer whose defect has failed twice is offered the web search and the page reader, that fixer only (plan WL.5,
behind `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`).

Measured before it: offered to every stage, the two tools were called almost never in about 3,500 requests, so they
are offered to none unless the run chose "always". This asks a narrower question - does a model use them when it has
failed at one error twice and is told they are there for it - and records each call, so the audit can answer it.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app import switches
from app.agents.specialists import SpecialistOutput
from app.sprint import Defect, RemediationCycle
from tests.a_role_agent import Scripted, Stopped

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
WEB = {"search_the_web", "read_web_page"}
ERROR = "TypeError: Argument #2 ($handler) must be of type callable, RequestHandlerInterface given"


class _Runs:
    """The run store's record of each run's own switch settings."""

    def __init__(self):
        self.overrides: dict[str, dict[str, bool]] = {}

    def switch_overrides(self, run_id):
        return dict(self.overrides.get(run_id, {}))


@pytest.fixture
def deployed(monkeypatch, tmp_path):
    """The compose file's tools and lean lists, a search service, the switch on; inside a run with no choice of its own."""
    runs = _Runs()
    for name, value in {
        "WEB_TOOLS_AFTER_TWO_FAILED_FIXES": "on", "LEAN_TOOL_LISTS": "on", "WEB_SEARCH_ENABLED": "true",
        "SEARXNG_URL": "http://search.invalid", "SWITCH_OVERRIDES_FROM_SETTINGS": "on", "DATA_DIR": str(tmp_path / "d"),
        "PACKAGE_LOOKUP_ENABLED": "true", "DOCS_LOOKUP_ENABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)
    for name in ("WEB_TOOLS_OFFERED", "WEB_LOOKUP_WHEN_STUCK", "DIAGNOSE_A_RECURRING_CAUSE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.server.run_store.RunStore.shared", classmethod(lambda cls: runs))
    monkeypatch.setattr(switches, "stored", lambda name: None)
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-r")
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-r")
    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001
    yield runs
    switches._RUN_OVERRIDES.clear()  # noqa: SLF001


def _defect(failed: int) -> Defect:
    return Defect(description="The product does not start for the acceptance suite.", severity="major",
                  reproduction_steps="r", expected_behavior="it starts", actual_behavior=ERROR, owner="backend",
                  attempts=[{"stage": f"defect_fix_{n}_0", "outcome": "left open"} for n in range(failed)])


def _the_fixer_is_run(tmp_path, failed: int = 0, defect: Defect | None = None) -> tuple[list[str], str]:
    """(the tool names the fixer's model is offered, the request it is sent) for a defect with `failed` failed fixes
    in its own cycle, or for `defect`."""
    from app.agents.specialists import create_specialist_agent

    model = Scripted(replies=[], requests=[], offered=[])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "defect_cursor": 0, "test_round": 3,
             "remediation": RemediationCycle(sprint_goal="g", defects=[defect or _defect(failed)]),
             "current_sprint_index": 0, "specialist_outputs": {}}

    def on_the_scripted_model(owner, **kwargs):
        return create_specialist_agent(owner, **{**kwargs, "model": model})

    def gated(state, config, *, agent, initial_request, **kwargs):
        try:
            agent.invoke(initial_request, {"configurable": {"thread_id": "fix"}})
        except Stopped:
            pass
        return {"__fix_result__": SpecialistOutput(changed_files=["app/main.py"], decisions=["d"])}

    from app.graph.workflow import build_workflow_graph

    with patch("app.graph.workflow.create_specialist_agent", side_effect=on_the_scripted_model), \
         patch("app.graph.workflow._what_the_last_failure_printed", return_value=""), \
         patch("app.graph.workflow._closed_if_an_earlier_fix_resolved_it", return_value=None), \
         patch("app.graph.workflow._what_the_ledger_confirms", return_value="npm test"), \
         patch("app.graph.acceptance_nodes.done_by_the_definition", return_value=[]), \
         patch("app.graph.engineering.before_a_fix", return_value=""), \
         patch("app.graph.engineering.after_a_fix", return_value=[]), \
         patch("app.graph.workflow._run_gated_agent", side_effect=gated):
        graph = build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        graph.nodes["defect_remediation"].bound.invoke(
            state, {"configurable": {"thread_id": "t", "run_id": "r"}})
    request = next(str(m.content) for m in model.requests[0] if getattr(m, "type", "") == "human")
    return model.offered[0], request


def _ledger(tmp_path, event: str) -> list[dict]:
    path = tmp_path / "d" / "transcripts" / "run-r.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    return [r for r in rows if r.get("kind") == "defect" and r.get("event") == event]


def test_a_fixer_whose_defect_failed_twice_is_offered_the_web_tools_and_told_so(deployed, tmp_path):
    offered, request = _the_fixer_is_run(tmp_path, failed=2)

    assert WEB <= set(offered)
    assert "`search_the_web` and `read_web_page` are offered to you for this error" in request
    assert [r["detail"] for r in _ledger(tmp_path, "web tools offered")] == ["after 2 failed fixes"]


def _a_criterion(criterion: str, *failing: str) -> Defect:
    """An acceptance criterion's defect as a test round raises it: its cause keyed by the tests failing this time."""
    return Defect(description=f"[{criterion}] Group the list - the acceptance suite says this does not work yet.",
                  severity="major", reproduction_steps="r", expected_behavior="e", actual_behavior=ERROR,
                  owner="backend", source="acceptance suite", kind="failing_test",
                  evidence=[{"test": f"[{criterion.lower()}] {name}"} for name in failing],
                  cause_key="failing_test:" + "|".join(f"test:[{criterion.lower()}] {name}" for name in failing))


def _left_open_in_an_earlier_attempt(root, defect: Defect) -> None:
    """One fix of `defect` measured and left open, as the fix stage keeps it in the run's fix journal."""
    from app.graph import cause_journal

    cause_journal.record(root, defect, {"stage": "defect_fix_1_0", "files": ["app/main.py"], "did": "d",
                                        "outcome": "left open: its tests still fail"}, sprint=0)


def test_a_criterion_left_open_once_in_each_of_two_sprint_attempts_is_offered_the_web_tools(deployed, tmp_path):
    """Measured: one criterion left open in a sprint's first attempt and again in its second, its failing tests
    different each time, counted at most one failed fix before each fixer; the tools were never offered."""
    _left_open_in_an_earlier_attempt(tmp_path, _a_criterion("AC-4", "groups", "keeps order", "clears"))
    _left_open_in_an_earlier_attempt(tmp_path, _a_criterion("AC-4", "keeps order"))

    offered, request = _the_fixer_is_run(tmp_path, defect=_a_criterion("AC-4", "keeps order"))

    assert WEB <= set(offered) and "`search_the_web` and `read_web_page`" in request
    assert [r["detail"] for r in _ledger(tmp_path, "web tools offered")] == ["after 2 failed fixes"]


def test_another_criterion_s_failed_fixes_do_not_count_toward_the_web_tools(deployed, tmp_path):
    _left_open_in_an_earlier_attempt(tmp_path, _a_criterion("AC-3", "keeps order"))
    _left_open_in_an_earlier_attempt(tmp_path, _a_criterion("AC-3", "keeps order"))

    offered, request = _the_fixer_is_run(tmp_path, defect=_a_criterion("AC-4", "keeps order"))

    assert not WEB & set(offered) and "search_the_web" not in request


def _a_probe_finding(request: str, error: str) -> Defect:
    return Defect(description=f"The probe's request failed: {error}", severity="major", reproduction_steps="r",
                  expected_behavior="e", actual_behavior=error, owner="backend", source="api probe",
                  kind="probe_finding", evidence=[{"probe": "routes", "request": request}, {"error": error}],
                  cause_key=f"probe_finding:error:{error.lower()}|probe:routes:{request.lower()}")


@pytest.mark.parametrize(("earlier", "counted"), [
    ([("GET /items", "404 not found"), ("GET /items", "500 TypeError")], 2),
    ([("POST /items", "500 KeyError")], 0),
])
def test_a_probe_finding_counts_the_failed_fixes_of_its_probe_and_request_whatever_its_error(tmp_path, earlier,
                                                                                             counted):
    from app.graph import cause_journal

    for request, error in earlier:
        _left_open_in_an_earlier_attempt(tmp_path, _a_probe_finding(request, error))

    assert cause_journal.failed_fixes_in_the_run(tmp_path, _a_probe_finding("GET /items", "500 KeyError")) == counted


@pytest.mark.parametrize("failed", [0, 1])
def test_a_fixer_with_fewer_than_two_failed_fixes_is_not_offered_them(deployed, tmp_path, failed):
    offered, request = _the_fixer_is_run(tmp_path, failed=failed)

    assert not WEB & set(offered) and "search_the_web" not in request


def test_with_the_switch_off_a_fixer_that_failed_twice_is_not_offered_them(deployed, tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_TOOLS_AFTER_TWO_FAILED_FIXES", "off")

    offered, request = _the_fixer_is_run(tmp_path, failed=2)

    assert not WEB & set(offered) and "search_the_web" not in request


def test_a_run_started_with_internet_lookups_off_offers_them_to_no_fixer(deployed, tmp_path):
    from app.internet_lookups import switches_for

    deployed.overrides["run-r"] = switches_for("off")

    offered, request = _the_fixer_is_run(tmp_path, failed=2)

    assert not WEB & set(offered) and "search_the_web" not in request


def test_another_stage_is_not_offered_them(deployed, tmp_path):
    from app.agents.specialists import create_specialist_agent

    model = Scripted(replies=[], requests=[], offered=[])
    try:
        create_specialist_agent("backend", model=model, repo_root=str(tmp_path)).invoke(
            {"messages": [{"role": "user", "content": "build it"}]}, {"configurable": {"thread_id": "b"}})
    except Stopped:
        pass

    assert not WEB & set(model.offered[0])


def _the_fixer_s_tools(monkeypatch, tmp_path, found: dict) -> dict:
    from app.graph import web_tools_after_two_failed_fixes
    from app.tools import web_search

    monkeypatch.setattr(web_search, "_get", lambda url, params=None: (200, json.dumps(found), "application/json"))
    cycle = RemediationCycle(sprint_goal="g", defects=[_defect(2)])
    return {t.name: t for t in web_tools_after_two_failed_fixes.tools_for(cycle, 0, "defect_fix_3_0", root=tmp_path)}


def test_each_call_of_a_fixer_s_web_tool_is_a_ledger_record_of_what_it_asked_and_found(deployed, tmp_path,
                                                                                       monkeypatch):
    tools = _the_fixer_s_tools(monkeypatch, tmp_path, {"results": [
        {"url": f"https://stackoverflow.com/q/{n}", "title": "t", "content": "c"} for n in range(3)]})

    tools["search_the_web"].invoke({"query": ERROR})

    calls = _ledger(tmp_path, "web tool call")
    assert len(calls) == 1 and calls[0]["stage"] == "defect_fix_3_0"
    assert "search_the_web" in calls[0]["detail"] and "RequestHandlerInterface" in calls[0]["detail"]
    assert "3 result(s)" in calls[0]["detail"]
    assert calls[0]["defect_id"] == _ledger(tmp_path, "web tools offered")[0]["defect_id"] != ""


def test_the_fixer_s_page_reader_refuses_a_private_address(deployed, tmp_path, monkeypatch):
    tools = _the_fixer_s_tools(monkeypatch, tmp_path, {"results": []})
    monkeypatch.setattr("app.tools.page_reader._fetch", lambda *a: pytest.fail("fetched a private address"))

    answer = tools["read_web_page"].invoke({"url": "http://169.254.169.254/latest/meta-data/"})

    assert "error" in answer and "error:" in _ledger(tmp_path, "web tool call")[0]["detail"]


def test_what_the_fixer_is_told_names_none_of_the_banned_words():
    from app.graph.web_tools_after_two_failed_fixes import SAID

    assert "search_the_web" in SAID and not BANNED.search(SAID)


def test_failed_fixes_recorded_before_problems_were_keyed_count_by_the_criteria_their_text_names(tmp_path):
    """Measured on the deploy that added problem keys: a live run's earlier failed fixes of [AC-4] carried none, so
    the count started again at nought for the next fixer of the very same criterion."""
    from app.graph import cause_journal

    for failing in (("groups",), ("keeps order",)):
        _left_open_in_an_earlier_attempt(tmp_path, _a_criterion("AC-4", *failing))
        _left_open_in_an_earlier_attempt(tmp_path, _a_criterion("AC-3", *failing))
    journal = tmp_path / ".harness" / "fix-journal.json"
    kept = json.loads(journal.read_text())
    for cause in kept["causes"].values():
        for entry in cause["entries"]:
            entry.pop("problem", None)
    journal.write_text(json.dumps(kept))

    assert cause_journal.failed_fixes_in_the_run(tmp_path, _a_criterion("AC-4", "clears")) == 2
