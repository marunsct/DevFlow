"""One decision ends a sprint's attempt, from one measurement, in one order (LR.26).

Four fixes in one day changed the end of an attempt: the settle rule read the measurement before the best attempt
came back, then again after it, the stall rule read a third, and the settle rule wanted the whole suite green, so a
sprint whose only failing tests waited on later sprints never settled.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from app.graph import best_attempt, end_of_attempt, settle_when_green, stalled_sprint

UNIT = SimpleNamespace(status="open", caught_by="npm test", source="", failing_criteria=[], description="unit: t1 fails")


def _decide(*, put_back="", settles=False, stalls=False, history=(3, 3, 3)):
    with mock.patch.object(best_attempt, "restore_if_worse", return_value=put_back), \
            mock.patch.object(settle_when_green, "open_after_the_put_back", side_effect=lambda root, d: list(d)), \
            mock.patch.object(settle_when_green, "applies", return_value=settles), \
            mock.patch.object(stalled_sprint, "record", return_value=list(history)), \
            mock.patch.object(stalled_sprint, "stalled", return_value=stalls):
        decision = end_of_attempt.decide("/w", [UNIT], replans=1, best_history=[3, 3])
    return decision


def test_the_best_is_put_back_first_and_the_decision_reads_after_it():
    """The margin of one test is held through `decide` on a real product: see
    `test_the_end_of_an_attempt_puts_back_a_product_one_test_worse_than_its_best`."""
    decision = _decide(put_back="2 file(s) were put back", settles=True)
    assert decision.outcome == end_of_attempt.SETTLE and "best attempt put back" in decision.why


def test_settle_comes_before_stall_and_stall_before_replan():
    assert _decide(settles=True, stalls=True).outcome == end_of_attempt.SETTLE
    assert _decide(stalls=True).outcome == end_of_attempt.STOP
    plan_again = _decide()
    assert plan_again.outcome == end_of_attempt.REPLAN and plan_again.best_history == [3, 3, 3]


def test_a_suite_failing_only_later_sprints_tests_can_settle(tmp_path, monkeypatch):
    from app.acceptance import suite

    monkeypatch.setattr(settle_when_green, "enabled", lambda: True)
    monkeypatch.setattr(suite, "last_result", lambda root: {"ran": True, "passed": 9, "failed": 4})
    monkeypatch.setattr(suite, "_command", lambda root: (["npx", "playwright", "test"], "r.xml", "."))
    monkeypatch.setattr(settle_when_green, "the_locked_suite_is_green_for_this_sprint", lambda root: True)
    assert settle_when_green.applies(tmp_path, [UNIT], replans=settle_when_green.AFTER_REPLANS)
    monkeypatch.setattr(settle_when_green, "the_locked_suite_is_green_for_this_sprint", lambda root: False)
    assert not settle_when_green.applies(tmp_path, [UNIT], replans=settle_when_green.AFTER_REPLANS)
