"""Each open question of the intake gets an assumed answer, recorded as a decision and given to the architect (plan IN.1).

Behind `ASSUMPTIONS_GATE`, off until measured: the architect read open
questions as prose and chose for itself, and nothing recorded the choice.
"""
from __future__ import annotations

import os
import re
from types import SimpleNamespace
from unittest import mock

from app.agents import assumptions

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"ASSUMPTIONS_GATE": "on"}


def test_the_rule_names_no_banned_word_and_is_asked_only_when_on():
    assert not BANNED.search(assumptions.RULE) and not BANNED.search(assumptions.SIMPLEST)
    request = {"messages": [{"role": "user", "content": "Read the brief."}]}
    with mock.patch.dict(os.environ, {"ASSUMPTIONS_GATE": ""}):
        assert assumptions.with_the_rule(request)["messages"][-1]["content"] == "Read the brief."
    with mock.patch.dict(os.environ, ON):
        assert assumptions.with_the_rule(request)["messages"][-1]["content"].endswith(assumptions.RULE)


def test_each_question_is_split_from_its_answer_and_one_with_none_gets_the_simplest():
    assert assumptions.assumed([
        "Do notes need an owner? -> assumed: no, one shared list",
        "Is search full text?",
        "",
    ]) == [("Do notes need an owner?", "no, one shared list"), ("Is search full text?", assumptions.SIMPLEST)]


def test_on_they_are_recorded_as_decisions_and_reach_the_architect(tmp_path):
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    update = {"product_intake": SimpleNamespace(open_questions=["Paged lists? -> assumed: 20 per page"])}
    with mock.patch.dict(os.environ, ON):
        assumptions.record(state, update)
        block = assumptions.block({**state, **update})

    record = update["decisions"][-1]
    assert record["point"] == "product_intake" and record["decision"] == "20 per page"
    assert "Paged lists?" in (tmp_path / "docs" / "decision_log.md").read_text()
    assert "- Paged lists? -> 20 per page" in block and not BANNED.search(block)
    with mock.patch.dict(os.environ, {"ASSUMPTIONS_GATE": ""}):
        assert assumptions.block({**state, **update}) == ""


def _marked(monkeypatch):
    """The rule, the record and the block replaced by markers, so a stage shows which it was given."""
    recorded = []

    def with_the_rule(request):
        request["messages"][-1]["content"] += "\n[the rule]"
        return request

    monkeypatch.setattr(assumptions, "with_the_rule", with_the_rule)
    monkeypatch.setattr(assumptions, "record", lambda state, update: recorded.append(update.get("product_intake")))
    monkeypatch.setattr(assumptions, "block", lambda state: "\n[the assumed answers]")
    return recorded


def test_the_intake_asks_by_the_rule_and_records_its_answers(tmp_path, monkeypatch):
    from app.agents.product_manager import ProductManagerOutput
    from workflow_node_stubs import run_node

    recorded = _marked(monkeypatch)
    intake = ProductManagerOutput(product_name="Notes", open_questions=["Paged lists? -> assumed: 20 per page"])

    seen = run_node(monkeypatch, tmp_path, "product_manager", answer=intake,
                    document=SimpleNamespace(text="Notes.", source_path="brief.md", source_type="markdown", truncated=False))

    (stage, request), = seen.requests
    assert stage == "product_manager" and request["messages"][-1]["content"].endswith("[the rule]")
    assert [i.open_questions for i in recorded] == [["Paged lists? -> assumed: 20 per page"]]


def test_the_architect_is_given_the_assumed_answers(tmp_path, monkeypatch):
    from app.agents.product_manager import ProductManagerOutput
    from workflow_node_stubs import run_node

    _marked(monkeypatch)

    seen = run_node(monkeypatch, tmp_path, "principal_architect", answer=None,
                    product_intake=ProductManagerOutput(product_name="Notes"), tools_models={"plan": "local"},
                    document=SimpleNamespace(text="Notes."),
                    overrides={"app.agents.research_brief.research_notes": lambda *a, **k: ""})

    (stage, request), = seen.requests
    assert stage == "principal_architect" and "[the assumed answers]" in request["messages"][-1]["content"]
