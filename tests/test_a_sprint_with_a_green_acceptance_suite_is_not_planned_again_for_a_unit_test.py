"""A sprint whose acceptance suite is fully green goes to the escalation when only unit tests are open, not to another re-plan.

Measured on a small-model run: 18 of 18 acceptance criteria passed from the eighteenth minute; the one open defect was a
unit test the model had written; the sprint was planned, drafted and measured again, three passes ending the same way.
Behind `SETTLE_WHEN_ACCEPTANCE_IS_GREEN`.
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import settle_when_green, workflow

UNIT = SimpleNamespace(status="open", description="The unit tests fail. It says: loadNotes throws on malformed JSON")
CRITERION = SimpleNamespace(status="open", description="[AC-5] Delete a note - the acceptance suite says this does not work yet.")


def _result(root, **fields):
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ran": True, "passed": 19, "failed": 0, **fields}))


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "on")


def test_a_green_suite_with_only_a_unit_test_open_settles_after_one_replan(tmp_path):
    _result(tmp_path)
    assert settle_when_green.applies(tmp_path, [UNIT], replans=1) is True


def test_the_first_exhaustion_still_gets_its_replan(tmp_path):
    _result(tmp_path)
    assert settle_when_green.applies(tmp_path, [UNIT], replans=0) is False


@pytest.mark.parametrize("fields", [{"failed": 1}, {"passed": 0}, {"ran": False}, {"problem": "The product did not start"}])
def test_a_suite_that_is_not_green_does_not_settle(tmp_path, fields):
    _result(tmp_path, **fields)
    assert settle_when_green.applies(tmp_path, [UNIT], replans=1) is False


def test_an_open_criterion_defect_does_not_settle(tmp_path):
    _result(tmp_path)
    assert settle_when_green.applies(tmp_path, [UNIT, CRITERION], replans=1) is False
    assert settle_when_green.applies(tmp_path, [], replans=1) is False


def test_off_nothing_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "off")
    _result(tmp_path)
    assert settle_when_green.applies(tmp_path, [UNIT], replans=1) is False


def test_the_replan_asks_before_it_plans_again():
    source = inspect.getsource(workflow)
    body = source[source.index("def _replan_or_escalate("):source.index("def defect_remediation_node(")]
    assert "settle_when_green.applies(" in body
    assert body.index("settle_when_green.applies(") < body.index("if revision_count > MAX_MILESTONE_REVISIONS:")
