"""A sprint whose suite, repaired at the end of an attempt, passes in full beside passing unit tests is measured again,
not planned again.

Measured three times in one day: a dispute at an attempt's end repaired the suite, it then passed in full beside passing
unit tests, and the sprint was planned again anyway - a lead's re-plan on a done product.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import ci
from app.acceptance import unstable
from app.graph import acceptance_nodes
from workflow_nodes import an_acceptance_review


def _result(*outcomes):
    return SimpleNamespace(ran=True, report=SimpleNamespace(tests=[SimpleNamespace(outcome=o) for o in outcomes]))


def _unit(tmp_path, monkeypatch, passed, same_product=True):
    monkeypatch.setattr(unstable, "fingerprint", lambda root: "now")
    path = tmp_path / ci.UNIT_RUN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"passed": passed, "fingerprint": "now" if same_product else "before"}))


def test_green_suite_and_passing_unit_tests_on_this_product(tmp_path, monkeypatch):
    _unit(tmp_path, monkeypatch, True)
    assert acceptance_nodes.a_repair_left_the_sprint_green(tmp_path, _result("passed", "passed"))


def test_anything_short_of_that_is_planned_again(tmp_path, monkeypatch):
    _unit(tmp_path, monkeypatch, True)
    assert not acceptance_nodes.a_repair_left_the_sprint_green(tmp_path, _result("passed", "failed"))
    assert not acceptance_nodes.a_repair_left_the_sprint_green(tmp_path, _result())
    _unit(tmp_path, monkeypatch, False)
    assert not acceptance_nodes.a_repair_left_the_sprint_green(tmp_path, _result("passed"))
    _unit(tmp_path, monkeypatch, True, same_product=False)
    assert not acceptance_nodes.a_repair_left_the_sprint_green(tmp_path, _result("passed"))


EVERY_CRITERION = ("test('[AC-1] adds', async () => {});\ntest('[AC-2] deletes', async () => {});\n"
                   "test('[AC-3] persists', async () => {});\n")


@pytest.mark.parametrize(("unit_tests_pass", "stage"), [(True, "test_and_triage"), (False, "technical_lead")])
def test_the_lock_after_a_repair_at_a_re_plan_s_entry_goes_to_a_test_round_only_when_green(
        tmp_path, monkeypatch, unit_tests_pass, stage):
    _unit(tmp_path, monkeypatch, unit_tests_pass)

    update = an_acceptance_review(tmp_path, EVERY_CRITERION,
                                  passed=["[AC-1] adds", "[AC-2] deletes", "[AC-3] persists"],
                                  state={"acceptance_return_to": "sprint_replan"})

    assert update["stage"] == stage
