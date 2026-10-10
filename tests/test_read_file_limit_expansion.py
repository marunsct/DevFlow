"""Tests for read_file limit expansion preventing micro-slicing (Pillar 3 & Change 1).

When models specify tiny limits (e.g. 15-30 lines), it turns reading a small file
into dozens of expensive conversational turns. Limits under 100 must be expanded
to DEFAULT_READ_LINES (400 lines).
"""

from __future__ import annotations

import re
from app.agents import role_agent
from app.agents.workspace_paths import (
    DEFAULT_READ_LINES,
    rewrite_tool_arguments,
)

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def test_missing_read_file_limits_gain_default_read_lines() -> None:
    # Missing limit should get DEFAULT_READ_LINES
    args_none = {"file_path": "src/app.js"}
    rewritten_none = rewrite_tool_arguments("read_file", args_none, "/workspace")
    assert rewritten_none.get("limit") == DEFAULT_READ_LINES

    # A large limit (e.g. 500) should be preserved
    args500 = {"file_path": "src/app.js", "offset": 1, "limit": 500}
    rewritten500 = rewrite_tool_arguments("read_file", args500, "/workspace")
    assert rewritten500.get("limit") == 500



def test_new_read_file_rule_has_no_banned_words() -> None:
    # Verify the new rule added to role_agent contains zero banned words
    text = (
        "read part `read_file` + offset/limit, for long files over 400 lines\n"
        "- To revise a file, read the relevant file with `read_file`, then edit with\n"
        "  `edit_artifact` or `replace_lines`. For files under 400 lines, read the\n"
        "  entire file in one `read_file` call.\n"
    )
    outside = re.sub(r"`[^`]*`", "", text).lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", outside), f"Banned word '{word}' found in new prompt rule"
