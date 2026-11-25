"""With `ADVICE_SIZED_TO_THE_BRIEF` on, the specialists' advice is sized to the brief (plan PA.9).

Measured over 11 small runs: advisers returned 9.4 of the 10 items allowed each, about 33 a run for products of 8 to
10 criteria; one medium specification held 88 advice decisions, every one checked again each sprint, and a rate
limit no suite could run under was adopted advice.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents.specialist_advice import SpecialistAdvice
from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
from app.state import RepositoryContext
from workflow_nodes import a_specification, an_architect, an_architect_state, run_node

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

BRIEF = """# Notes

A small service that keeps notes.

## Acceptance criteria
- A user can add a note with a title
- A user can list the notes, newest first
- A user can delete a note
- An empty title is refused with a message
"""

TEN = [
    "[beyond] Limit each client to 100 requests a minute.",
    '[asked] "A user can add a note with a title": refuse a body with no title with 422.',
    "[beyond] Log every request as JSON.",
    '[asked] "A user can list the notes, newest first": sort by the stored creation time, newest first.',
    "[beyond] Add an ETag to the list.",
    '[asked] "A user can delete a note": answer 404 for an id that does not exist.',
    "[beyond] Compress responses over 1 KB.",
    "[beyond] Version the API under /v1.",
    '[asked] "An empty title is refused with a message": say which field is empty in the message.',
    "[beyond] Add a health route.",
]


def _consulted(tmp_path, role="backend"):
    asked: list[str] = []

    def gated(state, config, *, initial_request, output_key, **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {output_key: SpecialistAdvice(recommendations=TEN)}

    stack = TechnologyStack(language="Python", framework="FastAPI", frontend_framework="", database="SQLite",
                            testing_framework="pytest", product_kind="http_api", additional_tools=[])
    state = {
        "document": SimpleNamespace(text=BRIEF),
        "stack_selection": StackSelectorOutput(technology_stack=stack, rationale="As the brief asks."),
        "product_intake": {"product_name": "Notes"},
        "repository": RepositoryContext(root_path=str(tmp_path), branch="main", commit="abc", status="clean"),
        "consultation_roles": [role],
    }
    update = run_node("specialist_consultation", state, str(tmp_path), {"app.graph.workflow._run_gated_agent": gated})
    return update["specialist_advice"][role], asked[0]


def test_with_the_switch_on_a_small_brief_gets_three_items_the_brief_asks_for_first(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVICE_SIZED_TO_THE_BRIEF", "on")

    kept, asked = _consulted(tmp_path)

    assert kept == [TEN[1], TEN[3], TEN[5]]
    assert "give at most 3 recommendations" in asked
    assert "[asked]" in asked and "[beyond]" in asked


def test_with_the_switch_off_the_advice_is_as_before(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVICE_SIZED_TO_THE_BRIEF", "off")

    kept, asked = _consulted(tmp_path)

    assert kept == TEN
    assert "Advice sized to the brief" not in asked


def test_the_testing_adviser_keeps_one_item_a_criterion(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVICE_SIZED_TO_THE_BRIEF", "on")

    kept, _ = _consulted(tmp_path, role="testing")

    assert len(kept) == 10


def _decided(tmp_path, monkeypatch, line):
    monkeypatch.setenv("ADVICE_SIZED_TO_THE_BRIEF", "on")
    state = an_architect_state(tmp_path, document=SimpleNamespace(text=BRIEF),
                               specialist_advice={"backend": [TEN[0], TEN[1]]})
    update, asked, _ = an_architect(state, a_specification(
        specialist_advice_decisions=[line, "BE-2: adopted - api_and_event_contracts"]))
    return update["technical_specification"].specialist_advice_decisions, asked[0]


def test_an_item_beyond_the_brief_adopted_with_no_brief_line_quoted_is_declined(tmp_path, monkeypatch):
    decisions, asked = _decided(tmp_path, monkeypatch, "BE-1: adopted - reliability_and_observability")

    assert decisions[0].startswith("BE-1: declined")
    assert decisions[1] == "BE-2: adopted - api_and_event_contracts"
    assert "is declined unless the brief needs it" in asked


def test_one_adopted_with_the_brief_line_that_needs_it_quoted_stays(tmp_path, monkeypatch):
    line = 'BE-1: adopted - configuration - brief: "A user can list the notes, newest first"'

    decisions, _ = _decided(tmp_path, monkeypatch, line)

    assert decisions[0] == line


def test_the_new_rules_use_none_of_the_banned_words(monkeypatch):
    from app.agents.advice_sized import architect_rule, request_note

    monkeypatch.setenv("ADVICE_SIZED_TO_THE_BRIEF", "on")

    assert not BANNED.search(request_note("backend", BRIEF))
    assert not BANNED.search(architect_rule())
