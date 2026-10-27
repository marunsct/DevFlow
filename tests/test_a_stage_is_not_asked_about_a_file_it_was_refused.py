"""A stage is asked to fix what the language service underlines only in files it wrote, not ones it was refused.

Measured on one run: QA tried to edit the product's `src/app.ts`, which only the product's builders may
write, and was refused. The check that asks a stage once to fix certain errors in the files it touched
counted the refused call, found the product's missing import there, and asked QA to fix it; QA spent
sixteen more refused writes on a product file in each of its passes.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app.graph import workflow


def test_a_refused_write_does_not_make_the_file_the_stage_s(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.ts").write_text("import { x } from './missing.ts';\n")
    found = SimpleNamespace(here=[{"line": 1, "message": "Cannot find module './missing.ts'.", "code": 2307}])
    monkeypatch.setattr("app.analysis.language_service.underlined_any", lambda *a, **k: found)
    result = {"messages": [
        AIMessage(content="", tool_calls=[{"name": "edit_artifact", "id": "c1", "args": {"relative_path": "app.ts"}}]),
        ToolMessage(content='{"error": "\'app.ts\' is not part of the acceptance suite."}', tool_call_id="c1"),
    ]}

    diagnostics = workflow._diagnostics_in_files_touched(
        {"repository": SimpleNamespace(root_path=str(tmp_path))}, result, SimpleNamespace(changed_files=[]))

    assert diagnostics == []


def test_a_file_it_wrote_is_still_checked(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.ts").write_text("import { x } from './missing.ts';\n")
    found = SimpleNamespace(here=[{"line": 1, "message": "Cannot find module './missing.ts'.", "code": 2307}])
    monkeypatch.setattr("app.analysis.language_service.underlined_any", lambda *a, **k: found)
    result = {"messages": [
        AIMessage(content="", tool_calls=[{"name": "edit_artifact", "id": "c1", "args": {"relative_path": "app.ts"}}]),
        ToolMessage(content='{"status": "written"}', tool_call_id="c1"),
    ]}

    diagnostics = workflow._diagnostics_in_files_touched(
        {"repository": SimpleNamespace(root_path=str(tmp_path))}, result, SimpleNamespace(changed_files=[]))

    assert len(diagnostics) == 1 and "app.ts" in diagnostics[0]
