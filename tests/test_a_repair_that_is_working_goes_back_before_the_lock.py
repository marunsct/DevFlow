"""A repair of tests no product can pass that is working goes back again before the suite locks (LR.27).

Found in the launch review: after the one send-back at the limit, the suite locked with such findings standing, and
76 of 190 suites were reopened for them later, after a build and a test round, at 20-30 minutes each.
"""
from __future__ import annotations

import inspect

from app.graph import acceptance_nodes as nodes

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


def test_the_review_sends_it_back_and_the_count_is_cleared_at_the_lock():
    source = inspect.getsource(nodes.acceptance_review)
    assert source.index("cannot_pass_again(") < source.index("suite.lock(root)")
    assert "cannot_pass_sent" in nodes.ONCE_AT_THE_LIMIT


def test_a_release_re_measure_that_fails_is_a_gap_not_silence(tmp_path):
    from unittest import mock

    from app.acceptance import suite
    from app.graph import delivery

    with mock.patch.object(suite, "is_locked", side_effect=RuntimeError("index.lock")):
        gaps = delivery._measured_again_if_it_changed(tmp_path)
    assert gaps and gaps[0].startswith(delivery.CHANGED_AT_RELEASE) and "RuntimeError" in gaps[0]
