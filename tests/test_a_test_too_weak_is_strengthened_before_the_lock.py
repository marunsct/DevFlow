"""At the review's round limit, a finding that a test is too weak goes back once more instead of locking open.

Over 21 release-candidate runs the review left 30 problems open at the lock; 13 said a test only checked a status
or never verified what the product returns, and one such gap shipped a false acceptance (an update that emptied a
title was accepted; no test asked it). Other findings keep the limit.
"""
from app.graph import acceptance_nodes

WEAK = "AC-10: test_ac10_get_note_not_found only asserts status code 404; it does not assert the response body."
NEVER = "AC-9: The test does not verify that GET /notes returns an empty array when no notes exist."
OTHER = "AC-15: start.sh should be named in the README as the way to start the service."


def test_weak_tests_go_back_once_at_the_limit():
    assert acceptance_nodes.too_weak_to_lock([WEAK, NEVER, OTHER], rounds=2, limit=2) == [WEAK, NEVER]


def test_nothing_goes_back_twice_or_before_the_limit():
    assert acceptance_nodes.too_weak_to_lock([WEAK], rounds=3, limit=2) == []
    assert acceptance_nodes.too_weak_to_lock([WEAK], rounds=1, limit=2) == []
    assert acceptance_nodes.too_weak_to_lock([OTHER], rounds=2, limit=2) == []


def test_the_review_step_asks_it_at_the_limit():
    import inspect

    source = inspect.getsource(acceptance_nodes)
    assert "too_weak_to_lock(" in source.split("def too_weak_to_lock", 1)[0] + source.split("def too_weak_to_lock", 1)[1].split("\ndef ", 1)[1]


def test_the_note_uses_none_of_the_banned_words():
    import re

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", acceptance_nodes.STRENGTHEN_ONLY, re.I)
