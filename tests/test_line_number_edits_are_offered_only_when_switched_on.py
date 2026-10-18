"""Line-number edits are offered only when switched on; the prompt names only the tools offered.

Measured across four runs: 51 of 81 `replace_lines` calls failed (62%),
against 7% for `edit_artifact` and `write_artifact`.
"""

from __future__ import annotations

import re

from app.agents import role_agent
from app.agents.role_agent import _WRITING_RULES, without_line_edits

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _names(tools):
    return [getattr(tool, "name", "") for tool in tools]


def test_by_default_no_stage_is_offered_line_edits_or_told_of_them(monkeypatch, tmp_path):
    monkeypatch.delenv("LINE_EDITS", raising=False)
    builder = role_agent.writing_tools

    assert "replace_lines" not in _names(builder(str(tmp_path)))
    told = without_line_edits(_WRITING_RULES)
    assert "replace_lines" not in told and "`edit_artifact`" in told
    assert "change    `edit_artifact`" in told and "expect_end" not in told


def test_switched_on_they_are_offered_and_described(monkeypatch, tmp_path):
    monkeypatch.setenv("LINE_EDITS", "on")
    builder = role_agent.writing_tools

    assert "replace_lines" in _names(builder(str(tmp_path)))
    assert without_line_edits(_WRITING_RULES) == _WRITING_RULES
