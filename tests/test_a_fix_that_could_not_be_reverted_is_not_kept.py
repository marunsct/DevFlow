"""A fix that broke tests is never committed as clean when its revert fails.

Found in a code review: when `ci.revert_to` failed (git refused, timed out, or found a lock), the fix that broke
tests fell through, was committed as "Fix: ..." and its measurement saved as the new baseline, so later regression
checks no longer saw the tests it broke.
"""
from __future__ import annotations

from unittest import mock

from app import ci
from app.graph import engineering


class _Snap:
    def __init__(self, passing):
        self._passing = set(passing)
        self.problem = ""
        self.unit = {}
        self.commit = "c0"

    def passing(self):
        return set(self._passing)


def _measure(revert_results):
    before, after = _Snap({"acceptance: a", "acceptance: b"}), _Snap({"acceptance: a"})
    with mock.patch.object(engineering, "ci_applies", return_value=True), \
            mock.patch.object(ci, "load", return_value=before), \
            mock.patch.object(ci, "take", return_value=after), \
            mock.patch.object(ci, "regressions", return_value=["acceptance: b"]), \
            mock.patch.object(engineering, "_broken_tests", return_value=["acceptance: b"]), \
            mock.patch.object(engineering, "what_the_fix_did_to_the_install", return_value=""), \
            mock.patch.object(engineering, "_its_tests_without_its_product_change", return_value=None), \
            mock.patch.object(ci, "revert_to", side_effect=revert_results) as revert, \
            mock.patch.object(ci, "commit") as commit, mock.patch.object(ci, "save") as save:
        broken = engineering.after_a_fix("/w", "base", "defect_fix_1", "a fix")
    return broken, revert, commit, save


def test_a_failed_revert_reports_the_breakage_and_commits_nothing():
    broken, revert, commit, save = _measure([False, False])
    assert broken == ["acceptance: b"]
    assert revert.call_count == 2
    commit.assert_not_called()
    save.assert_not_called()


def test_a_revert_that_works_on_the_second_try_is_reported_too():
    broken, revert, commit, save = _measure([False, True])
    assert broken == ["acceptance: b"] and revert.call_count == 2
    commit.assert_not_called()
