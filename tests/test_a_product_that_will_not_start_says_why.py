"""When the suite cannot reach the product, the harness runs the project's own start command and the fixer sees what it wrote.

Measured on one run: "Server did not start in time" through three fix rounds, with a syntax error in the product's SQL
to read by simply running it. The sandbox here is the real one, in-container, and so is the command it runs.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.agents.specialists import ReportedDefect
from app.graph import acceptance_nodes, workflow
from app.tools import sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CAUSE = 'syntax error at or near "SELEC"'
JUNIT = ('<testsuite tests="2"><testcase classname="c" name="[AC-1] lists"><failure message="{m}">{m}</failure></testcase>'
         '<testcase classname="c" name="[AC-2] adds">{second}</testcase></testsuite>')


@pytest.fixture(autouse=True)
def the_real_sandbox(monkeypatch):
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")


def _project(root: Path, start: str | None = f"echo '{CAUSE}' >&2\nexit 3\n") -> Path:
    """A project no pack scaffolded: a locked suite that declares its own command, as a run with no pack has."""
    (root / ".project-directory").write_text("notes\n")
    project = root / "notes"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "test_x.py").write_text("def test_x(): pass\n")
    (project / "acceptance" / "run.json").write_text(json.dumps({"command": ["pytest"], "report": "r.xml"}))
    if start is not None:
        (project / "start.sh").write_text(start)
    suite.lock(root)
    return project


def _runner(project: Path, message: str, *, second_passes: bool = False):
    def run(argv, category, where):
        second = "" if second_passes else f'<failure message="{message}">{message}</failure>'
        (project / "r.xml").write_text(JUNIT.format(m=message, second=second))
        return {"returncode": "1", "stdout": "", "stderr": ""}
    return run


def test_a_suite_whose_own_test_threw_the_output_away_gets_it(tmp_path):
    project = _project(tmp_path)
    result = suite.run(tmp_path, runner=_runner(project, "Server did not start in time"))
    assert CAUSE in result.server_log
    assert "exit code 3" in result.server_log and "sh start.sh" in result.server_log


def test_one_test_s_own_start_is_enough_with_the_rest_of_the_suite_fine(tmp_path):
    project = _project(tmp_path)
    result = suite.run(tmp_path, runner=_runner(project, "Server did not start in time", second_passes=True))
    assert CAUSE in result.server_log


@pytest.mark.parametrize("message", ["failed on setup with ValueError: x", "beforeAll hook failed", "connect ECONNREFUSED 127.0.0.1:1"])
def test_a_whole_suite_erroring_at_setup_gets_it(tmp_path, message):
    project = _project(tmp_path)
    assert CAUSE in suite.run(tmp_path, runner=_runner(project, message)).server_log


def test_a_failure_of_its_own_runs_nothing(tmp_path, monkeypatch):
    project = _project(tmp_path)
    result = suite.run(tmp_path, runner=_runner(project, "expected 200, got 500"))
    assert CAUSE not in result.server_log


def test_a_suite_not_locked_yet_runs_nothing(tmp_path, monkeypatch):
    from app.acceptance import start_output

    _project(tmp_path)
    monkeypatch.setattr(suite, "is_locked", lambda _root: False)
    result = SimpleNamespace(problem=suite.PRODUCT_DID_NOT_START, server_log="", report=SimpleNamespace(tests=[]), exit_code=1)
    start_output.add_to(tmp_path, result)
    assert result.server_log == ""


def test_a_probe_s_run_on_a_product_broken_on_purpose_runs_nothing(tmp_path):
    project = _project(tmp_path)
    assert CAUSE not in suite.run(tmp_path, runner=_runner(project, "Server did not start in time"), save=False).server_log


def test_a_service_that_keeps_running_is_ended_by_the_sandbox_s_limit_and_says_so(tmp_path, monkeypatch):
    project = _project(tmp_path, "echo listening on $PORT\nexec sleep 30\n")
    monkeypatch.setitem(sandbox.TIMEOUTS, "start", 1)
    result = suite.run(tmp_path, runner=_runner(project, "Server did not start in time"))
    assert "still running after 1 seconds" in result.server_log
    assert re.search(r"listening on \d+", result.server_log)


def test_the_same_product_is_not_started_twice(tmp_path, monkeypatch):
    from app.acceptance import start_output
    from app.acceptance import unstable

    project = _project(tmp_path)
    calls = []
    real = start_output._execute
    monkeypatch.setattr(start_output, "_execute", lambda *a: (calls.append(a), real(*a))[1])
    monkeypatch.setattr(unstable, "unchanged_since_the_suite_measured", lambda _root: True)
    suite.run(tmp_path, runner=_runner(project, "Server did not start in time"))
    assert CAUSE in suite.run(tmp_path, runner=_runner(project, "Server did not start in time")).server_log
    assert len(calls) == 1


def test_no_process_is_signalled_from_the_harness_s_own_code():
    from app.acceptance import start_output

    source = inspect.getsource(start_output)
    assert not re.search(r"\b(?:killpg|kill|terminate|send_signal)\s*\(", source)
    assert "getpid" not in source


def test_it_never_raises(tmp_path, monkeypatch):
    from app.acceptance import start_output

    _project(tmp_path)

    def boom(*_):
        raise RuntimeError("boom")

    monkeypatch.setattr(start_output, "_execute", boom)
    assert start_output.what_it_wrote(tmp_path) == ""


def test_a_command_the_sandbox_refused_says_nothing(tmp_path, monkeypatch):
    from app.acceptance import start_output

    _project(tmp_path)
    monkeypatch.setattr(start_output, "_execute", lambda *_: {"error": "Not enough memory"})
    assert start_output.what_it_wrote(tmp_path) == ""


def test_an_agent_is_still_refused_the_command():
    outcome = sandbox.SandboxExecutor.execute(["sh", "-c", "echo hi"], repo_root="/tmp", role_name="testing_specialist", category="start")
    assert "error" in outcome and "returncode" not in outcome


# --- what a project with no pack can say of itself ---

@pytest.mark.parametrize(("files", "expected"), [
    ({"start.sh": "x"}, ["sh", "start.sh"]),
    ({"package.json": json.dumps({"scripts": {"start": "node a.js"}})}, ["npm", "start"]),
    ({"Procfile": "web: gunicorn app:app\nworker: x\n"}, ["sh", "-c", "gunicorn app:app"]),
    ({"Makefile": "build:\n\tx\nrun:\n\ty\n"}, ["make", "run"]),
    ({"app.py": ""}, ["python3", "app.py"]),
    ({"src/index.js": ""}, ["node", "src/index.js"]),
    ({"main.go": ""}, ["go", "run", "."]),
    ({"src/main.rs": ""}, ["cargo", "run"]),
    ({"start.sh": "x", "app.py": "", "package.json": json.dumps({"scripts": {"start": "y"}})}, ["sh", "start.sh"]),
    ({"README.md": "nothing to go on"}, None),
    ({"package.json": json.dumps({"scripts": {"test": "x"}})}, None),
    ({"package.json": "{not json"}, None),
])
def test_what_a_project_with_no_pack_can_say(tmp_path, files, expected):
    from app.acceptance import start_output

    (tmp_path / ".project-directory").write_text("p\n")
    for name, text in files.items():
        path = tmp_path / "p" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    command = start_output.command_for(tmp_path)
    assert (command[0] if command else None) == expected


def test_a_python_entry_runs_on_the_project_s_own_python(tmp_path):
    from app.acceptance import start_output

    (tmp_path / "app.py").write_text("")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("")
    assert start_output.command_for(tmp_path)[0] == [".venv/bin/python", "app.py"]


def test_a_pack_with_nothing_to_start_runs_nothing(tmp_path, monkeypatch):
    from app.acceptance import start_output
    from app.stacks import contract

    (tmp_path / "main.py").write_text("")
    monkeypatch.setattr(contract, "the_pack", lambda _r: (SimpleNamespace(kind="cli"), {"project": ""}))
    assert start_output.command_for(tmp_path) is None


# --- it reaches the fixer ---

def _measured(monkeypatch, tmp_path, saved, failing):
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda _s: (failing, "pytest"))
    monkeypatch.setattr(suite, "last_result", lambda _r: saved)
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda _s, _t: "backend")
    monkeypatch.setattr(acceptance_nodes, "_what_the_language_service_finds", lambda _s: [])
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


def _the_paragraph():
    from app.acceptance import start_output

    return f"{start_output.START_MARK} (`sh start.sh`): it stopped by itself with exit code 3. It wrote:\n{CAUSE}"


_FAILING = {"id": "AC-1", "text": "lists", "tests": [{"name": "[AC-1] lists", "outcome": "failed", "message": "Server did not start in time"}]}


def test_the_start_defect_carries_it(monkeypatch, tmp_path):
    state = _measured(monkeypatch, tmp_path, {"problem": suite.PRODUCT_DID_NOT_START + ": x", "server_log": _the_paragraph()}, [_FAILING])
    defects = acceptance_nodes.failing_due_defects(state, [])
    assert CAUSE in defects[0].actual_behavior


def test_a_criterion_s_defect_carries_it(monkeypatch, tmp_path):
    state = _measured(monkeypatch, tmp_path, {"server_log": _the_paragraph()}, [_FAILING])
    assert CAUSE in acceptance_nodes.failing_due_defects(state, [])[0].actual_behavior


def test_a_defect_the_round_wrote_itself_carries_it(monkeypatch, tmp_path):
    state = _measured(monkeypatch, tmp_path, {"server_log": _the_paragraph()}, [_FAILING])
    written = ReportedDefect(description="[AC-1] does not list", severity="major", reproduction_steps="r",
                             expected_behavior="e", actual_behavior="did not start", affected_files=[], owner="backend")
    acceptance_nodes.failing_due_defects(state, [written])
    assert CAUSE in written.actual_behavior


def test_a_merge_keeps_it():
    other = SimpleNamespace(actual_behavior=f"x\n{_the_paragraph()}")
    assert CAUSE in workflow._with_a_stopped_service_s_report(SimpleNamespace(actual_behavior="lead"), [other])


def test_its_words_name_nothing_banned():
    from app.acceptance import start_output

    assert not BANNED.search(start_output.START_MARK)
    assert not BANNED.search(_the_paragraph())
