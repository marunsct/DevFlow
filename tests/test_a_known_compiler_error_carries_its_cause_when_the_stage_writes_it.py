"""A compiler error the stack pack knows carries its cause the moment the stage that wrote it is told of it.

Deep review 2026-11-18, item E4: a pack's known causes (`StackPack.known_errors`) were added only at triage, after a
test round had failed on the error - measured on Rust runs, `axum::test` (which does not exist) survived two fix
rounds. The stage that wrote the file was told the compiler's message alone, when one change would have fixed it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app.graph import workflow
from app.stacks import contract
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes_in_lines
from app.stacks.packs.rust_axum_api import PACK as RUST

AXUM_TEST = "error[E0433]: failed to resolve: could not find `test` in `axum`"


def _rust_workspace(root: Path) -> Path:
    contract.write(root, RUST, "notes", "Notes", package="notes")
    (root / "notes" / "tests").mkdir(parents=True)
    (root / "notes" / "tests" / "notes.rs").write_text("use axum::test::TestClient;\n")
    return root


def test_a_line_naming_a_known_error_gets_its_cause_and_others_stay_as_they_were(tmp_path):
    root = _rust_workspace(tmp_path)

    known, other = with_known_causes_in_lines(root, [f"- In `x.rs` line 1: {AXUM_TEST}", "- In `x.rs` line 2: E0308"])

    assert KNOWN_CAUSE in known and "oneshot" in known
    assert other == "- In `x.rs` line 2: E0308"


def test_the_stage_that_wrote_the_file_is_told_the_cause_with_the_compiler_s_error(tmp_path, monkeypatch):
    root = _rust_workspace(tmp_path)
    # The compiler runs in the sandbox; its answer is the input here.
    monkeypatch.setattr("app.analysis.compiler_check.findings",
                        lambda *a, **k: [{"file": "notes/tests/notes.rs", "line": 1, "message": AXUM_TEST, "code": "error"}])
    result = {"messages": [
        AIMessage(content="", tool_calls=[{"name": "write_artifact", "id": "c1",
                                           "args": {"relative_path": "notes/tests/notes.rs"}}]),
        ToolMessage(content='{"status": "written"}', tool_call_id="c1"),
    ]}

    told = workflow._diagnostics_in_files_touched(
        {"repository": SimpleNamespace(root_path=str(root))}, result, SimpleNamespace(changed_files=[]), "fix_1")

    assert len(told) == 1 and AXUM_TEST in told[0]
    assert KNOWN_CAUSE in told[0] and "tower::ServiceExt::oneshot" in told[0]
