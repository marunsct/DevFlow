"""A failing unit or partial run beside a locked suite measured fully green does not send an accepted sprint back.

Measured on three runs: the ledger's last test run was 9 cases with 1 failed while the locked suite stood at 18 of 18;
each accepted sprint was sent back for a revision, though the owner's rule (LF.327) is that a green sprint is not
redrafted for unit tests alone.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import settle_when_green, workflow

STATE = {"repository": SimpleNamespace(root_path="/x"), "sprint_attempts": []}
RED = {"tests": 9, "passed": 8, "failed": 1, "returncode": 1}


def _measured(monkeypatch, green: bool, last: str):
    monkeypatch.setenv("SETTLE_WHEN_ACCEPTANCE_IS_GREEN", "on")
    monkeypatch.setattr(workflow, "_the_suite_the_ledger_measured", lambda state: dict(RED))
    monkeypatch.setattr(workflow, "_the_last_test_command", lambda state: last)
    monkeypatch.setattr(settle_when_green, "the_locked_suite_is_green", lambda root: green)
    monkeypatch.setattr(settle_when_green, "the_acceptance_command", lambda root: "npm run test:acceptance")


def test_a_unit_run_failing_beside_a_green_suite_is_not_sent_back(monkeypatch):
    _measured(monkeypatch, green=True, last="npm test")
    assert workflow._a_red_suite_the_review_called_green(STATE) == ""


def test_the_suite_itself_failing_or_a_red_suite_still_is(monkeypatch):
    _measured(monkeypatch, green=True, last="npm run test:acceptance")
    assert workflow._a_red_suite_the_review_called_green(STATE).startswith("MUST FIX")
    _measured(monkeypatch, green=False, last="npm test")
    assert workflow._a_red_suite_the_review_called_green(STATE).startswith("MUST FIX")
