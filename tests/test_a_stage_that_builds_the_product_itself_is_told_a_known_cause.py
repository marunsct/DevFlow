"""A building stage is told the cause of an error its stack pack knows on every path it meets the error.

Measured on a Rust run: three building stages ran `cargo build` themselves and read in its output an error the pack
could name (an axum 0.8 extractor under `#[async_trait]`, E0195). The pack's causes reached only a defect at triage
and the lines of the harness's own build check - and in the note that sends a builder back before the unit tests, a
cause following a long error line would be cut by the line's bound.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.graph.built_before_testing import the_note
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes_in_lines
from app.tools.agent_toolkit import build_terminal_command_tool

CAPTURED = Path(__file__).parent / "captured"
# What `cargo build` printed on axum 0.8.9, rustc 1.85: E0195 on the extractor, then E0599 and E0308.
CARGO_BUILD = (CAPTURED / "cargo-build-rustc-1.85-axum-0.8.9-extractor-under-async-trait.txt").read_text(encoding="utf-8")
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
E0195 = ("lifetime parameters or bounds on associated function `from_request_parts` do not match the trait "
         "declaration: lifetimes do not match associated function in trait")


@pytest.fixture
def printed(monkeypatch):
    """The sandbox's container: it prints what the test puts here, with its exit code."""
    out: dict = {"stdout": "", "stderr": "", "returncode": "0"}
    from app.tools.sandbox import SandboxExecutor

    monkeypatch.setattr(SandboxExecutor, "execute", staticmethod(lambda **kw: dict(out)))
    return out


def _cargo_build(root: Path, pack: str = "rust-axum-api") -> dict:
    contract.write(root, pack_named(pack), "notes-api", "Notes")
    (root / "notes-api").mkdir(exist_ok=True)
    tool = build_terminal_command_tool(str(root), "backend_specialist")
    return tool.func(command=["cargo", "build"], working_directory="notes-api")


def test_a_failed_build_s_known_errors_come_with_their_causes(tmp_path, printed):
    printed.update(stderr=CARGO_BUILD, returncode="101")

    result = _cargo_build(tmp_path)

    note = result["note"]
    assert KNOWN_CAUSE in note
    assert "delete that attribute line above the `impl`" in note  # E0195, the extractor under `#[async_trait]`
    assert "`pub fn routes() -> Router<AppState>`" in note  # E0308, `.with_state` on a `Router<()>`
    assert result["stderr"] == CARGO_BUILD
    assert not BANNED.search(note)


def test_a_build_that_passed_is_given_no_cause(tmp_path, printed):
    printed.update(stderr="warning: unused import: `tower::Limit` in a comment `from_request_parts` do not match the "
                          "trait declaration", returncode="0")

    assert "note" not in _cargo_build(tmp_path)


def test_another_stack_s_project_is_not_given_the_rust_causes(tmp_path, printed):
    printed.update(stderr=CARGO_BUILD, returncode="101")

    assert KNOWN_CAUSE not in str(_cargo_build(tmp_path, "go-http-api").get("note") or "")


def test_a_builder_sent_back_for_the_build_reads_the_cause_whole(tmp_path):
    contract.write(tmp_path, pack_named("rust-axum-api"), "notes-api", "Notes")
    lines = with_known_causes_in_lines(tmp_path, [
        f"- In `notes-api/src/db.rs` line 162: {E0195} (the compiler)",
        f"- In `notes-api/src/db.rs` line 210: {E0195} (the compiler)",
    ])

    note = the_note(lines)

    assert "remove `async-trait` from `Cargo.toml` when nothing else uses it" in note
    assert "there the `impl` needs the attribute too." in note  # the cause's last words: not cut
    assert note.count(KNOWN_CAUSE) == 1  # two errors with one cause: said once
    assert "line 162" in note and "line 210" in note
