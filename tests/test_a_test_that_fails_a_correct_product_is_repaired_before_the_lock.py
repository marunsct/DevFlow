"""A suite is not locked with a finding that one of its tests fails on a correct product (LF.1442).

Measured on a fast run (deep review 2026-11-25, decisions finding 3): the suite locked "after 3 round(s) with these
still open", among them the QA lead's blocking finding that the tag filter test leaves a record behind, so the invalid
JSON test fails "even though the product correctly rejected invalid input". Fix rounds ran against it for 88 minutes,
then the harness's own check reached the same conclusion and reopened the suite; the repair took two more hours. The
findings and severities are the QA lead's real answer at that lock.
"""
from __future__ import annotations

from app.graph import suite_gate
from app.graph.acceptance_nodes import REPAIR_ONLY

AT_THE_LOCK = {
    "AC-11 (tag filter test): The test at api.spec.js:64 creates two bookmarks (tagged and untagged) but only deletes "
    "the tagged one on line 76. The untagged bookmark remains in the store, which causes the later AC-12 invalid JSON "
    "test (api.spec.js:159) to fail its assertion that the entire list is empty — even though the product "
    "correctly rejected invalid input. The tag filter test must also delete its untagged bookmark.": "blocking",
    "AC-12 (invalid JSON test): The test at api.spec.js:159 asserts `expect(list).toEqual([])`, requiring the entire "
    "bookmark list to be empty. This is fragile because any prior test that left data (as the tag filter test does, "
    "see above) would cause this test to fail regardless of whether the product correctly handled the invalid JSON. "
    "The assertion should check only that no bookmark with URL matching the failed request exists, consistent with "
    "all other AC-12 validation tests.": "major",
    "AC-12 error messages not verified: Several AC-12 tests check `expect(body).toHaveProperty('error')` but do not "
    "verify the exact error message (e.g., 'Title is required', 'URL must start with http:// or https://', 'Invalid "
    "JSON'). The brief's interface contract specifies these exact messages. Tests should assert the exact message to "
    "ensure the product returns the correct human-readable errors.": "minor",
}


def test_the_tests_that_fail_on_a_correct_product_go_back_for_one_repair(tmp_path):
    findings = list(AT_THE_LOCK)

    feedback = suite_gate.repair_before_the_lock(tmp_path, findings, dict(AT_THE_LOCK))

    assert feedback[0] == REPAIR_ONLY
    assert feedback[1:] == findings[:2]


def test_the_repair_is_made_once_and_the_suite_then_locks_as_before(tmp_path):
    findings = list(AT_THE_LOCK)
    suite_gate.repair_before_the_lock(tmp_path, findings, dict(AT_THE_LOCK))

    assert suite_gate.repair_before_the_lock(tmp_path, findings, dict(AT_THE_LOCK)) == []


def test_findings_that_only_ask_for_closer_checks_lock_as_before(tmp_path):
    minor = [finding for finding, severity in AT_THE_LOCK.items() if severity == "minor"]

    assert suite_gate.repair_before_the_lock(tmp_path, minor, dict(AT_THE_LOCK)) == []
