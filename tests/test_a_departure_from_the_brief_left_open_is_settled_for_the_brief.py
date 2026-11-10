"""At an escalation, an open finding that the specification departs from the brief is settled, and the brief stands.

Audit item 4 of the per-role audit. Measured: a design review ended with one major finding open - the specification
departed from the output the brief stated - and the one call that settles open findings ruled only on contradictions
inside the specification. Nothing settled it, every later stage read the specification's version, and the hidden test
of that output was lost.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.agents import specification_rulings
from app.agents.shared_facts import the_facts_section
from app.graph import escalation

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = "Print each word and its count, one per line, as `word: count`, sorted by count."
SPEC_SAYS = "The tool prints a JSON array of objects with word and count fields"
BRIEF_SAYS = "one per line, as `word: count`"
FINDING = "[major] The output format departs from the brief's stated one-per-line form"


class Specification(BaseModel):
    acceptance_criteria: list[str] = [f"{SPEC_SAYS}, sorted by count"]


class Model:
    def __init__(self, reply: str):
        self.reply, self.asked = reply, []

    def invoke(self, messages, **kwargs):
        self.asked.append(messages[-1].content)
        return SimpleNamespace(content=self.reply)


def _reply(first=SPEC_SAYS, second=BRIEF_SAYS, stands="second", why="The brief states the output form."):
    return json.dumps({"rulings": [{"finding": 1, "first_statement": first, "second_statement": second,
                                    "stands": stands, "why": why}]})


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("SETTLE_SPEC_CONTRADICTIONS", "on")
    monkeypatch.delenv("SHARED_FACTS", raising=False)


def _decide(tmp_path, model):
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "document": SimpleNamespace(text=BRIEF),
        "technical_specification": Specification(),
        "escalation": {"kind": "design", "findings": [FINDING], "error": "Still asks for changes."},
    }
    return escalation.escalation(state, {}, SimpleNamespace(judgement_model=model))


def _departures(update):
    return [d for d in update["decisions"] if "departs from what the brief states" in d["question"]]


@pytest.mark.parametrize("stands", ["second", "first"])
def test_the_brief_s_words_stand_whatever_the_ruling_says(tmp_path, on, stands):
    update = _decide(tmp_path, Model(_reply(stands=stands)))
    [recorded] = _departures(update)
    assert recorded["decision"] == BRIEF_SAYS and recorded["decided_by"] == "auto"
    assert any(line.startswith("Design review finding settled by DR-") and FINDING in line for line in update["known_issues"])
    section = the_facts_section(tmp_path, built=False)
    assert f"the brief's \"{BRIEF_SAYS}\" stands, over the specification's \"{SPEC_SAYS}\"" in section
    assert "Build and test to the brief's words." in section


@pytest.mark.parametrize("second", [
    "one line per word, as word then count",  # in neither the specification nor the brief
    "count",  # too short to be a statement
])
def test_a_quote_the_brief_does_not_hold_is_rejected(tmp_path, on, second):
    update = _decide(tmp_path, Model(_reply(second=second)))
    assert _departures(update) == []
    assert f"Design review left open: {FINDING}" in update["known_issues"]


def test_the_specification_s_side_must_be_the_specification_s(tmp_path, on):
    update = _decide(tmp_path, Model(_reply(first="The tool prints whatever it likes")))
    assert _departures(update) == []


def test_the_call_is_asked_to_settle_departures_in_plain_words():
    asked = specification_rulings.the_request(["F"], "S", "B")
    assert "departs from something the brief states" in asked and "The brief's words stand." in asked
    assert not BANNED.search(asked)
