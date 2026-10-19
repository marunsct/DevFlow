"""A criterion is traced to the step that first made one of its tests pass (plan BG.9).

The run page listed which criteria pass, and the Changes tab listed every
commit, with nothing between them: which change made a criterion pass could
only be found by reading diffs. Each snapshot now records when a test first
passed and after which step; a test that fails again keeps its first time.
"""

from __future__ import annotations

import json

from app import ci


def _snapshot(label: str, passing: list[str], failing: list[str] = ()) -> ci.Snapshot:
    tests = {**{name: "passed" for name in passing}, **{name: "failed" for name in failing}}
    return ci.Snapshot(label=label, acceptance=tests, acceptance_ran=True)


def test_a_criterion_s_first_passing_test_and_the_step_after_which_it_passed(tmp_path):
    ci.save(tmp_path, _snapshot("suite locked", [], ["auth.spec.js › [AC-1] signs in", "items.spec.js › [AC-2][AC-3] adds"]))
    ci.save(tmp_path, _snapshot("after defect_fix_1_0", ["auth.spec.js › [AC-1] signs in"], ["items.spec.js › [AC-2][AC-3] adds"]))
    ci.save(tmp_path, _snapshot("after defect_fix_1_1", [], ["auth.spec.js › [AC-1] signs in"]))
    ci.save(tmp_path, _snapshot("after defect_fix_1_2", ["auth.spec.js › [AC-1] signs in", "items.spec.js › [AC-2][AC-3] adds"]))

    found = ci.first_passes(tmp_path)

    assert found["AC-1"]["after"] == "after defect_fix_1_0" and found["AC-1"]["test"] == "auth.spec.js › [AC-1] signs in"
    assert found["AC-2"]["after"] == found["AC-3"]["after"] == "after defect_fix_1_2"
    assert found["AC-1"]["at"] <= found["AC-2"]["at"]


def test_the_latest_snapshot_is_kept_as_before(tmp_path):
    ci.save(tmp_path, _snapshot("after defect_fix_1_0", ["auth.spec.js › [AC-1] signs in"]))
    assert ci.load(tmp_path).label == "after defect_fix_1_0"
    assert set(json.loads((tmp_path / ci.CI_FILE).read_text())) == {"latest", "first_passed"}


def test_no_record_is_no_trace(tmp_path):
    assert ci.first_passes(tmp_path) == {}
