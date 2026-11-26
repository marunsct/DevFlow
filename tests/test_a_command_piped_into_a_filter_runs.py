"""`a | b` is read as the commands it runs: `a` runs, and the filter `b` is applied to what it printed (plan PA.6).

Measured over 120 runs' transcripts: 27 commands piped into a filter of their output were refused ("'|' is a shell
operator and there is no shell here"), each a model call to send it again. The commands below are those calls as
they were sent; the outputs are a test runner's own, captured whole.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.tools.agent_toolkit import build_terminal_command_tool

CAPTURED = Path(__file__).parent / "captured"
PYTEST = json.loads((CAPTURED / "pytest-9.2-failed-passed-and-errors.json").read_text(encoding="utf-8"))
PLAYWRIGHT = (CAPTURED / "playwright-1.64-summary-of-a-run-over-a-minute.txt").read_text(encoding="utf-8")
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def ran(monkeypatch):
    """The sandbox's container: records what it is asked to run and prints what `printed` holds."""
    calls: list = []
    printed: dict = {"stdout": "", "stderr": ""}
    from app.tools.sandbox import SandboxExecutor

    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(
        lambda **kw: calls.append((kw["command"], kw.get("working_directory")))
        or {"stdout": printed["stdout"], "stderr": printed["stderr"], "returncode": "1"}))
    return calls, printed


def _run(tmp_path, argv, working_directory=None, role="backend_specialist"):
    for folder in ("tasks-api", "bookmarks", "notes-api"):
        (tmp_path / folder).mkdir(exist_ok=True)
    return build_terminal_command_tool(str(tmp_path), role).func(command=argv, working_directory=working_directory)


def test_a_test_run_piped_into_head_runs_and_shows_its_first_lines(tmp_path, ran):
    calls, printed = ran
    printed.update(stdout=PYTEST["stdout"], stderr=PYTEST["stderr"])

    result = _run(tmp_path, ["cd", "tasks-api", "&&",
                             ".venv/bin/python -m pytest tests/test_app.py -q --tb=short 2>&1 | head -80"],
                  working_directory="tasks-api")

    assert calls == [([".venv/bin/python", "-m", "pytest", "tests/test_app.py", "-q", "--tb=short"], "tasks-api")]
    assert result["stdout"].splitlines() == (PYTEST["stdout"] + PYTEST["stderr"]).splitlines()[:80]
    assert result["returncode"] == "1"
    assert "head -80" in result["note"] and "exit code" in result["note"]


def test_a_suite_piped_into_tail_shows_its_last_lines(tmp_path, ran):
    calls, printed = ran
    printed["stdout"] = PLAYWRIGHT

    result = _run(tmp_path, ["cd", "bookmarks", "&&", "npm", "run", "test:acceptance", "2>&1", "|", "tail", "-100"],
                  working_directory="bookmarks")

    assert calls == [(["npm", "run", "test:acceptance"], "bookmarks")]
    assert result["stdout"].splitlines() == PLAYWRIGHT.splitlines()[-100:]


def test_a_run_piped_into_grep_shows_only_the_lines_it_matches(tmp_path, ran):
    calls, printed = ran
    printed["stdout"] = PLAYWRIGHT

    result = _run(tmp_path, ["npm", "run", "test:acceptance", "2>&1", "|", "grep", "-E", r"(failed|passed|\[AC-11\])"],
                  working_directory="bookmarks")

    kept = result["stdout"].splitlines()
    assert kept and all(re.search(r"failed|passed|\[AC-11\]", line) for line in kept)
    assert kept == [line for line in PLAYWRIGHT.splitlines() if re.search(r"failed|passed|\[AC-11\]", line)]


def test_a_filter_the_role_may_not_run_is_refused_as_itself(tmp_path, ran):
    calls, _ = ran

    result = _run(tmp_path, ["sed", "-n", "834p", "tasks-api/tests/test_app.py", "|", "cat", "-A"],
                  working_directory="tasks-api", role="testing_specialist")

    assert calls == []
    assert "error" in result


@pytest.mark.parametrize("argv", [
    ["cat", "notes-api/src/Service.php", "|", "xargs", "rm"],
    ["cat", "notes-api/src/Service.php", "|", "grep", "-q", "x", "other.txt"],
])
def test_a_command_after_the_pipe_that_is_no_filter_is_refused_saying_why(tmp_path, ran, argv):
    calls, _ = ran

    result = _run(tmp_path, argv, working_directory="notes-api")

    assert calls == []
    assert "Run the command before the `|` alone" in result["error"] or "not permitted" in result["error"]


def test_a_bar_inside_an_argument_is_no_pipe(tmp_path, ran):
    calls, _ = ran

    _run(tmp_path, ["grep", "-E", "a|b", "src/app.py"], working_directory="notes-api")

    assert calls == [(["grep", "-E", "a|b", "src/app.py"], "notes-api")]


def test_what_the_tool_says_of_pipes_names_no_product_and_no_control(tmp_path):
    from app.tools.piped_commands import refusal

    tool = build_terminal_command_tool(str(tmp_path), "backend_specialist")
    said = tool.description + refusal([["xargs", "rm"]], "backend_specialist", str(tmp_path))

    assert "applied by the harness" in " ".join(tool.description.split())
    assert not BANNED.search(said)


def test_a_plan_s_command_piped_into_a_filter_is_not_sent_back(tmp_path):
    """The lead's plan is checked the same way: a pipe into a filter runs, so it is no reason to send the plan back."""
    from app.analysis.planned_commands import commands_the_sandbox_would_refuse

    said = commands_the_sandbox_would_refuse(
        "Verify with `npm run test:acceptance 2>&1 | tail -100` and `cat notes-api/src/Service.php | xargs rm`.",
        "backend_specialist", str(tmp_path))

    assert not any("test:acceptance" in note for note in said)
    assert any("xargs rm" in note for note in said)
