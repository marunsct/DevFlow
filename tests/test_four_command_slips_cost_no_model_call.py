"""Four command slips are absorbed or explained instead of costing a model call each (TR.9).

Measured over 26 runs (tool review 2026-11-26), each captured here as the model sent it:
- `["cd", "/workspace/tasks-api", "&&", "python", "-m", "pytest", ...]` refused as "'/workspace/tasks-api' is not a
  directory in this workspace", the sandbox's own mount, which every command's output shows;
- `["tasks-api/.venv/bin/python", "-m", "pytest", ...]` with `working_directory` `tasks-api`: exit 127, 7 calls in 3
  runs. The doubled folder was not taken off because the virtualenv's `python` is a link to the sandbox image's
  interpreter, which the worker does not have;
- `["ls", "-la", "/workspace/tasks-api/.venv/bin/python*"]`: 9 of 9 such calls failed and nothing said why;
- `["python3", "-m", "py_compile", ...]` refused as able to "execute arbitrary code".
"""
from __future__ import annotations

import json
import os
import re

import pytest

from app.tools.agent_toolkit import build_terminal_command_tool

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _a_tool_whose_sandbox_answers(tmp_path, monkeypatch, answer: dict) -> tuple:
    """The terminal tool over `tmp_path`, its sandbox stubbed to answer `answer`, and the calls the sandbox got."""
    from app.tools.sandbox import SandboxExecutor

    calls: list = []
    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(
        lambda **kw: calls.append((kw["command"], kw.get("working_directory"))) or dict(answer)))
    return build_terminal_command_tool(str(tmp_path), "backend"), calls


def test_a_cd_into_the_sandbox_s_mount_runs_the_command_in_the_project(tmp_path, monkeypatch):
    (tmp_path / "tasks-api").mkdir()
    tool, calls = _a_tool_whose_sandbox_answers(tmp_path, monkeypatch, {"returncode": "0"})

    tool.func(command=["cd", "/workspace/tasks-api", "&&", "python", "-m", "pytest",
                       "tests/test_routes.py::TestSignup::test_create_user_returns_201", "-v", "--tb=short"])

    assert calls == [(["python", "-m", "pytest", "tests/test_routes.py::TestSignup::test_create_user_returns_201",
                       "-v", "--tb=short"], "tasks-api")]


def test_a_program_path_that_repeats_the_working_directory_is_shortened(tmp_path):
    """The virtualenv's interpreter is a link whose target exists only in the sandbox image."""
    from app.tools.sandbox import strip_a_doubled_working_directory

    (tmp_path / "tasks-api" / ".venv" / "bin").mkdir(parents=True)
    os.symlink("/nowhere-in-this-worker/python3", tmp_path / "tasks-api" / ".venv" / "bin" / "python")

    argv, note = strip_a_doubled_working_directory(
        ["tasks-api/.venv/bin/python", "-m", "pytest", "tests/test_schemas.py", "-q", "--tb=short"],
        str(tmp_path), "tasks-api")

    assert argv == [".venv/bin/python", "-m", "pytest", "tests/test_schemas.py", "-q", "--tb=short"]
    assert "tasks-api" in note


#: The sandbox's answer to `["ls", "-la", "/workspace/tasks-api/.venv/bin/python*"]`, as captured.
_A_STAR_TAKEN_AS_WRITTEN = {
    "stdout": "",
    "stderr": "ls: cannot access '/workspace/tasks-api/.venv/bin/python*': No such file or directory\n",
    "returncode": "2",
    "network": "none",
}


def test_a_star_the_program_took_as_written_is_explained(tmp_path, monkeypatch):
    tool, _ = _a_tool_whose_sandbox_answers(tmp_path, monkeypatch, _A_STAR_TAKEN_AS_WRITTEN)

    result = tool.func(command=["ls", "-la", "/workspace/tasks-api/.venv/bin/python*"])

    assert "no shell" in result["note"]
    assert json.dumps(["find", "/workspace/tasks-api/.venv/bin", "-maxdepth", "1", "-name", "python*"]) in result["note"]
    harness_s_words = result["note"].replace("/workspace/tasks-api", "")
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", harness_s_words, re.IGNORECASE), word


def test_a_star_a_program_matches_itself_gets_no_note(tmp_path, monkeypatch):
    tool, _ = _a_tool_whose_sandbox_answers(tmp_path, monkeypatch, {
        "stdout": "./.venv/bin/python3\n", "stderr": "", "returncode": "0"})

    result = tool.func(command=["find", ".venv/bin", "-name", "python*"])

    assert "note" not in result


def test_compiling_a_file_to_check_it_is_permitted(tmp_path):
    from app.tools.sandbox import STACK_MARKER, validate_command

    (tmp_path / STACK_MARKER).write_text("python", encoding="utf-8")

    argv = validate_command(["python3", "-m", "py_compile", "tmp-inline-3ed15a9c.py"],
                            role_name="backend_specialist", repo_root=tmp_path)

    assert argv == ["python3", "-m", "py_compile", "tmp-inline-3ed15a9c.py"]


def test_a_module_that_serves_is_still_refused(tmp_path):
    from app.tools.sandbox import STACK_MARKER, CommandNotAllowed, validate_command

    (tmp_path / STACK_MARKER).write_text("python", encoding="utf-8")

    with pytest.raises(CommandNotAllowed):
        validate_command(["python3", "-m", "http.server"], role_name="backend_specialist", repo_root=tmp_path)
