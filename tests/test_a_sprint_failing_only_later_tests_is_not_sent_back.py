"""A sprint whose locked suite fails only tests of criteria a later sprint delivers is not sent back by the gate.

Measured on one run: sprint 1 of 2 had 18 locked tests failing, every one waiting on a criterion not yet due; the
milestone review accepted it, the measured-suite gate sent it back, the lead re-planned with nothing to build, and the
run went round review, re-plan and review three times without building anything.
"""
import inspect
from types import SimpleNamespace

from app.acceptance import junit, sprint_scope, suite
from app.graph import settle_when_green, workflow


def _measured(monkeypatch, failing, waiting):
    monkeypatch.setattr(suite, "last_result", lambda root: {"ran": True, "passed": 30, "failed": len(failing)})
    monkeypatch.setattr(suite, "_command", lambda root: (["pytest"], "report.xml", "app"))
    monkeypatch.setattr(junit, "read", lambda path: SimpleNamespace(tests=[
        SimpleNamespace(name=name, outcome="failed") for name in failing] + [SimpleNamespace(name="ok", outcome="passed")]))
    monkeypatch.setattr(sprint_scope, "waiting_tests", lambda root: waiting)


def test_failing_only_tests_of_a_later_sprint_is_green_for_this_sprint(monkeypatch):
    _measured(monkeypatch, ["test_ac11_items_no_auth", "test_ac5_toggle"],
              {"test_ac11_items_no_auth": ["AC-11"], "test_ac5_toggle": ["AC-5"]})
    assert settle_when_green.the_locked_suite_is_green_for_this_sprint("/w") is True


def test_one_failing_test_of_this_sprint_is_not(monkeypatch):
    _measured(monkeypatch, ["test_ac11_items_no_auth", "test_ac1_signup"], {"test_ac11_items_no_auth": ["AC-11"]})
    assert settle_when_green.the_locked_suite_is_green_for_this_sprint("/w") is False


def test_no_later_sprint_or_nothing_failing_is_not(monkeypatch):
    _measured(monkeypatch, ["test_ac1_signup"], {})
    assert settle_when_green.the_locked_suite_is_green_for_this_sprint("/w") is False
    _measured(monkeypatch, [], {"test_ac11_items_no_auth": ["AC-11"]})
    assert settle_when_green.the_locked_suite_is_green_for_this_sprint("/w") is False


def test_the_measured_suite_gate_asks_it():
    assert "the_locked_suite_is_green_for_this_sprint(" in inspect.getsource(workflow)
