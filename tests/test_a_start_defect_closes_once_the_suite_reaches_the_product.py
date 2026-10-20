"""A "the product does not start" defect closes once the suite reaches the product.

Measured on one gate run: round 1's run of the suite passed 47 of 62 tests, and
round 0's start defect stayed open. It names no criterion, so the round's
measurement could not close it; its fixer spent 20 minutes on it and left it
open as "its own tests still fail" - the unit tests, which say nothing about
how the suite starts the product, failing for another reason.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app import ci
from app.graph import workflow
from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START
from app.sprint import Defect


def _start_defect():
    return Defect(description=THE_PRODUCT_DOES_NOT_START, severity="blocking", reproduction_steps="run the suite",
                  expected_behavior="it starts", actual_behavior="unable to open database file", owner="backend",
                  found_in_round=0)


def _last_result(root, **result):
    (root / ".harness").mkdir(exist_ok=True)
    (root / ".harness" / "acceptance-result.json").write_text(json.dumps(result))


def test_the_round_s_measurement_closes_it_when_the_suite_reached_the_product(tmp_path, monkeypatch):
    _last_result(tmp_path, passed=47, failed=15, problem="")
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "current_sprint_index": 0}
    cycle = SimpleNamespace(defects=[_start_defect()])
    marked = []
    monkeypatch.setattr(workflow, "mark_defect_fixed", lambda cycle, index, **kw: marked.append((index, kw)) or cycle)

    workflow._closed_by_this_round_s_measurement(state, cycle, 1)

    ((index, kw),) = marked
    assert index == 0 and "47 of 62" in kw["resolution"]


def test_it_stays_open_while_the_product_does_not_start(tmp_path):
    _last_result(tmp_path, passed=0, failed=0, problem="The product did not start for the acceptance suite: ...")

    assert workflow._the_product_starts_now(str(tmp_path), _start_defect()) == ""


def test_a_fix_is_settled_on_whether_the_suite_reached_the_product_not_on_the_unit_tests(tmp_path):
    ci.save(tmp_path, ci.Snapshot(label="after defect_fix_2_1", unit={"pytest › tests.test_items": "failed"},
                                  unit_ran=True, acceptance={"items.spec.js › AC-1 lists": "passed"},
                                  acceptance_ran=True))

    assert workflow._the_defect_s_tests_in(str(tmp_path), "after defect_fix_2_1", _start_defect()) is True
    ci.save(tmp_path, ci.Snapshot(label="after defect_fix_2_2", acceptance_ran=True,
                                  problem="The product did not start for the acceptance suite: ..."))
    assert workflow._the_defect_s_tests_in(str(tmp_path), "after defect_fix_2_2", _start_defect()) is False
