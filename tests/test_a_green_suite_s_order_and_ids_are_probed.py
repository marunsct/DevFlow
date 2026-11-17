"""Behind `ORDER_PROBE`, tests failing only when their file runs alone are recorded; behind `IDS_READ_WITHOUT_A_CREATE`, a literal id nothing created is a finding (plan item 20)."""
from __future__ import annotations

import json
import re
import runpy
import shutil
from pathlib import Path

import pytest

from app.acceptance import ids_read_without_a_create as ids
from app.acceptance import order_probe, suite
from app.stacks import contract, pack_named

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "locked_suites"


def _junit(tests: dict[str, bool]) -> str:
    cases = "".join(
        f'<testcase name="{name}" classname="c" time="0">' + ("" if ok else '<failure message="boom">boom</failure>') + "</testcase>"
        for name, ok in tests.items())
    return f'<testsuites><testsuite name="s" tests="{len(tests)}">{cases}</testsuite></testsuites>'


def _record(tmp_path: Path) -> tuple[dict, Path]:
    base = tmp_path / "p" / "acceptance"
    base.mkdir(parents=True)
    for name in ("a.spec.js", "b.spec.js", "c.spec.js"):
        (base / name).write_text("//")
    report = tmp_path / "p" / "test-results" / "acceptance.xml"
    record = {"project": "p", "acceptance_dir": "acceptance", "acceptance_pattern": "*.spec.js",
              "acceptance_test": ["runner", "test", "acceptance"], "acceptance_report": "test-results/acceptance.xml"}
    return record, report


def _runner(report: Path, outcomes: dict[str, dict[str, bool] | None], seen: list[str]):
    def run(argv, kind, project):
        name = next(a for a in argv if a.endswith(".spec.js"))
        seen.append(name)
        assert kind == "probe" and project == "p"
        result = outcomes[name]
        if result is not None:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(_junit(result))
        return {"returncode": 0}
    return run


def test_each_file_runs_alone_last_first_and_what_fails_only_then_is_recorded(tmp_path):
    record, report = _record(tmp_path)
    report.parent.mkdir(parents=True)
    report.write_text(_junit({"whole": True}))
    seen: list[str] = []
    found = order_probe.probe(tmp_path, record, _runner(report, {
        "acceptance/a.spec.js": {"a1": True},
        "acceptance/b.spec.js": {"[AC-2] reads what a left": False, "b2": True},
        "acceptance/c.spec.js": None,
    }, seen))
    assert seen == ["acceptance/c.spec.js", "acceptance/b.spec.js", "acceptance/a.spec.js"]
    assert [u["test"] for u in found["unstable"]] == ["[AC-2] reads what a left"]
    assert found["files_run"] == 2 and found["files_without_a_report"] == 1
    # The whole suite's report, which the next round reads, is as it was.
    assert "whole" in report.read_text()


def test_a_suite_of_one_file_is_not_probed(tmp_path):
    record, report = _record(tmp_path)
    for name in ("b.spec.js", "c.spec.js"):
        (tmp_path / "p" / "acceptance" / name).unlink()
    assert order_probe.probe(tmp_path, record, lambda *_: {}) == {}


def _locked(tmp_path: Path, monkeypatch) -> Path:
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    where = tmp_path / "notes" / "acceptance"
    where.mkdir(parents=True, exist_ok=True)
    (where / "a.spec.js").write_text("//a")
    (where / "b.spec.js").write_text("//b")
    monkeypatch.setattr(suite, "is_locked", lambda _: True)
    return tmp_path


def test_it_runs_once_for_a_suite_when_on_and_never_when_off(tmp_path, monkeypatch):
    root = _locked(tmp_path, monkeypatch)
    calls = []
    record = contract.read(root)
    report = root / "notes" / record["acceptance_report"]

    def run(argv, kind, project):
        calls.append(argv)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(_junit({"t": True}))
        return {"returncode": 0}

    monkeypatch.setenv("ORDER_PROBE", "off")
    assert order_probe.at_a_green_round(root, run) == {} and not calls
    monkeypatch.setenv("ORDER_PROBE", "on")
    assert order_probe.at_a_green_round(root, run)["files_run"] == 2
    assert json.loads((root / order_probe.FILE).read_text())["unstable"] == []
    assert order_probe.at_a_green_round(root, run) == {} and len(calls) == 2
    # A changed suite is probed again.
    (root / "notes" / "acceptance" / "a.spec.js").write_text("//changed")
    assert order_probe.at_a_green_round(root, run)["files_run"] == 2


def test_a_probe_that_fails_costs_the_round_nothing(tmp_path, monkeypatch):
    root = _locked(tmp_path, monkeypatch)
    monkeypatch.setenv("ORDER_PROBE", "on")

    def broken(*_):
        raise RuntimeError("no")

    assert order_probe.at_a_green_round(root, broken) == {}


def _the_round_probes(tmp_path: Path, monkeypatch, *, failed: int) -> bool:
    """Whether the test round's node probed the order of its locked suite, run with `failed` failures."""
    from types import SimpleNamespace
    from unittest.mock import patch

    from langgraph.checkpoint.memory import MemorySaver

    from app.agents.specialists import SpecialistOutput
    from app.graph import workflow

    root = _locked(tmp_path, monkeypatch)
    monkeypatch.setenv("ORDER_PROBE", "on")
    report = root / "notes" / contract.read(root)["acceptance_report"]

    def one_file_in_the_sandbox(argv, kind, project):
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(_junit({"t": True}))
        return {"returncode": 0}

    milestone = SimpleNamespace(selected_sprint_goal="Build features", milestone_scope=[], delegated_tasks=[])
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)), "milestone_plan": milestone, "test_round": 1,
        "specialist_outputs": {}, "review_defects": [], "current_sprint_index": 0,
    }
    with patch("app.graph.acceptance_nodes.acceptance_for_round", return_value=("", [])), \
         patch("app.graph.acceptance_nodes.reopen_the_suite_for", return_value=None), \
         patch("app.graph.acceptance_nodes.beyond_repair", return_value=[]), \
         patch("app.graph.acceptance_nodes._failing_due", return_value=([], "npx playwright test")), \
         patch("app.graph.workflow._run_unit_tests_procedurally", return_value=(False, "AssertionError")), \
         patch("app.graph.acceptance_nodes.suite.is_locked", return_value=True), \
         patch("app.graph.acceptance_nodes.suite.last_result",
               return_value={"ran": True, "passed": 9 - failed, "failed": failed}), \
         patch("app.agents.specialists.what_the_files_already_prove", return_value=[]), \
         patch("app.graph.acceptance_nodes.interface_defects", return_value=[]), \
         patch("app.graph.acceptance_nodes.failing_due_defects", return_value=[]), \
         patch("app.graph.workflow._with_the_contract_s_server_errors", side_effect=lambda s, result, m: result), \
         patch("app.acceptance.suite._sandbox_runner", return_value=one_file_in_the_sandbox), \
         patch("app.graph.workflow._run_gated_agent", return_value={"__test_result__": SpecialistOutput(
             changed_files=[], defects=[workflow._the_unit_tests_fail(milestone, "AssertionError: 2 != 3")])}):
        graph = workflow.build_workflow_graph(checkpointer=MemorySaver(), repo_root=str(tmp_path))
        graph.nodes["test_and_triage"].bound.invoke(state, {"configurable": {"thread_id": "t", "run_id": "r"}})
    return (root / order_probe.FILE).is_file()


@pytest.mark.parametrize(("failed", "probed"), [(0, True), (1, False)])
def test_the_round_probes_the_order_only_when_the_suite_is_green(tmp_path, monkeypatch, failed, probed):
    """The probe is run by a round whose locked suite failed nothing, whatever else it found; never by a red one."""
    assert _the_round_probes(tmp_path, monkeypatch, failed=failed) is probed


def test_the_effects_report_says_what_the_probe_recorded():
    line = runpy.run_path(str(ROOT / "scripts" / "loop" / "effects.py"))["order_probe_line"](
        {"unstable": [{"test": "t"}], "files_run": 4, "files_without_a_report": 1})
    assert "1  tests failing only when their file runs alone (4 files probed, 1 without a report)" in line


def _ids_workspace(tmp_path: Path, body: str) -> Path:
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    where = tmp_path / "notes" / "acceptance"
    where.mkdir(parents=True, exist_ok=True)
    (where / "a.spec.js").write_text("import { test, expect } from '@playwright/test';\n" + body)
    return tmp_path


def test_a_literal_id_nothing_created_is_found_when_on(tmp_path, monkeypatch):
    root = _ids_workspace(tmp_path, "test('[AC-1] reads', async ({ request }) => {\n  const r = await request.get('/notes/1');\n  expect(r.status()).toBe(200);\n});\n")
    monkeypatch.setenv("IDS_READ_WITHOUT_A_CREATE", "off")
    assert ids.findings(root) == []
    monkeypatch.setenv("IDS_READ_WITHOUT_A_CREATE", "on")
    found = ids.findings(root)
    assert len(found) == 1 and "an id the test never created" in found[0] and "line 3" in found[0]
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", found[0], re.I)
    cannot_pass = suite.tests_that_cannot_pass(root, suite.AcceptanceResult(ran=True))
    assert [item for item in cannot_pass if "an id the test never created" in item]


def test_a_test_that_creates_expects_a_refusal_or_has_a_hook_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("IDS_READ_WITHOUT_A_CREATE", "on")
    for body in (
        "test('a', async ({ request }) => { await request.post('/notes', {data:{}}); const r = await request.get('/notes/1'); });",
        "test('a', async ({ request }) => { const r = await request.get('/notes/999'); expect(r.status()).toBe(404); });",
        "test.beforeEach(async () => {});\ntest('a', async ({ request }) => { await request.get('/notes/1'); });",
    ):
        assert ids.findings(_ids_workspace(tmp_path, body)) == [], body


def test_the_stored_suites_that_passed_their_hidden_tests_give_no_id_finding(tmp_path, monkeypatch):
    monkeypatch.setenv("IDS_READ_WITHOUT_A_CREATE", "on")
    found = {}
    for kept in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        root = tmp_path / kept.name
        contract.write(root, pack_named("node-hono-native-api"), "notes", "Notes")
        shutil.copytree(kept / "acceptance", root / "notes" / "acceptance", dirs_exist_ok=True)
        items = ids.findings(root)
        if items:
            found[kept.name] = items
    assert found == {}
