"""A defect whose agent-loop fix changed no file goes to the harness's rewrite once before it is left open.

Measured over ten runs: the five costliest agent-loop fix stages (36-40 calls, 1.1-1.9M input tokens each) ended in a
surrender - no changed file, "we can't fix all" among the blockers - and the defect was left open for the next test
round. The rewrite (`rewritten_fixes.fix_by_rewriting`) was tried only before the agent loop (fast delivery) or after
a failed fix (candidates), never on a defect the loop gave up on. Behind `SURRENDER_TO_REWRITE` (off until measured).
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.agents.specialists import SpecialistOutput
from app.graph import surrender_to_rewrite, workflow


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


def _helper():
    source = inspect.getsource(workflow)
    return source[source.index("    def _fixed_by_rewriting("):source.index("    def _fix_one(")]


def test_the_fix_step_sends_a_surrender_to_the_rewrite_before_it_is_measured():
    source = inspect.getsource(workflow)
    fix_one = source[source.index("    def _fix_one("):source.index("    def defect_remediation_node(")]

    asked = fix_one.index("after_a_surrender(fix_result")
    assert fix_one.index('fix_result = update.pop("__fix_result__")') < asked < fix_one.index("engineering.after_a_fix(")
    assert "after_a_surrender=True" in fix_one


def test_the_rewrite_after_a_surrender_is_the_single_rewrite_in_any_delivery_mode():
    helper = _helper()

    assert "after_a_surrender: bool = False" in helper
    assert "not _fast_delivery() and not after_a_surrender" in helper, "the single rewrite is not fast delivery's alone"
    assert "and not after_a_surrender:" in helper[:helper.index("fix_by_candidates(")], "no second round of candidates"
