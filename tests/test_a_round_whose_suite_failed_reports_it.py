"""A test round whose own last run of the suite failed cannot report no defects.

Measured on one run: two rounds in a row ran `npm test`, were answered with
exit 134 and a heap-exhaustion trace, and returned an empty defect list. The
sprint went to its milestone review as passing, the review found the suite
failing, and the run ended on its last revision with nobody asked to fix it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.graph.workflow import _a_suite_failure_the_round_did_not_report
from app.tools.sandbox import _ledger_path

NPM_TEST = ["npm", "test"]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "the-app-run-abc"
    root.mkdir()
    return root


def _ran(root: Path, *entries: dict) -> None:
    path = _ledger_path(str(root))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def _entry(stage: str, code, command=NPM_TEST, category="test", error=None) -> dict:
    return {"stage": stage, "command": command, "category": category, "returncode": code, "error": error}


def test_a_failed_last_run_becomes_a_defect(workspace) -> None:
    _ran(workspace, _entry("test_round_5", 0), _entry("test_round_5", 134))

    defect = _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_5")

    assert defect is not None and defect.severity == "major"
    assert "`npm test` exited 134" in defect.description
    assert defect.owner == "testing"


def test_a_suite_that_failed_and_then_passed_is_dealt_with(workspace) -> None:
    _ran(workspace, _entry("test_round_5", 1), _entry("test_round_5", 0))

    assert _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_5") is None


def test_a_timeout_counts_as_a_failure(workspace) -> None:
    _ran(workspace, _entry("test_round_2", None, error="Command timed out after 300 seconds."))

    defect = _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_2")

    assert defect is not None and "timed out" in defect.description


def test_another_stage_s_runs_and_other_commands_are_not_this_round_s(workspace) -> None:
    _ran(
        workspace,
        _entry("defect_fix_6_0", 134),
        _entry("test_round_6", 1, command=["grep", "-n", "x", "app.js"], category="default"),
    )

    assert _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_6") is None


def test_a_round_that_ran_nothing_is_left_as_reported(workspace) -> None:
    assert _a_suite_failure_the_round_did_not_report(str(workspace), "test_round_0") is None
