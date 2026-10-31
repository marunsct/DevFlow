"""A contradiction the design review leaves open is ruled on once, and every later stage reads the same ruling.

Behind `SETTLE_SPEC_CONTRADICTIONS`. Measured on one run: the finding became a known risk, a unit test took one side and a
locked test the other, and fixes were reverted for hours.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app import switches
from app.acceptance.criteria import Criterion
from app.agents.shared_facts import the_facts_section
from app.graph import acceptance_nodes, escalation, workflow
from app.observability import provenance

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SAYS_EMPTY = "GET /health answers 200 with an empty body"
SAYS_JSON = "GET /health answers 200 with a JSON object naming the status"
FINDING = "[blocking] The health criterion and the API contract are mutually exclusive"
OTHER = "[blocking] The retention period is not chosen"
RULINGS_FILE = ".harness/specification_rulings.json"


class Specification(BaseModel):
    acceptance_criteria: list[str] = [SAYS_EMPTY]
    api_and_event_contracts: list[str] = [f"{SAYS_JSON}, as the monitoring expects"]


class Model:
    def __init__(self, reply: str | Exception):
        self.reply, self.asked = reply, []

    def invoke(self, messages, **kwargs):
        self.asked.append(messages[-1].content)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=self.reply)


def _reply(first=SAYS_EMPTY, second=SAYS_JSON, stands="second", finding=1, why="The brief asks for a status."):
    return json.dumps({"rulings": [{"finding": finding, "first_statement": first, "second_statement": second,
                                    "stands": stands, "why": why}]})


def _stuck(tmp_path, findings=(FINDING, OTHER)):
    return {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text="The health route says the service's status."),
        "technical_specification": Specification(),
        "escalation": {"kind": "design", "findings": list(findings), "error": "Still asks for changes."},
    }


def _decide(tmp_path, model, **state):
    return escalation.escalation({**_stuck(tmp_path), **state}, {}, SimpleNamespace(judgement_model=model))


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("SETTLE_SPEC_CONTRADICTIONS", "on")
    monkeypatch.delenv("SHARED_FACTS", raising=False)
    monkeypatch.delenv("PREMIUM_PROJECT_INTELLIGENCE", raising=False)


def _rulings_recorded(update):
    return [d for d in update["decisions"] if "contradicts itself" in d["question"]]


def test_a_ruling_is_recorded_and_the_run_goes_on_unstopped(tmp_path, on):
    model = Model(_reply())
    update = _decide(tmp_path, model)

    assert len(model.asked) == 1
    assert update["stage"] == "scaffold" and update["escalation"] is None
    recorded = _rulings_recorded(update)
    assert len(recorded) == 1
    assert recorded[0]["decision"] == SAYS_JSON and recorded[0]["decided_by"] == "auto"
    assert recorded[0]["rationale"] == "The brief asks for a status."
    assert (tmp_path / "docs" / "decision_log.md").read_text().count("contradicts itself") == 1


def test_the_settled_finding_is_no_longer_said_to_be_open_and_the_other_still_is(tmp_path, on):
    update = _decide(tmp_path, Model(_reply()))
    known = update["known_issues"]
    assert not any(line.startswith("Design review left open") and FINDING in line for line in known)
    assert any(line.startswith("Design review finding settled by DR-") and FINDING in line for line in known)
    assert f"Design review left open: {OTHER}" in known


def test_the_ruling_reaches_a_later_stage_through_the_facts_with_the_shared_facts_off(tmp_path, on):
    _decide(tmp_path, Model(_reply()))
    section = the_facts_section(tmp_path, built=False)
    assert f'"{SAYS_JSON}" stands, over "{SAYS_EMPTY}"' in section
    assert "The brief asks for a status." in section and "DR-" in section


def test_it_follows_the_shared_facts_when_they_have_facts_of_their_own(tmp_path, on, monkeypatch):
    from app.agents import shared_facts

    _decide(tmp_path, Model(_reply()))
    monkeypatch.setenv("SHARED_FACTS", "on")
    monkeypatch.setattr(shared_facts, "facts_from_the_workspace", lambda root, built=True: ["- a fact"])
    section = the_facts_section(tmp_path)
    assert section.index("- a fact") < section.index(SAYS_JSON)


def test_the_acceptance_author_is_told_the_ruling(tmp_path, on, monkeypatch):
    from app.acceptance import suite
    from app.agents import specialists

    _decide(tmp_path, Model(_reply()))
    suite.save_criteria(tmp_path, [Criterion("AC-1", "The health route answers.", "brief")])
    asked = {}

    def gated(state, config, *, initial_request, **_):
        asked.update(initial_request)
        return {}

    monkeypatch.setattr(workflow, "_run_gated_agent", gated)
    monkeypatch.setattr(specialists, "create_specialist_agent", lambda *a, **k: object())
    context = SimpleNamespace(model=None, judgement_model=None, checkpointer=None, repo_root=str(tmp_path), allow_subdirectories=True)
    acceptance_nodes.acceptance_author(_stuck(tmp_path), {}, context)
    assert f'"{SAYS_JSON}" stands' in asked["messages"][-1]["content"]


def test_a_test_rewritten_in_one_call_is_told_the_ruling(tmp_path, on, monkeypatch):
    from app.graph import rewritten_tests

    _decide(tmp_path, Model(_reply()))
    given = {}
    monkeypatch.setattr(rewritten_tests, "enabled", lambda: True)
    monkeypatch.setattr(rewritten_tests, "repair", lambda root, broken, model, **kw: given.update(kw) or True)
    assert acceptance_nodes._rewritten_in_one_call_each(_stuck(tmp_path), ["a test"], object())
    assert f'"{SAYS_JSON}" stands' in given["reference"]


def test_the_planning_stages_are_told_it_too():
    # Inside the graph's closures: the two nodes that plan the sprints and the work orders.
    assert inspect.getsource(workflow).count("with_the_rulings(request,") == 2


def test_only_one_call_is_made_in_a_run_whatever_comes_back_through_the_design_path(tmp_path, on):
    model = Model(_reply())
    _decide(tmp_path, model)
    update = _decide(tmp_path, model)
    assert len(model.asked) == 1
    assert _rulings_recorded(update) == []
    # The first ruling still stands.
    assert SAYS_JSON in the_facts_section(tmp_path)


def test_a_ruling_with_a_quote_not_in_the_specification_is_rejected(tmp_path, on):
    model = Model(_reply(first="GET /health answers with nothing at all"))
    update = _decide(tmp_path, model)
    assert len(model.asked) == 1
    assert _rulings_recorded(update) == []
    assert the_facts_section(tmp_path) == ""
    assert f"Design review left open: {FINDING}" in update["known_issues"]


@pytest.mark.parametrize("change", [
    {"first": "GET"},  # could be found by chance
    {"first": "x" * 501},
    {"second": SAYS_EMPTY},
    {"second": "answers 200 with an empty body"},  # inside the other quote
    {"stands": "neither"},
    {"finding": 9},  # no open finding
    {"finding": 0},
    {"why": "  "},
])
def test_a_ruling_that_does_not_hold_together_is_rejected(tmp_path, on, change):
    model = Model(_reply(**change))
    update = _decide(tmp_path, model)
    assert len(model.asked) == 1 and _rulings_recorded(update) == []


def test_a_quote_across_the_document_s_line_break_is_still_word_for_word(tmp_path, on):
    specification = Specification(acceptance_criteria=["GET /health answers 200\n   with an empty body"])
    model = Model(_reply())
    update = _decide(tmp_path, model, technical_specification=specification)
    assert len(model.asked) == 1 and len(_rulings_recorded(update)) == 1


def test_at_most_five_rulings_are_kept(tmp_path, on):
    pairs = [[f"statement number {n} says yes", f"statement number {n} says no"] for n in range(7)]
    specification = Specification(acceptance_criteria=[text for pair in pairs for text in pair])
    reply = json.dumps({"rulings": [{"finding": 1, "first_statement": a, "second_statement": b, "stands": "first", "why": "So."}
                                    for a, b in pairs]})
    update = _decide(tmp_path, Model(reply), technical_specification=specification)
    assert len(_rulings_recorded(update)) == 5


@pytest.mark.parametrize("reply", [RuntimeError("the server went away"), "not JSON at all", '["a list"]', '{"rulings": "none"}', ""])
def test_a_failed_call_leaves_the_run_exactly_as_it_is_today(tmp_path, on, reply):
    model = Model(reply)
    update = _decide(tmp_path, model)
    assert len(model.asked) == 1
    assert update["stage"] == "scaffold" and update["escalation"] is None
    assert [d["decision"] for d in update["decisions"]] == [
        "build from the latest specification, recording the open points as known risks"]
    assert update["known_issues"] == [f"Design review left open: {FINDING}", f"Design review left open: {OTHER}"]
    assert the_facts_section(tmp_path) == ""


def test_off_nothing_is_asked_or_carried(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLE_SPEC_CONTRADICTIONS", "off")
    monkeypatch.delenv("SHARED_FACTS", raising=False)
    monkeypatch.delenv("PREMIUM_PROJECT_INTELLIGENCE", raising=False)
    model = Model(_reply())
    update = _decide(tmp_path, model)
    assert model.asked == [] and not (tmp_path / RULINGS_FILE).exists()
    assert update["known_issues"] == [f"Design review left open: {FINDING}", f"Design review left open: {OTHER}"]


def test_no_model_and_no_findings_ask_nothing(tmp_path, on):
    assert _decide(tmp_path, None)["stage"] == "scaffold"
    model = Model(_reply())
    state = _stuck(tmp_path, findings=())
    assert escalation.escalation(state, {}, SimpleNamespace(judgement_model=model))["stage"] == "scaffold"
    assert model.asked == []


def test_the_person_s_approval_path_settles_too_and_their_retry_clears_the_rulings(tmp_path, on):
    model = Model(_reply())
    context = SimpleNamespace(judgement_model=model)
    update = escalation.accept(_stuck(tmp_path), {}, context)
    assert update["stage"] == "scaffold" and len(_rulings_recorded(update)) == 1
    assert SAYS_JSON in the_facts_section(tmp_path)

    assert escalation.retry(_stuck(tmp_path), {}, context)["stage"] == "principal_architect"
    assert the_facts_section(tmp_path) == ""
    _decide(tmp_path, model)
    assert len(model.asked) == 1


def test_the_request_gives_the_findings_the_brief_and_the_specification_and_the_preference(tmp_path, on):
    model = Model(_reply())
    _decide(tmp_path, model)
    asked = model.asked[0]
    assert FINDING in asked and OTHER in asked and SAYS_EMPTY in asked and SAYS_JSON in asked
    assert "The health route says the service's status." in asked
    assert asked.index("brief's own words") < asked.index("allows more")


def test_the_words_of_the_rule_are_plain(tmp_path, on):
    from app.agents import specification_rulings

    model = Model(_reply())
    _decide(tmp_path, model, technical_specification=Specification(acceptance_criteria=[SAYS_EMPTY]),
            escalation={"kind": "design", "findings": ["F"], "error": ""}, document=SimpleNamespace(text="B"))
    said = specification_rulings.the_request(["F"], "S", "B") + specification_rulings.explanation + specification_rulings.HEADING
    said += the_facts_section(tmp_path).replace(SAYS_EMPTY, "").replace(SAYS_JSON, "")
    assert not BANNED.search(said)


def test_the_switch_is_registered_and_off(monkeypatch):
    name = "SETTLE_SPEC_CONTRADICTIONS"
    monkeypatch.delenv(name, raising=False)
    assert name in switches.EXPERIMENTS and name not in switches.EXPERIMENTS_ON
    assert provenance.switch(provenance.SWITCHES[name]).enabled() is False
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    assert f"{name}: ${{{name}:-off}}" in compose
