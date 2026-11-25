"""The page probe keeps whether it ran clean, found something, or could not run (deep review of silent mechanisms).

Measured: the probe was reached in 8 of 45 workspaces with no finding, and it returned None both when it could not run
and when its runner wrote no report, logged only at debug level: nothing told "four checks passed" from "did not run".
The contract probes keep such a record in `.harness/contract-probe.json`; the page probe now keeps one there too.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.acceptance import interface_contract as ic
from app.acceptance import page_probe, probe_coverage
from app.stacks import contract

#: The checks' names as the spec gives them, and what Playwright says of a check the spec skips.
RAN = [
    SimpleNamespace(name="page check 1: markup typed into a text field is shown as text", outcome="passed", message=""),
    SimpleNamespace(name="page check 2: no console error or failed request while an item is added", outcome="passed",
                    message=""),
    SimpleNamespace(name="page check 3: the page fits a 360px-wide screen", outcome="skipped",
                    message="the brief does not ask for small screens"),
    SimpleNamespace(name="page check 4: an item added is still shown after a reload", outcome="skipped",
                    message="the brief does not say the data persists"),
]


@pytest.fixture
def a_page_project(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGE_PROBE", "on")
    pack = SimpleNamespace(probe_runner="playwright", runtime_report="test-results/page-load.json")
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "app"}))
    (tmp_path / "app").mkdir()
    return tmp_path


def _kept(root):
    return json.loads((root / probe_coverage.COVERAGE_FILE).read_text())[page_probe.RECORD_KIND]


def test_a_clean_run_is_kept_with_each_check_s_result(a_page_project, monkeypatch):
    monkeypatch.setattr(ic, "_the_probe_s_report", lambda *a, **k: SimpleNamespace(found=True, tests=RAN))

    assert page_probe.page_errors(a_page_project, "A list of notes.", runner=lambda *a, **k: {}) == []

    kept = _kept(a_page_project)
    assert kept["outcome"] == "ran clean" and kept["probed"] == 2
    assert sorted(s["reason"] for s in kept["skipped"]) == ["the brief does not ask for small screens",
                                                            "the brief does not say the data persists"]


def test_a_run_with_no_report_is_kept_as_not_run(a_page_project, monkeypatch):
    monkeypatch.setattr(ic, "_the_probe_s_report", lambda *a, **k: None)

    assert page_probe.page_errors(a_page_project, "A list of notes.", runner=lambda *a, **k: {}) is None

    assert _kept(a_page_project)["outcome"].startswith("could not run")


def test_a_probe_that_raised_is_kept_as_not_run_with_why(a_page_project, monkeypatch):
    def broken(*a, **k):
        raise OSError("the sandbox is gone")

    monkeypatch.setattr(ic, "_the_probe_s_report", broken)

    assert page_probe.page_errors(a_page_project, "A list of notes.", runner=lambda *a, **k: {}) is None

    assert "OSError" in _kept(a_page_project)["outcome"]


def test_the_effects_report_shows_the_outcome():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "effects_script", Path(__file__).resolve().parents[1] / "scripts" / "loop" / "effects.py")
    effects = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(effects)

    lines = effects.contract_probe_lines({"page": {"considered": 4, "asked": 4, "probed": 2, "skipped": [],
                                                   "outcome": "ran clean"}})

    assert lines == ["contract probe page: 4 lines, 4 asked, 2 probed; ran clean"]
