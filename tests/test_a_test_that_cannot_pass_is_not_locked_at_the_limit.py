"""A test the harness finds can never pass goes back once at the review's round limit instead of being locked.

Measured on one run: at the limit, the suite locked with tests asking the whole page for "Done", "Edit" and
"Delete" while the brief gives one to each record; found again only after a build and a test round, the suite went
back to its writers then.
"""
import inspect
import re

from app.graph import acceptance_nodes as nodes

CANNOT = ['`todo/acceptance/a.spec.js` line(s) 85 ask the whole page for "Done", and the brief gives one to each record']


def test_at_the_limit_cannot_pass_findings_go_back_once():
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=3, limit=3) == [nodes.REPAIR_ONLY, *CANNOT]
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=4, limit=3) == [nodes.REPAIR_ONLY, *CANNOT], "past the limit, never reached by an exact comparison, still once"
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=4, limit=3, already_sent=True) == []
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=2, limit=3) == []
    assert nodes.cannot_pass_to_lock([], rounds=3, limit=3) == []


def test_the_review_uses_it_before_locking():
    source = inspect.getsource(nodes.acceptance_review)
    assert "cannot_pass_to_lock(" in source
    assert source.index("cannot_pass_to_lock(") < source.index("suite.lock(root)")


def test_the_note_avoids_the_banned_words():
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", nodes.REPAIR_ONLY, re.I)


def test_the_partial_output_send_back_also_reaches_a_suite_past_the_limit_once():
    """The same exact comparison kept a suite whose rounds ran past the limit from being sent back, here and in the
    weak-test and cannot-pass sends (one run locked a control found by no name and lost a hidden test)."""
    import inspect

    source = inspect.getsource(nodes.acceptance_review)
    assert "rounds >= MAX_ACCEPTANCE_ROUNDS and not sent_back.get(\"partial_strengthened_once\")" in source
    assert "rounds == MAX_ACCEPTANCE_ROUNDS" not in source
