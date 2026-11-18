"""The intake asks a few questions that change behaviour, answers them with the brief's words, and says what it assumed.

Deep review 2026-11-18, item C8: an earlier audit traced all four false acceptances it found to an intake or a
specification that overrode the brief, and the intake answered every open question with "the simplest answer that
meets the brief" - an answer the brief never gave - up to twelve of them. With `INTAKE_ASKS_FIRST` on: at most five
questions, each one whose answer would change what the product does, each answered by the brief's own words with
nothing added; a run a person answers waits at the intake review; every assumption is a note in the release.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app import completion_verdict
from app.agents import assumptions

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_intake_is_asked_for_few_questions_that_change_behaviour_answered_by_the_brief(monkeypatch):
    monkeypatch.setenv("INTAKE_ASKS_FIRST", "on")
    request = {"messages": [{"role": "user", "content": "Read the brief."}]}

    asked = assumptions.with_the_rule(request)["messages"][-1]["content"]

    assert "at most 5 open questions" in asked
    assert "would change what the product does" in asked
    assert "the brief's own words" in asked and "adding nothing" in asked
    assert "simplest" not in asked
    assert not BANNED.search(asked) and not BANNED.search(assumptions.LITERAL)


def test_at_most_five_are_kept_and_one_with_no_answer_is_the_brief_s_words(monkeypatch):
    monkeypatch.setenv("INTAKE_ASKS_FIRST", "on")

    pairs = assumptions.assumed([f"Question {n}? -> assumed: as stated" for n in range(7)] + ["Is it paged?"])

    assert len(pairs) == 5
    assert assumptions.assumed(["Is it paged?"]) == [("Is it paged?", "As the brief states it; nothing added.")]


def test_an_answer_a_person_changed_at_the_review_is_the_one_built_to(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_ASKS_FIRST", "on")
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}
    first = {"product_intake": SimpleNamespace(open_questions=["Paged lists? -> assumed: as the brief states it"])}
    assumptions.record(state, first)
    revised = {"decisions": first["decisions"],
               "product_intake": SimpleNamespace(open_questions=["Paged lists? -> assumed: 20 a page"])}

    assumptions.record({**state, "decisions": first["decisions"]}, revised)

    assert "- Paged lists? -> 20 a page" in assumptions.block({**state, **revised})


def test_a_run_a_person_answers_waits_at_the_intake_review_and_an_unattended_one_does_not(monkeypatch):
    monkeypatch.setenv("INTAKE_ASKS_FIRST", "on")
    questions = ["Paged lists? -> assumed: as the brief states it"]

    assert assumptions.waits_for_answers(questions, person_answers=True) is True
    assert assumptions.waits_for_answers(questions, person_answers=False) is False
    assert assumptions.waits_for_answers([], person_answers=True) is False


def test_the_intake_hands_on_to_its_review_when_a_person_answers(tmp_path, monkeypatch):
    from app.agents.product_manager import ProductManagerOutput
    from workflow_node_stubs import run_node

    monkeypatch.setenv("INTAKE_ASKS_FIRST", "on")
    intake = ProductManagerOutput(product_name="Notes", open_questions=["Paged lists? -> assumed: as stated"])

    seen = run_node(monkeypatch, tmp_path, "product_manager", answer=intake,
                    document=SimpleNamespace(text="Notes.", source_path="brief.md", source_type="markdown",
                                             truncated=False),
                    overrides={"app.agents.assumptions.a_person_answers": lambda run_id: True})

    assert seen.update["stage"] == "user_review_product_intake"


def test_each_assumption_is_a_note_for_the_release_s_reader_not_a_gap(monkeypatch):
    monkeypatch.setenv("INTAKE_ASKS_FIRST", "on")
    state = {"decisions": [{"point": "product_intake", "question": "Paged lists?", "decision": "20 a page",
                            "rationale": f"{assumptions.MARK}: the brief does not say."}]}

    notes = assumptions.at_release(state)

    assert notes == ["Assumed at intake where the brief does not say: Paged lists? -> 20 a page"]
    assert completion_verdict.split(notes) == ([], notes)
