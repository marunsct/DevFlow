"""A sprint whose suite, repaired at the end of an attempt, passes in full beside passing unit tests is measured again,
not planned again.

Measured three times in one day: a dispute at an attempt's end repaired the suite, it then passed in full beside passing
unit tests, and the sprint was planned again anyway - a lead's re-plan on a done product.
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

from app import ci
from app.acceptance import unstable
from app.graph import acceptance_nodes


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


def test_the_lock_returns_to_a_test_round_then():
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    at = source.index("a_repair_left_the_sprint_green(root, result)")
    assert 'stage = "test_and_triage"' in source[at:at + 800]
