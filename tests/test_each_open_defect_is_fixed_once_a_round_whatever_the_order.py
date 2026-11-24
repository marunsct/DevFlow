"""One at a time, a fix round sends each open defect once, however the order of fixes changes during the round.

Measured on one run: the next defect was chosen by position - the one after the last worked - in an order read again
at each visit. A deploy mid-round and a defect raised again and regrouped each changed that order, and every defect
the new order put ahead of the position was never sent: ten defects of one round, the round's root cause among them,
were skipped and the round ended without them. A fix paused for approval must still go on with its own defect.
"""

from __future__ import annotations

import the_fix_stage


def _raised(description: str, found_in_round: int = 1):
    return the_fix_stage.a_defect(description, affected_files=[f"app/{len(description)}.py"],
                                  found_in_round=found_in_round)


def _one_round_with_two_criteria():
    """Five defects one test round raised: three of unit tests, then two failing acceptance criteria."""
    return [
        _raised("A unit test of the parser fails"),
        _raised("A unit test of the formatter fails"),
        _raised("A unit test of the cache fails"),
        _raised("[AC-1] Creating an entry returns 404"),
        _raised("[AC-2] Listing entries returns 404"),
    ]


def test_a_deploy_that_changes_the_order_mid_round_leaves_no_defect_unsent(monkeypatch, tmp_path):
    """The order rule itself changes after two fixes, as a deploy (here a switch read at each visit) changes it."""
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "off")

    def deployed_after_two(visits, defects):
        if visits == 2:
            monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")
        return defects

    sent = the_fix_stage.one_at_a_time(tmp_path, _one_round_with_two_criteria(), between=deployed_after_two)

    assert sent == ["defect_fix_2_0", "defect_fix_2_1", "defect_fix_2_3", "defect_fix_2_4", "defect_fix_2_2"]


def test_a_defect_raised_again_mid_round_is_still_sent_once(monkeypatch, tmp_path):
    """A defect carried over is raised again after two fixes, so it joins the latest round's group, ahead of them."""
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "off")
    ledger = [
        _raised("Signing in returns 500", found_in_round=0),
        _raised("Dates are not accepted", found_in_round=0),
        _raised("The router is mounted with a double prefix"),
        _raised("Creating an entry returns 404"),
        _raised("Updating an entry returns 404"),
    ]

    def raised_again_after_two(visits, defects):
        if visits == 2:
            return [defects[0].model_copy(update={"found_in_round": 1}), *defects[1:]]
        return defects

    sent = the_fix_stage.one_at_a_time(tmp_path, ledger, between=raised_again_after_two)

    assert sent == ["defect_fix_2_2", "defect_fix_2_3", "defect_fix_2_0", "defect_fix_2_4", "defect_fix_2_1"]


def test_a_fix_paused_for_approval_goes_on_with_its_own_defect_when_the_order_changed(monkeypatch, tmp_path):
    """Three fixes done and the fourth paused; while it waits, the order puts that defect first."""
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")
    ledger = [*_one_round_with_two_criteria()[:3], _raised("[AC-1] Creating an entry returns 404"),
              _raised("Styles are missing")]
    state = the_fix_stage.a_state(
        tmp_path, *ledger, defect_cursor=3,
        fixes_tried=["defect_fix_2_0", "defect_fix_2_1", "defect_fix_2_2", "defect_fix_2_3"],
        pending_inner_thread_id="t:defect_fix_2_3:0123abcd", fix_base_commit="base",
    )

    _, seen = the_fix_stage.run(tmp_path, state, during=lambda stage: stage)

    assert seen.during == ["defect_fix_2_3"]
