"""Tests for the in-stage syntax and reference error interceptor (Pillar 7).

Catches syntax, import, and reference errors in files modified during a stage,
asking the agent once to fix them before completing the stage rather than
deferring them to multi-minute test rounds and defect triage.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def test_interceptor_prompt_contains_no_banned_words() -> None:
    from app.graph import workflow

    asked: dict[str, Any] = {}

    def _mock_nudge(agent, thread, callbacks, previous, schema, run_id, stage, text=None):
        asked["text"] = text
        return None

    original = workflow._nudge_for_the_structured_response
    workflow._nudge_for_the_structured_response = _mock_nudge
    try:
        diagnostics = ["- In `src/app.js` line 12: `undefinedVar` is not defined"]
        workflow._ask_about_high_confidence_diagnostics(
            None, "test-thread", [], diagnostics, None, "specialist_ui_ux_0"
        )
    finally:
        workflow._nudge_for_the_structured_response = original

    text = asked.get("text", "")
    assert text, "Prompt text must not be empty"
    assert "undefinedVar" in text

    outside = re.sub(r"`[^`]*`", "", text).lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", outside), f"Banned word '{word}' found in prompt: {text}"


def test_diagnostics_in_files_touched_finds_underlined_issues(tmp_path: Path) -> None:
    from app.graph import workflow

    js_file = tmp_path / "app.js"
    # An undeclared global / missing import in strict context
    js_file.write_text("export function run() { return nonExistentSymbol(); }\n", encoding="utf-8")

    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
    }
    result = {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "write_artifact", "id": "call-1", "args": {"relative_path": "app.js"}}]),
            ToolMessage(content='{"status": "written"}', tool_call_id="call-1"),
        ]
    }
    structured_response = SimpleNamespace(changed_files=["app.js"])

    # If underlined_any flags nonExistentSymbol (diagnostic 2304 / 2552),
    # _diagnostics_in_files_touched returns the finding.
    # We mock underlined_any to verify the extraction logic.
    mock_underlined = SimpleNamespace(
        here=[{"line": 1, "message": "Cannot find name 'nonExistentSymbol'.", "code": 2304}]
    )

    import app.analysis.language_service as ls
    orig_underlined = ls.underlined_any
    ls.underlined_any = lambda repo_root, target, content, project=None: mock_underlined
    try:
        diagnostics = workflow._diagnostics_in_files_touched(state, result, structured_response)
        assert len(diagnostics) == 1
        assert "app.js" in diagnostics[0]
        assert "nonExistentSymbol" in diagnostics[0]
    finally:
        ls.underlined_any = orig_underlined


def test_diagnostics_in_files_touched_ignores_clean_and_scratch_files(tmp_path: Path) -> None:
    from app.graph import workflow

    scratch_file = tmp_path / "tmp-check.js"
    scratch_file.write_text("export const x = 1;\n", encoding="utf-8")

    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
    }
    result = {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "write_artifact", "id": "call-1", "args": {"relative_path": "tmp-check.js"}}]),
            ToolMessage(content='{"status": "written"}', tool_call_id="call-1"),
        ]
    }
    structured_response = SimpleNamespace(changed_files=["tmp-check.js"])

    mock_underlined = SimpleNamespace(
        here=[{"line": 1, "message": "Cannot find name 'badSymbol'.", "code": 2304}]
    )
    import app.analysis.language_service as ls
    orig_underlined = ls.underlined_any
    ls.underlined_any = lambda repo_root, target, content, project=None: mock_underlined
    try:
        diagnostics = workflow._diagnostics_in_files_touched(state, result, structured_response)
        # Scratch files must be skipped
        assert diagnostics == []
    finally:
        ls.underlined_any = orig_underlined

