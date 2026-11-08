"""Each probe of the locked contract records the lines it asked and why it left the rest (harness review HR2.Q.9).

The three probes found 3 of 1,421 gaps, and nothing said which lines they had asked: an unprobed line and a clean one
looked the same to the audit.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.acceptance import interface_contract as ic
from app.acceptance import probe_coverage


def _a_runner(tmp_path):
    def runner(argv, category, where):
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / ic.REPORT_FILE).write_text(
            '<testsuites><testsuite name="c" tests="1">'
            '<testcase name="[AC-1] contract 1: AC-1 POST /notes -&gt; 400"></testcase>'
            "</testsuite></testsuites>")
        return {"returncode": "0"}
    return runner


def test_a_contract_with_a_page_line_and_a_write_records_the_page_line_skipped_with_its_reason(tmp_path, monkeypatch):
    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(files={"playwright.config.js": ""}, probe_runner="playwright"), {"project": "app"}))
    (tmp_path / "app").mkdir()
    ic.record_at_lock(tmp_path, ["AC-1 POST /notes -> 400", 'AC-2 page /notes shows heading "Notes"'])
    assert [c.kind for c in ic.the_locked_contract(tmp_path)] == ["http", "page"]

    assert ic.server_errors(tmp_path, runner=_a_runner(tmp_path)) == []

    stored = json.loads((tmp_path / probe_coverage.COVERAGE_FILE).read_text())["server_error"]
    assert stored["considered"] == 2 and stored["asked"] == 1 and stored["probed"] == 1
    assert stored["skipped"] == [{"line": 'AC-2 page /notes shows heading "Notes"', "reason": "page line"}]


def test_a_test_the_product_s_answer_skipped_is_recorded_with_the_skip_s_message() -> None:
    check = SimpleNamespace(line="AC-1 PUT /notes/{id} -> 404")
    report = SimpleNamespace(tests=[SimpleNamespace(name="contract 1: x", outcome="skipped", message="the sign-in answered first")])
    record = probe_coverage.coverage(considered=1, asked=[check], report=report, check_of=lambda test: check)
    assert record["probed"] == 0
    assert record["skipped"] == [{"line": "AC-1 PUT /notes/{id} -> 404", "reason": "the sign-in answered first"}]


def test_a_probe_with_no_report_records_every_asked_line_as_unanswered() -> None:
    check = SimpleNamespace(line="AC-1 POST /notes -> 400")
    record = probe_coverage.coverage(considered=1, asked=[check], report=None)
    assert record["skipped"] == [{"line": "AC-1 POST /notes -> 400", "reason": "the probe's runner wrote no report"}]


def test_the_effects_report_counts_each_probe_s_skip_reasons() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "effects.py"
    spec = importlib.util.spec_from_file_location("loop_effects", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lines = module.contract_probe_lines({"server_error": {"considered": 3, "asked": 1, "probed": 1, "skipped": [
        {"line": "a", "reason": "page line"}, {"line": "b", "reason": "page line"}]}})
    assert lines == ["contract probe server_error: 3 lines, 1 asked, 1 probed; skipped: 2 page line"]
