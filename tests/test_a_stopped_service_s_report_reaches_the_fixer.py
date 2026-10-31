"""What a service wrote as it stopped by itself under a test reaches the defect a fixer is shown.

Measured on one run: the helper's report stood in the suite's output, the test read "socket hang up", and no defect carried
the service's own fatal error.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import suite
from app.agents.specialists import ReportedDefect
from app.graph import acceptance_nodes, workflow
from app.stacks.packs._service import SERVICE_STOPPED_BY_ITSELF

_FATAL = "Fatal error reading the data file"
_REPORT = f"{SERVICE_STOPPED_BY_ITSELF} (code 1, signal null). What it wrote: Listening\n{_FATAL}"
_FAILING = {
    "id": "AC-6", "text": "records survive a restart",
    "tests": [{"name": "[AC-6] records survive", "outcome": "failed", "message": "socket hang up (ECONNRESET)"}],
}


def _defect(description: str, actual: str = "") -> ReportedDefect:
    return ReportedDefect(description=description, severity="major", reproduction_steps="Run it.", expected_behavior="It works.",
                          actual_behavior=actual, affected_files=[], owner="backend")


def _measured(monkeypatch, tmp_path, saved: dict):
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda _state: ([_FAILING], "npm test"))
    monkeypatch.setattr(suite, "last_result", lambda _root: saved)
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda _state, _text: "backend")
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


def test_what_the_server_logged_keeps_the_report_from_the_whole_run():
    output = _REPORT + "\n" + "x" * (suite.OUTPUT_TAIL_CHARS * 2)
    logged = suite.what_the_server_logged(output)
    assert SERVICE_STOPPED_BY_ITSELF in logged and _FATAL in logged


def test_no_report_adds_nothing():
    assert suite.what_the_server_logged("1 failed\n") == ""


def test_the_raised_defect_carries_what_the_service_wrote(monkeypatch, tmp_path):
    state = _measured(monkeypatch, tmp_path, {"output": _REPORT})
    defects = acceptance_nodes.failing_due_defects(state, [])
    assert any(_FATAL in item.actual_behavior for item in defects)


def test_a_defect_the_round_wrote_itself_carries_it_too(monkeypatch, tmp_path):
    state = _measured(monkeypatch, tmp_path, {"server_log": _REPORT})
    own = _defect("[AC-6] restart loses the records")
    acceptance_nodes.failing_due_defects(state, [own])
    assert _FATAL in own.actual_behavior


def test_it_survives_a_merge_under_another_defect():
    lead = _defect("The unit tests fail in `shared-thing`", "exit 1")
    other = _defect("[AC-6] `shared-thing` restart", _REPORT)
    merged = workflow._one_defect_per_cause([lead, other])
    assert len(merged) == 1 and _FATAL in merged[0].actual_behavior


def test_a_dispute_sees_a_report_the_output_s_tail_lost(monkeypatch, tmp_path):
    spec = tmp_path / "persistence.spec.js"
    spec.write_text("const { startService } = require('./service.cjs');\ntest('[AC-6] records survive', async () => {});\n")
    monkeypatch.setattr(suite, "suite_files", lambda _root: [spec])
    monkeypatch.setattr(suite, "last_result", lambda _root: {"output": "1 failed", "server_log": _REPORT})
    line = "`[AC-6] records survive` cannot pass for any product"
    assert acceptance_nodes.tests_whose_service_stayed_up(tmp_path, [line]) == ([], ["[AC-6] records survive"])
