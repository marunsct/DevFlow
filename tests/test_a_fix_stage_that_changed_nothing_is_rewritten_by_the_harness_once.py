"""A defect whose agent-loop fix changed no file goes to the harness's rewrite once before it is left open.

Measured over ten runs: the five costliest agent-loop fix stages (36-40 calls, 1.1-1.9M input tokens each) ended in a
surrender - no changed file, "we can't fix all" among the blockers - and the defect was left open for the next test
round. The rewrite (`rewritten_fixes.fix_by_rewriting`) was tried only before the agent loop (fast delivery) or after
a failed fix (candidates), never on a defect the loop gave up on. Behind `SURRENDER_TO_REWRITE` (off until measured).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import the_fix_stage
from the_fix_stage import a_defect, a_state

from app.agents.specialists import SpecialistOutput
from app.graph import surrender_to_rewrite


SURRENDER = SpecialistOutput(blockers=["we can't fix all of these"])
REWRITTEN = SpecialistOutput(changed_files=["src/store.py"], decisions=["Rewrote src/store.py"])


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SURRENDER_TO_REWRITE", "on")


def test_an_answer_with_no_changed_file_is_replaced_by_the_rewrite_s():
    asked = []

    def rewrite():
        asked.append(1)
        return REWRITTEN

    assert surrender_to_rewrite.after_a_surrender(SURRENDER, rewrite) is REWRITTEN
    assert asked == [1], "asked once"


def test_an_answer_that_changed_a_file_is_left_alone():
    kept = SpecialistOutput(changed_files=["src/a.py"])

    def rewrite():
        raise AssertionError("not asked")

    assert surrender_to_rewrite.after_a_surrender(kept, rewrite) is kept


def test_a_rewrite_that_wrote_nothing_or_failed_leaves_the_defect_with_the_loop_s_answer():
    assert surrender_to_rewrite.after_a_surrender(SURRENDER, lambda: None) is SURRENDER
    assert surrender_to_rewrite.after_a_surrender(SURRENDER, lambda: SpecialistOutput()) is SURRENDER

    def broken():
        raise RuntimeError("the model server is down")

    assert surrender_to_rewrite.after_a_surrender(SURRENDER, broken) is SURRENDER


def test_off_a_surrender_stands_and_the_rewrite_is_not_asked(monkeypatch):
    monkeypatch.setenv("SURRENDER_TO_REWRITE", "off")

    def rewrite():
        raise AssertionError("not asked")

    assert surrender_to_rewrite.after_a_surrender(SURRENDER, rewrite) is SURRENDER


def test_what_a_surrender_is():
    assert surrender_to_rewrite.surrendered(SURRENDER)
    assert surrender_to_rewrite.surrendered(SimpleNamespace(changed_files=[]))
    assert not surrender_to_rewrite.surrendered(REWRITTEN)


def test_the_fix_step_sends_a_surrender_to_the_rewrite_before_it_is_measured(tmp_path):
    """The agent loop's answer that changed no file goes to the rewrite, and what is measured and settled is the
    rewrite's - in thorough delivery too, where a rewrite is otherwise never asked."""
    _, seen = the_fix_stage.run(tmp_path, a_state(tmp_path), answer=SURRENDER, rewrite=REWRITTEN)

    assert seen.events == ["agent", "agent loop", "rewrite", "measured"]
    assert seen.settled == [REWRITTEN]


def test_the_rewrite_after_a_surrender_is_the_single_rewrite_in_any_delivery_mode(tmp_path):
    """After a failed fix the candidates come first; a surrender after them gets one rewrite, not a second round."""
    failed_once = a_state(tmp_path, a_defect(fix_attempts=1))

    _, seen = the_fix_stage.run(tmp_path, failed_once, answer=SURRENDER, rewrite=REWRITTEN,
                                   candidate_model=SimpleNamespace(name="candidates"), candidate=None)

    assert seen.events == ["candidates", "agent", "agent loop", "rewrite", "measured"]
    assert seen.settled == [REWRITTEN]
