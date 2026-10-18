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
from app.tools import agent_toolkit
from app.tools.agent_toolkit import build_terminal_command_tool

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def ran(monkeypatch):
    calls = []
    from app.tools.sandbox import SandboxExecutor

    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(lambda **kw: calls.append(kw["command"]) or {"returncode": "0"}))
    return calls


def _run(tmp_path, argv):
    return build_terminal_command_tool(str(tmp_path), "ui_ux").func(command=argv)


def test_a_look_is_refused_once_reading_is_withheld(tmp_path, monkeypatch, ran):
    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: True)

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
