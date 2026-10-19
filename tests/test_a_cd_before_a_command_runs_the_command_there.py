"""`cd <folder> <command>` runs the command in that folder instead of being refused.

Measured live: `["cd", "task-management-dashboard", ".venv/bin/python", "-m", "pip",
"list"]` was refused three times in one run ("`cd` is not a program. Pass
`working_directory`"), five in another - each a model call to say what the argv
already said.
"""
from __future__ import annotations

import pytest

from app.tools.agent_toolkit import build_terminal_command_tool


@pytest.fixture
def ran(monkeypatch):
    calls = []
    from app.tools.sandbox import SandboxExecutor

    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(
        lambda **kw: calls.append((kw["command"], kw.get("working_directory"))) or {"returncode": "0"}))
    return calls


def _run(tmp_path, argv, working_directory=None):
    (tmp_path / "shop").mkdir(exist_ok=True)
    tool = build_terminal_command_tool(str(tmp_path), "backend")
    return tool.func(command=argv, working_directory=working_directory)


def test_the_command_runs_in_the_folder(tmp_path, ran):
    result = _run(tmp_path, ["cd", "shop", ".venv/bin/python", "-m", "pip", "list"])

    assert ran == [([".venv/bin/python", "-m", "pip", "list"], "shop")]
    assert "working_directory" in str(result.get("note"))


def test_an_and_after_the_folder_is_dropped(tmp_path, ran):
    _run(tmp_path, ["cd", "shop", "&&", "npm", "test"])

    assert ran == [(["npm", "test"], "shop")]


def test_the_folder_is_taken_from_the_working_directory_given(tmp_path, ran):
    (tmp_path / "shop" / "web").mkdir(parents=True)
    _run(tmp_path, ["cd", "web", "npm", "test"], working_directory="shop")

    assert ran == [(["npm", "test"], "shop/web")]


def test_a_cd_alone_is_left_to_the_refusal(tmp_path, ran):
    _run(tmp_path, ["cd", "shop"])

    assert ran == [(["cd", "shop"], None)]


def test_the_note_holds_to_the_house_rules(tmp_path, ran):
    import re

    note = _run(tmp_path, ["cd", "shop", "npm", "test"])["note"]
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", note, re.I)
