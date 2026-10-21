"""Each open question of the intake gets an assumed answer, recorded as a decision and given to the architect (plan IN.1).

Behind `ASSUMPTIONS_GATE`, off until measured: the architect read open
questions as prose and chose for itself, and nothing recorded the choice.
"""
from __future__ import annotations

import inspect
import os
import re
from types import SimpleNamespace
from unittest import mock

from app.agents import assumptions
from app.graph import workflow

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


def test_the_intake_and_the_architect_use_it():
    source = inspect.getsource(workflow)
    assert "assumptions.with_the_rule(request)" in source
    assert "assumptions.record(state, update)" in source
    assert "assumptions.block(state)" in source
