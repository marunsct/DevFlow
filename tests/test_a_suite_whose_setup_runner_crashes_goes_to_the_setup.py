"""A suite whose runner crashed in the setup's own file goes to the setup stage, not to the suite's writers (LF.1594).

Measured on one run of a library with no framework: the acceptance suite's runner was the JUnit wrapper the setup
stage wrote and the harness kept. It crashed on the first failing test, so the suite wrote no report; the review sent
the suite back to its writers five times - each round found its tests right and named the crash in "the harness's
runner, which I may not change" as a blocker - and the run failed: "The acceptance suite cannot run or load". The
runner and its traceback here are the ones that run printed (`tests/captured/a-setup-runner-that-crashes-on-a-failure/`).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.acceptance.suite import AcceptanceResult
from app.graph import acceptance_nodes, runner_repair
from app.stacks import contract, custom_setup, pack_named, runner_check
from the_acceptance_review import CONFIG, reviewed

CAPTURED = Path(__file__).parent / "captured" / "a-setup-runner-that-crashes-on-a-failure"
TRACEBACK = (CAPTURED / "stderr.txt").read_text(encoding="utf-8")
RUNNER = (CAPTURED / "junit_runner.py.txt").read_text(encoding="utf-8")
#: The same runner with the line that crashed written so it reports the failure.
REPAIRED = RUNNER.replace('"".join(payload[1]) if payload else ""', 'str(payload[1]) if payload else ""')
COMMAND = ".venv/bin/python -m junit_runner acceptance test-results/acceptance.xml"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: One of the suite's tests as its writers left it: it fails until the product is built.
A_SUITE_TEST = """import unittest


class ImportTests(unittest.TestCase):
    def test_ac1_imports(self):
        import textkit  # noqa: F401
"""


@pytest.fixture(autouse=True)
def _a_library_of_its_own(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("PROVEN_SETUP_LIBRARY", str(tmp_path_factory.mktemp("library")))


def _a_proven_setup(root: Path, runner: str = RUNNER) -> Path:
    """The run's workspace after its setup was proven: the contract, the kept runner and one acceptance test."""
    declared = json.loads((CAPTURED / "stack-setup.json").read_text(encoding="utf-8"))
    setup = {**{key: declared[key] for key in ("kind", "install", "unit_test", "unit_report", "unit_dir", "unit_pattern",
                                               "acceptance_test", "acceptance_report", "acceptance_dir",
                                               "acceptance_pattern", "guide", "acceptance_guide")},
             "language": "python", "stack_line": "language Python 3", "kept": {"junit_runner.py": runner}}
    contract.write(root, custom_setup.pack_from({"pack": custom_setup.PROVEN_SETUP, "setup": setup}),
                   "text-toolkit-library", "Text toolkit", extra={"setup": setup})
    project = root / "text-toolkit-library"
    (project / "acceptance").mkdir(parents=True, exist_ok=True)
    (project / "junit_runner.py").write_text(runner, encoding="utf-8")
    (project / "acceptance" / "test_imports.py").write_text(A_SUITE_TEST, encoding="utf-8")
    (project / "tests").mkdir(exist_ok=True)
    return project


def _the_crashed_run() -> AcceptanceResult:
    return AcceptanceResult(ran=False, exit_code=1, command=COMMAND, output=TRACEBACK,
                            problem="the runner wrote no report at `test-results/acceptance.xml`")


def test_the_captured_crash_is_read_as_one_in_the_setup_s_runner(tmp_path):
    _a_proven_setup(tmp_path)

    crash = runner_check.the_setup_s_runner_crashed(tmp_path, TRACEBACK)

    assert (crash.file, crash.line) == ("junit_runner.py", 86)
    assert "TypeError: can only join an iterable" in crash.traceback


def test_the_same_crash_under_a_stack_pack_is_not_the_setup_s(tmp_path):
    """A pack's runners are the harness's own, proven by its pack checks: nothing goes to a setup stage."""
    contract.write(tmp_path, pack_named("python-cli"), "text-toolkit-library", "Text toolkit")
    (tmp_path / "text-toolkit-library").mkdir()
    (tmp_path / "text-toolkit-library" / "junit_runner.py").write_text(RUNNER)

    assert runner_check.the_setup_s_runner_crashed(tmp_path, TRACEBACK) is None


@pytest.mark.parametrize("rounds", [1, acceptance_nodes.MAX_ACCEPTANCE_ROUNDS + 2], ids=["first round", "last round"])
def test_the_review_sends_the_crash_to_the_setup_and_spends_no_round(tmp_path, rounds):
    _a_proven_setup(tmp_path)

    update, asked = reviewed(tmp_path, _the_crashed_run(), rounds=rounds)

    assert update["stage"] == "scaffold"
    crash = update["scaffold_result"][runner_repair.CRASHED]
    assert crash["file"] == "junit_runner.py" and "can only join an iterable" in crash["traceback"]
    assert "acceptance_feedback" not in update and "acceptance_round" not in update
    assert asked == [], "the QA lead is not asked about a suite that never ran"


def test_a_run_given_its_repairs_stops_naming_the_runner(tmp_path):
    _a_proven_setup(tmp_path)

    update, _ = reviewed(tmp_path, _the_crashed_run(), state={"scaffold_result": {
        "ok": True, "runner_repairs": runner_repair.MAX_REPAIRS}})

    assert update["stage"] == "failed"
    assert "junit_runner.py" in update["error"] and "can only join an iterable" in update["error"]


def _runs_here(root: Path):
    """The sandbox's stand-in: a test command runs for real with this interpreter."""
    def run(argv, category, working_directory):
        argv = [sys.executable if part == ".venv/bin/python" else part for part in argv]
        done = subprocess.run(argv, cwd=root / working_directory, capture_output=True, text=True, timeout=120)
        return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}
    return run


def _the_repair(root: Path, writes: str, *, repairs: int = 0, changes_a_test: bool = False):
    """The scaffold node entered with the crash; the setup stage stood in for by one that writes `writes` as the runner."""
    project = root / "text-toolkit-library"
    asked: list[str] = []

    def the_setup_stage(state, config, **kwargs):
        asked.append(kwargs["initial_request"]["messages"][0]["content"])
        (project / "junit_runner.py").write_text(writes, encoding="utf-8")
        if changes_a_test:
            (project / "acceptance" / "test_imports.py").write_text("# emptied\n")
        return {"__runner_repair__": SimpleNamespace(), "stage": "acceptance_review"}

    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "acceptance_round": 3,
        "stack_pack": custom_setup.PROVEN_SETUP,
        "scaffold_result": {"ok": True, "pack": custom_setup.PROVEN_SETUP, "project": project.name,
                            "runner_repairs": repairs,
                            runner_repair.CRASHED: {"file": "junit_runner.py", "line": 86, "traceback": TRACEBACK,
                                                    "command": COMMAND, "problem": ""}},
    }
    ctx = SimpleNamespace(model=None, checkpointer=None, repo_root=str(root), allow_subdirectories=True)
    with patch("app.agents.specialists.create_specialist_agent", lambda *a, **k: None), \
            patch("app.graph.workflow._run_gated_agent", the_setup_stage), \
            patch("app.stacks.scaffold.sandbox_runner", lambda repo_root: _runs_here(Path(repo_root))):
        update = acceptance_nodes.scaffold(state, CONFIG, ctx)
    return update, asked


def test_the_setup_stage_is_asked_with_the_traceback_and_its_repair_is_kept(tmp_path):
    project = _a_proven_setup(tmp_path)

    update, asked = _the_repair(tmp_path, REPAIRED, changes_a_test=True)

    assert update["stage"] == "acceptance_review", "the suite is reviewed again, in the same round"
    assert "acceptance_round" not in update
    assert runner_repair.CRASHED not in update["scaffold_result"]
    assert "junit_runner.py" in asked[0] and "can only join an iterable" in asked[0]
    _, record = contract.the_pack(tmp_path)
    assert record["setup"]["kept"]["junit_runner.py"] == REPAIRED, "the repaired runner is the one kept"
    assert (project / "acceptance" / "test_imports.py").read_text() == A_SUITE_TEST, "the suite is the writers'"
    assert not list(project.rglob(f"*{runner_check.STEM}*.py"))


def test_a_repair_that_still_crashes_is_asked_again_then_stops_the_run(tmp_path):
    _a_proven_setup(tmp_path)

    again, _ = _the_repair(tmp_path, RUNNER)
    assert again["stage"] == "scaffold"
    assert "cannot report a failing test" in again["scaffold_result"][runner_repair.CRASHED]["problem"]

    stopped, _ = _the_repair(tmp_path, RUNNER, repairs=runner_repair.MAX_REPAIRS - 1)
    assert stopped["stage"] == "failed" and "junit_runner.py" in stopped["error"]


def test_what_the_setup_stage_is_asked_avoids_the_banned_words():
    crash = {"file": "junit_runner.py", "line": 86, "traceback": "", "problem": ""}
    text = runner_repair.request("text-toolkit-library", crash, "test-results/acceptance.xml", COMMAND,
                                 ["junit_runner.py"])["messages"][0]["content"]
    assert "junit_runner.py" in text and not BANNED.search(text)
