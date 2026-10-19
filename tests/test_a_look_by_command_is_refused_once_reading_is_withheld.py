"""Once a stage's reading is withheld, the command tool does not read for it.

Measured live: a fixer had its read tools withheld for re-reading files it
already held. It then read the same files with `cat` and listed the same
folders with `ls` through the command tool, about ten calls in two minutes,
until its budget ran out with nothing written.
"""
from __future__ import annotations

import re

import pytest

from app.agents import settled_answer
from app.tools import seen_content
from app.tools import agent_toolkit
from app.tools.agent_toolkit import build_terminal_command_tool

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def ran(monkeypatch):
    calls = []
    from app.tools.sandbox import SandboxExecutor

    seen_content.forget_everything()

    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(lambda **kw: calls.append(kw["command"]) or {"returncode": "0"}))
    return calls


def _run(tmp_path, argv):
    return build_terminal_command_tool(str(tmp_path), "ui_ux").func(command=argv)


def _workspace(tmp_path):
    """Two files the stage has seen as they are, as the memory hands them over."""
    files = {"app/src/App.tsx": "export const App = () => null;\n", "app/src/main.tsx": "import { App } from './App';\n"}
    for relative, text in files.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(text)
        seen_content.remember(relative, text)
    return tmp_path


def test_a_look_is_refused_once_reading_is_withheld(tmp_path, monkeypatch, ran):
    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: True)
    _workspace(tmp_path)

    result = _run(tmp_path, ["cat", "app/src/App.tsx"])

    assert ran == []
    assert "reading is done for this stage" in result["error"]
    assert not BANNED.search(result["error"])


def test_other_commands_still_run(tmp_path, monkeypatch, ran):
    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: True)

    _run(tmp_path, ["npm", "run", "build"])

    assert ran == [["npm", "run", "build"]]


def test_a_look_runs_while_reading_is_allowed(tmp_path, monkeypatch, ran):
    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: False)

    _run(tmp_path, ["ls", "app"])

    assert ran == [["ls", "app"]]


class TestALookAtWhatTheMemoryDoesNotHoldStillRuns:
    """Measured live: 49 of 70 refused looks were at what the memory never shows -
    `ls .venv/bin/python`, `ls dist` (the build's output), `find data -type f` (where
    a stale database was) - and each was told it only showed what it already had."""

    @pytest.fixture(autouse=True)
    def _withheld(self, monkeypatch):
        monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: True)

    def test_a_folder_of_files_the_memory_holds_is_refused(self, tmp_path, ran):
        _workspace(tmp_path)
        assert "reading is done" in _run(tmp_path, ["ls", "app/src"])["error"]
        assert "reading is done" in _run(tmp_path, ["head", "-n", "20", "app/src/main.tsx"])["error"]
        assert ran == []

    def test_an_installed_or_built_folder_runs(self, tmp_path, ran):
        _workspace(tmp_path)
        (tmp_path / "app" / ".venv" / "bin").mkdir(parents=True)
        (tmp_path / "app" / ".venv" / "bin" / "python").write_text("")
        (tmp_path / "app" / "dist").mkdir()
        (tmp_path / "app" / "dist" / "index.js").write_text("x")

        _run(tmp_path, ["ls", "app/.venv/bin/python"])
        _run(tmp_path, ["ls", "app/dist"])

        assert ran == [["ls", "app/.venv/bin/python"], ["ls", "app/dist"]]

    def test_a_folder_holding_what_is_not_text_runs(self, tmp_path, ran):
        _workspace(tmp_path)
        (tmp_path / "app" / "data").mkdir()
        (tmp_path / "app" / "data" / "app.db").write_bytes(b"SQLite format 3\x00")

        _run(tmp_path, ["find", "app/data", "-type", "f"])

        assert ran == [["find", "app/data", "-type", "f"]]

    def test_a_path_that_is_not_there_runs_and_says_so_itself(self, tmp_path, ran):
        _workspace(tmp_path)
        _run(tmp_path, ["ls", "app/missing"])
        assert ran == [["ls", "app/missing"]]

    def test_the_working_directory_is_where_a_path_is_looked_up(self, tmp_path, ran):
        _workspace(tmp_path)
        tool = build_terminal_command_tool(str(tmp_path), "ui_ux")
        assert "reading is done" in tool.func(command=["ls", "src"], working_directory="app")["error"]

    def test_a_file_the_memory_names_but_this_stage_never_saw_is_read(self, tmp_path, ran):
        _workspace(tmp_path)
        (tmp_path / "app" / "src" / "store.ts").write_text("export const store = {};\n")

        _run(tmp_path, ["cat", "app/src/store.ts"])

        assert ran == [["cat", "app/src/store.ts"]]

    def test_a_file_changed_since_the_stage_saw_it_is_read(self, tmp_path, ran):
        _workspace(tmp_path)
        (tmp_path / "app" / "src" / "App.tsx").write_text("export const App = () => 'changed';\n")

        _run(tmp_path, ["cat", "app/src/App.tsx"])

        assert ran == [["cat", "app/src/App.tsx"]]

