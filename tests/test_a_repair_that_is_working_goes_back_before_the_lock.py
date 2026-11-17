"""A repair of tests no product can pass that is working goes back again before the suite locks (LR.27).

Found in the launch review: after the one send-back at the limit, the suite locked with such findings standing, and
76 of 190 suites were reopened for them later, after a build and a test round, at 20-30 minutes each.
"""
from __future__ import annotations

from app.acceptance import suite
from app.graph import acceptance_nodes as nodes
from the_acceptance_review import (
    A_FAIR_TEST, FAILED, NO_PRODUCT_CAN_PASS, PASSED, a_service_suite, measured, reviewed, saved_state,
)

CANNOT = ["`[AC-2] lists` looks for a control on the whole page that each record has"]


def test_fewer_than_last_time_goes_back_within_the_extra_rounds():
    limit = nodes.MAX_ACCEPTANCE_ROUNDS
    assert nodes.cannot_pass_again(CANNOT, rounds=limit, limit=limit, last_sent=3) == [nodes.REPAIR_ONLY, *CANNOT]
    assert nodes.cannot_pass_again(CANNOT, rounds=limit + nodes.CANNOT_PASS_EXTRA_ROUNDS, limit=limit, last_sent=3) == []


def test_no_progress_or_no_earlier_send_locks_as_before():
    limit = nodes.MAX_ACCEPTANCE_ROUNDS
    assert nodes.cannot_pass_again(CANNOT, rounds=limit, limit=limit, last_sent=1) == []
    assert nodes.cannot_pass_again(CANNOT, rounds=limit, limit=limit, last_sent=None) == []
    assert nodes.cannot_pass_again([], rounds=limit, limit=limit, last_sent=3) == []


def test_the_review_sends_back_a_repair_that_left_fewer_than_last_time(tmp_path):
    root = a_service_suite(tmp_path, NO_PRODUCT_CAN_PASS)

    update, _ = reviewed(root, measured(FAILED), rounds=nodes.MAX_ACCEPTANCE_ROUNDS + 1,
                         saved={"cannot_pass_repaired_once": True, "cannot_pass_sent": 3})

    assert update["stage"] == "acceptance_author"
    assert update["acceptance_feedback"][0].startswith("Repair only the tests named below")
    assert not suite.is_locked(root)


def test_the_count_sent_last_time_is_forgotten_when_the_suite_locks(tmp_path):
    """A suite reopened after the lock starts its send-backs afresh, not measured against an earlier lock's count."""
    root = a_service_suite(tmp_path, A_FAIR_TEST)

    reviewed(root, measured(PASSED), saved={"cannot_pass_repaired_once": True, "cannot_pass_sent": 3})

    assert suite.is_locked(root)
    assert "cannot_pass_sent" not in saved_state(root)


def test_a_release_re_measure_that_fails_is_a_gap_not_silence(tmp_path):
    from unittest import mock

    from app.acceptance import suite
    from app.graph import delivery

    with mock.patch.object(suite, "is_locked", side_effect=RuntimeError("index.lock")):
        gaps = delivery._measured_again_if_it_changed(tmp_path)
    assert gaps and gaps[0].startswith(delivery.CHANGED_AT_RELEASE) and "RuntimeError" in gaps[0]
