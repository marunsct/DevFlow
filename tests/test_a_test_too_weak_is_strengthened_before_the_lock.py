"""At the review's round limit, a finding that a test is too weak goes back once more instead of locking open.

Over 21 release-candidate runs the review left 30 problems open at the lock; 13 said a test only checked a status
or never verified what the product returns, and one such gap shipped a false acceptance (an update that emptied a
title was accepted; no test asked it). Other findings keep the limit.
"""
from app.acceptance import suite
from app.graph import acceptance_nodes
from the_acceptance_review import A_FAIR_TEST, PASSED, a_service_suite, measured, qa_lead, reviewed

WEAK = "AC-10: test_ac10_get_note_not_found only asserts status code 404; it does not assert the response body."
NEVER = "AC-9: The test does not verify that GET /notes returns an empty array when no notes exist."
OTHER = "AC-15: start.sh should be named in the README as the way to start the service."


def test_weak_tests_go_back_once_at_the_limit():
    assert acceptance_nodes.too_weak_to_lock([WEAK, NEVER, OTHER], rounds=2, limit=2) == [WEAK, NEVER]


def test_nothing_goes_back_twice_or_before_the_limit():
    assert acceptance_nodes.too_weak_to_lock([WEAK], rounds=3, limit=2, already_sent=True) == []
    assert acceptance_nodes.too_weak_to_lock([WEAK], rounds=1, limit=2) == []
    assert acceptance_nodes.too_weak_to_lock([OTHER], rounds=2, limit=2) == []


def test_the_review_at_its_limit_sends_a_weak_test_back_and_keeps_other_findings_open(tmp_path):
    root = a_service_suite(tmp_path, A_FAIR_TEST)

    update, _ = reviewed(root, measured(PASSED), rounds=acceptance_nodes.MAX_ACCEPTANCE_ROUNDS,
                         review=qa_lead(False, WEAK, OTHER))

    assert update["stage"] == "acceptance_author"
    assert update["acceptance_feedback"][0].startswith("Strengthen only the tests named below")
    assert update["acceptance_feedback"][1:] == [WEAK]
    assert not suite.is_locked(root)


def test_the_note_uses_none_of_the_banned_words():
    import re

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", acceptance_nodes.STRENGTHEN_ONLY, re.I)


NAMED = ("`bookmarks/acceptance/e2e/ui.spec.ts` finds a control by something no person sees on line(s) 130 "
         "(`await page.locator('#filter-by-tag').fill(\"work\");`). Find each by the label the brief gives it.")
NO_NAME = 'The brief names these controls and no test finds any of them by that name: "Filter by tag".'


def test_a_suite_past_the_limit_is_sent_back_once_for_a_control_found_by_no_name():
    """Measured on one run: five passes that could not run took the suite past the review's limit, it was never sent
    back, locked with both findings open, and a hidden test finding the field by its label failed."""
    sent = acceptance_nodes.too_weak_to_lock([NAMED, NO_NAME, OTHER], rounds=5, limit=3)
    assert sent == [NAMED, NO_NAME]
    assert acceptance_nodes.too_weak_to_lock([NAMED], rounds=5, limit=3, already_sent=True) == []
    assert acceptance_nodes.too_weak_to_lock([NAMED], rounds=2, limit=3) == []
