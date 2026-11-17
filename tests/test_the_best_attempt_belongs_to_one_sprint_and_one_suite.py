"""The best-attempt record belongs to one sprint and one locked suite, and a tie keeps the newer product.

Found in a code review: `.harness/best-attempt.json` was never reset. A later sprint's first batch could be undone for
passing fewer tests than the last sprint's best, a count from a suite since repaired decided a put-back, and a tie
kept the oldest commit, so a put-back threw away every later change that passed as many tests.
"""
from __future__ import annotations

import json
from unittest import mock

from app import ci
from app.acceptance import suite
from app.graph import best_attempt


def _workspace(tmp_path, suite_text="test('a')"):
    (tmp_path / ".harness").mkdir(exist_ok=True)
    spec = tmp_path / "acceptance" / "a.spec.js"
    spec.parent.mkdir(exist_ok=True)
    spec.write_text(suite_text)
    return spec


def _noted(tmp_path, passed, commit, total=10):
    with mock.patch.object(best_attempt, "enabled", return_value=True), \
            mock.patch.object(best_attempt, "_passed_now", return_value=passed), \
            mock.patch.object(suite, "last_result", return_value={"ran": True, "passed": passed, "failed": total - passed}), \
            mock.patch.object(ci, "commit", return_value=commit):
        best_attempt.note(tmp_path)
    return json.loads((tmp_path / ".harness" / "best-attempt.json").read_text())


def test_a_tie_keeps_the_newer_product(tmp_path):
    _workspace(tmp_path)
    assert _noted(tmp_path, 5, "old")["commit"] == "old"
    assert _noted(tmp_path, 5, "new")["commit"] == "new"


def test_a_record_made_against_a_suite_of_another_size_is_not_the_best(tmp_path):
    _workspace(tmp_path)
    _noted(tmp_path, 9, "c1", total=10)
    with mock.patch.object(suite, "last_result", return_value={"ran": True, "passed": 3, "failed": 17}):
        assert best_attempt._best(tmp_path) == {}
    with mock.patch.object(suite, "last_result", return_value={"ran": True, "passed": 3, "failed": 7}):
        assert best_attempt._best(tmp_path)["commit"] == "c1"
    assert _noted(tmp_path, 3, "c2", total=20)["commit"] == "c2"


def test_the_record_is_dropped_when_a_sprint_is_accepted(tmp_path):
    from types import SimpleNamespace

    from workflow_nodes import run_node

    _workspace(tmp_path)
    _noted(tmp_path, 4, "c1")

    update = run_node("sprint_advance", {"repository": SimpleNamespace(root_path=str(tmp_path)), "current_sprint_index": 0},
                      str(tmp_path), {"app.graph.workflow._record_sprint_summary": lambda state, status: {}})

    assert update["current_sprint_index"] == 1
    assert not (tmp_path / ".harness" / "best-attempt.json").exists()
