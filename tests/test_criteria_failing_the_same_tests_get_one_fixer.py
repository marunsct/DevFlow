"""Criteria whose failing tests are exactly the same set are one defect and one fixer.

Measured on one run: "[AC-16] The JSON interface behaves as described" and "[AC-17] Invalid bookmarks are refused"
were carried by one and the same failing test; two fixers worked it one after the other, about 40 and 45 minutes,
and both were left open.
"""
from types import SimpleNamespace

from app.graph import workflow


def _defect(cid, text):
    return SimpleNamespace(
        description=f"[{cid}] {text} - the acceptance suite says this does not work yet.",
        expected_behavior=text, actual_behavior=f"{cid} fails", severity="major", owner="backend",
        reproduction_steps="run the suite", affected_files=[],
    )


RESULT = {"criteria": {
    "AC-16": {"tests": [{"name": "[AC-16][AC-17] JSON API returns correct status codes", "outcome": "failed"}]},
    "AC-17": {"tests": [{"name": "[AC-16][AC-17] JSON API returns correct status codes", "outcome": "failed"}]},
    "AC-15": {"tests": [{"name": "[AC-15] save, list, filter and delete", "outcome": "failed"},
                        {"name": "[AC-16][AC-17] JSON API returns correct status codes", "outcome": "failed"}]},
}}


def test_two_criteria_on_the_same_failing_tests_become_one():
    reported = [_defect("AC-16", "The JSON interface behaves as described"),
                _defect("AC-17", "Invalid bookmarks are refused"),
                _defect("AC-15", "Bookmarks can be saved, listed, filtered and deleted from the page")]

    merged = workflow._one_defect_per_failing_tests(reported, RESULT)

    assert len(merged) == 2
    assert merged[0].description.startswith("[AC-16][AC-17] ")
    assert "Invalid bookmarks are refused" in merged[0].expected_behavior
    assert merged[1].description.startswith("[AC-15] ")


def test_nothing_is_merged_without_a_result():
    reported = [_defect("AC-16", "a"), _defect("AC-17", "b")]
    assert workflow._one_defect_per_failing_tests(reported, {}) == reported
