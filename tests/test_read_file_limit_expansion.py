"""Tests for read_file limit expansion preventing micro-slicing (Pillar 3 & Change 1).

When models specify tiny limits (e.g. 15-30 lines), it turns reading a small file
into dozens of expensive conversational turns. Limits under 100 must be expanded
to DEFAULT_READ_LINES (400 lines).
"""

from __future__ import annotations

from app.agents.workspace_paths import (
    DEFAULT_READ_LINES,
    rewrite_tool_arguments,
)


def test_missing_read_file_limits_gain_default_read_lines() -> None:
    # Missing limit should get DEFAULT_READ_LINES
    args_none = {"file_path": "src/app.js"}
    rewritten_none = rewrite_tool_arguments("read_file", args_none, "/workspace")
    assert rewritten_none.get("limit") == DEFAULT_READ_LINES

    # A large limit (e.g. 500) should be preserved
    args500 = {"file_path": "src/app.js", "offset": 1, "limit": 500}
    rewritten500 = rewrite_tool_arguments("read_file", args500, "/workspace")
    assert rewritten500.get("limit") == 500
