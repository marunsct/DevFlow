"""A test the harness finds can never pass goes back once at the review's round limit instead of being locked.

Measured on one run: at the limit, the suite locked with tests asking the whole page for "Done", "Edit" and
"Delete" while the brief gives one to each record; found again only after a build and a test round, the suite went
back to its writers then.
"""
import re

from app.acceptance import suite
from app.graph import acceptance_nodes as nodes
from the_acceptance_review import FAILED, NO_PRODUCT_CAN_PASS, a_service_suite, measured, reviewed

CANNOT = ['`todo/acceptance/a.spec.js` line(s) 85 ask the whole page for "Done", and the brief gives one to each record']


def test_at_the_limit_cannot_pass_findings_go_back_once():
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=3, limit=3) == [nodes.REPAIR_ONLY, *CANNOT]
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=4, limit=3) == [nodes.REPAIR_ONLY, *CANNOT], "past the limit, never reached by an exact comparison, still once"
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=4, limit=3, already_sent=True) == []
    assert nodes.cannot_pass_to_lock(CANNOT, rounds=2, limit=3) == []
    assert nodes.cannot_pass_to_lock([], rounds=3, limit=3) == []


def test_the_review_at_its_limit_sends_the_suite_back_instead_of_locking_it(tmp_path):
    root = a_service_suite(tmp_path, NO_PRODUCT_CAN_PASS)

    update, _ = reviewed(root, measured(FAILED), rounds=nodes.MAX_ACCEPTANCE_ROUNDS)

    assert update["stage"] == "acceptance_author"
    assert update["acceptance_feedback"][0].startswith("Repair only the tests named below")
    assert any("response.status()" in item for item in update["acceptance_feedback"][1:])
    assert not suite.is_locked(root)


def test_the_note_avoids_the_banned_words():
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", nodes.REPAIR_ONLY, re.I)
