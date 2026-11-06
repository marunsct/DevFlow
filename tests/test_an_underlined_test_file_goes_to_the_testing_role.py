"""A language-service finding in a test file is the testing role's to fix, not the first builder's.

Measured on one run: `tests/test_main.py` named a function the module does not have; the defect's owner was chosen
with no file at all - the first role in the plan that is not testing - so two backend fixers in a row were sent a
unit test's fault and each left it "still reported".
"""
from types import SimpleNamespace

from app.graph import engineering


def _state():
    plan = SimpleNamespace(tasks=[SimpleNamespace(title="API routes", specialist_role="backend"),
                                  SimpleNamespace(title="Unit tests", specialist_role="testing")])
    return {"milestone_plan": plan, "sprint_plan": plan}


def test_a_test_file_s_finding_goes_to_testing(monkeypatch):
    monkeypatch.setattr(engineering, "_tasks", lambda state: _state()["milestone_plan"].tasks)
    assert engineering.owner_of_the_file(_state(), "tasks-api/tests/test_main.py") == "testing"


def test_a_product_file_s_finding_goes_to_a_builder(monkeypatch):
    monkeypatch.setattr(engineering, "_tasks", lambda state: _state()["milestone_plan"].tasks)
    assert engineering.owner_of_the_file(_state(), "tasks-api/tasks_api/main.py") == "backend"


def test_the_underlined_defects_use_it():
    import inspect

    assert "owner=owner_of_the_file(state, relative)" in inspect.getsource(engineering.underlined_in_the_batch)
