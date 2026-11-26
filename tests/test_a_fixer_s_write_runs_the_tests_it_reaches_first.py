"""After a fixer's write, the tests the code graph says reach the changed file run first, and the defect's own only when
those pass (plan PF.3, LF.1557, `TESTS_REACHED_FIRST`).

Before it, the check after a write ran only the defect's own tests: a write that broke another criterion's test served
by the same file was found at the measurement after the stage, by the whole suite, and the whole fix was reverted for
it, minutes after the write that caused it.

The product and its acceptance suite are a captured Go notes service and the suite its run stored
(`tests/captured/projects/go-notes-api`, `tests/captured/project-tests/go-notes-api`); the sandbox that runs one
acceptance file is stood in for, writing the report the runner writes.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage

from app import ci
from app.acceptance import per_file
from app.graph import tests_reached_first, verify_after_write

CAPTURED = Path(__file__).parent / "captured"
PROJECT = "go-notes-api"
SERVER = f"{PROJECT}/server.go"
SUITE = (CAPTURED / "project-tests" / PROJECT / "acceptance" / "api.spec.js").read_text()
NAMES = re.findall(r"^test\('([^']+)'", SUITE, re.M)
CHECK = 'if strings.TrimSpace(req.Title) == "" {'
#: The test a write that refuses every title breaks, and the defect's own tests.
CREATES = "[AC-1][AC-7][AC-8] POST /notes creates a note and returns 201"
OWN = [name for name in NAMES if name.startswith("[AC-13]")]
RECORD = {"pack": "a-pack-this-host-does-not-have", "project": PROJECT, "acceptance_dir": "acceptance",
          "acceptance_pattern": "*.spec.js", "acceptance_report": "test-results/acceptance.xml",
          "acceptance_test": ["npx", "playwright", "test"]}
#: What the runner printed for the create test once every title was refused (the stored run's form).
REFUSED = "Error: expect(received).toBe(expected) // Object.is equality\n\n    Expected: 201\n    Received: 422\n"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _report(failing: dict[str, str]) -> str:
    cases = "".join(
        f'<testcase name="{name}" classname="api.spec.js">'
        + (f'<failure message="failed">{failing[name]}</failure>' if name in failing else "") + "</testcase>"
        for name in NAMES)
    return f'<?xml version="1.0"?><testsuites><testsuite name="api.spec.js">{cases}</testsuite></testsuites>'


def _the_sandbox(root: Path):
    """One acceptance file run as the suite runs it: the report it writes, by the product as it is now."""
    def run(argv, category, project):
        refuses_all = "if true {" in (root / SERVER).read_text()
        failing = {name: "Expected: 422\n    Received: 201\n" for name in OWN}
        if refuses_all:
            failing[CREATES] = REFUSED
        report = root / PROJECT / "test-results" / "acceptance.xml"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(_report(failing))
        return {"returncode": 1, "stdout": f"Running {len(NAMES)} tests\n  {len(failing)} failed\n"}
    return lambda where: run


def _a_workspace(tmp_path: Path) -> tuple[Path, str]:
    shutil.copytree(CAPTURED / "projects" / PROJECT, tmp_path / PROJECT)
    shutil.copytree(CAPTURED / "project-tests" / PROJECT, tmp_path / PROJECT, dirs_exist_ok=True)
    server = tmp_path / SERVER
    server.write_text(server.read_text().replace(CHECK, 'if req.Title == "" {'))
    (tmp_path / ".project-directory").write_text(PROJECT)
    (tmp_path / ".harness").mkdir(exist_ok=True)
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps(RECORD))
    base = ci.commit(tmp_path, "as the defect found it")
    ci.save(tmp_path, ci.Snapshot(label="latest", acceptance={
        f"api.spec.js › {name}": "failed" if name in OWN else "passed" for name in NAMES}, acceptance_ran=True))
    per_file.forget_runs()
    return tmp_path, base


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("TESTS_REACHED_FIRST", "on")
    monkeypatch.setenv("VERIFY_AFTER_WRITE", "on")


def _the_write_s_answer(tmp_path: Path, written: str) -> str:
    """What the fix stage's write of `written` into the server file answers, the fixer's stage run by the fix node."""
    from workflow_nodes import a_defect, a_fix_stage

    root, base = _a_workspace(tmp_path)
    answers: list[str] = []

    def the_fixer(state, config, *, stage_name, **kwargs):
        (root / SERVER).write_text(written)
        reply = ToolMessage(content=f"Edited {SERVER}", tool_call_id="1")
        answers.append(verify_after_write.after_a_write(
            "edit_file", reply, config["configurable"].get("app_run_id"), stage_name).content)
        from app.agents.specialists import SpecialistOutput

        return {"__fix_result__": SpecialistOutput(changed_files=[SERVER], tests=["acceptance/api.spec.js"])}

    defect = a_defect("[AC-13] POST /notes accepts a title of only spaces", affected_files=[SERVER])
    a_fix_stage(root, [defect], patches={
        "app.graph.workflow._fast_delivery": lambda: False,
        "app.graph.engineering.before_a_fix": lambda *args: base,
        "app.graph.workflow._run_gated_agent": the_fixer,
        "app.graph.workflow._the_defect_s_tests_pass": lambda where, defect: False,
        "app.stacks.scaffold.sandbox_runner": _the_sandbox(root),
    })
    return answers[0]


def test_a_write_that_breaks_a_test_its_file_serves_is_told_so_at_once(tmp_path):
    fixed = (CAPTURED / "projects" / SERVER).read_text()

    answer = _the_write_s_answer(tmp_path, fixed.replace(CHECK, "if true {"))

    assert f"`{CREATES}` (`{PROJECT}/acceptance/api.spec.js`)" in answer
    assert "Received: 422" in answer
    assert "this defect's own tests were not run" in answer
    assert not BANNED.search(re.sub(r"`[^`]*`", "", answer))


def test_a_write_that_breaks_nothing_it_reaches_goes_on_to_the_defect_s_own_tests(tmp_path):
    fixed = (CAPTURED / "projects" / SERVER).read_text()

    answer = _the_write_s_answer(tmp_path, fixed.replace(CHECK, 'if len(req.Title) == 0 {'))

    assert tests_reached_first.SAID not in answer
    assert tests_reached_first.OWN_FAILING in answer


def test_the_tests_reaching_a_service_file_are_the_ones_requesting_its_routes(tmp_path):
    from app.analysis import project_graph

    root, _ = _a_workspace(tmp_path)

    acceptance, unit = tests_reached_first.reached(project_graph.build(root), [SERVER])

    assert set(acceptance) == {f"{PROJECT}/acceptance/api.spec.js"}
    assert {"AC-1", "AC-13"} <= acceptance[f"{PROJECT}/acceptance/api.spec.js"]
    assert unit == set()


def test_the_new_words_avoid_the_product_words():
    for text in (tests_reached_first.SAID, tests_reached_first.FAILING, tests_reached_first.OWN_FAILING,
                 tests_reached_first.said(["`x` (`y`): z"])):
        assert not BANNED.search(re.sub(r"`[^`]*`", "", text))
