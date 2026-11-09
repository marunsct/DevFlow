"""Each deferred criterion with a locked test gets one last rewrite aimed at it before release (deep review F3).

Measured over 19 runs: of 5 false acceptances, 4 shipped the failing behaviour as a deferred criterion. Behind
`LAST_TRY_ON_DEFERRED`; the change is kept only when the criterion's tests pass and no test that passed breaks.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.acceptance.criteria import number
from app.graph import delivery, last_try_on_deferred

BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("LAST_TRY_ON_DEFERRED", "on")
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number(BRIEF), {"AC-2": "could not be made to pass after fixes and re-planning"})
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text("test('[AC-1] adds', async () => {});\ntest('[AC-2] deletes', async () => {});\n")
    put_back: list = []
    monkeypatch.setattr("app.ci.commit", lambda root, message: "c1")
    monkeypatch.setattr("app.ci.restore_paths", lambda root, commit, paths: put_back.append(list(paths)) or True)
    return tmp_path, put_back


def _result(**outcomes):
    return SimpleNamespace(report=SimpleNamespace(tests=[
        SimpleNamespace(name=name, outcome=outcome, message="Expected: 204 Received: 404" if outcome == "failed" else "")
        for name, outcome in outcomes.items()]))


def test_a_last_try_that_passes_the_criterion_keeps_it_and_takes_it_off_the_deferred_list(workspace):
    root, put_back = workspace
    runs = iter([_result(**{"[AC-1] adds": "passed", "[AC-2] deletes": "failed"}),
                 _result(**{"[AC-1] adds": "passed", "[AC-2] deletes": "passed"})])
    asked = []

    made = last_try_on_deferred.try_them(root, {}, run_suite=lambda: next(runs),
                                         rewrite=lambda d: asked.append(d) or SimpleNamespace(changed_files=["notes/src/app.ts"]))

    assert made == ["AC-2"] and "AC-2" not in suite.deferred(root) and put_back == []
    assert "[AC-2]" in asked[0].description and "404" in asked[0].actual_behavior


def test_a_last_try_that_breaks_another_test_is_put_back(workspace):
    root, put_back = workspace
    runs = iter([_result(**{"[AC-1] adds": "passed", "[AC-2] deletes": "failed"}),
                 _result(**{"[AC-1] adds": "failed", "[AC-2] deletes": "passed"})])

    made = last_try_on_deferred.try_them(root, {}, run_suite=lambda: next(runs),
                                         rewrite=lambda d: SimpleNamespace(changed_files=["notes/src/app.ts"]))

    assert made == [] and "AC-2" in suite.deferred(root) and put_back == [["notes/src/app.ts"]]


def test_off_nothing_is_tried(workspace, monkeypatch):
    root, _ = workspace
    monkeypatch.setenv("LAST_TRY_ON_DEFERRED", "off")
    assert last_try_on_deferred.try_them(root, {}, run_suite=lambda: 1 / 0, rewrite=lambda d: 1 / 0) == []


def test_the_release_makes_the_last_try_before_it_measures_the_suite():
    source = inspect.getsource(delivery.release)
    assert source.index("last_try_on_deferred.try_them(") < source.index("result = suite.run(root)")
