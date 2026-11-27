"""A fix's forward repair is handed the pack's known cause of the break it is to repair.

Measured on a Rust axum run: a fix's rewrite was told the known causes of `tower::Limit` and of E0308 "expected `()`,
found `AppState`" and removed the first; the fix still did not build, and its forward repair was handed the build's
output with neither cause. It rewrote `src/lib.rs` back to `tower::Limit` and `-> Router<AppState>`, as the
specification it was also shown said, and the fix was reverted.
"""
from __future__ import annotations

import re
from pathlib import Path

from app import ci
from app.graph import judged_fixes
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The start's failure after that fix, as the run's forward repair was shown it.
CAPTURED = Path(__file__).parent / "captured" / "cargo-start-axum-0.8.9-state-given-to-a-router-of-unit.txt"


def _given(root: Path, problem: str) -> str:
    contract.write(root, pack_named("rust-axum-api"), "notes-api", "Notes")
    before = ci.Snapshot(label="before", acceptance_ran=True, acceptance={"notes.spec.js › [AC-14] health": "passed"})
    after = ci.Snapshot(label="after", acceptance_ran=True, problem=problem)
    return judged_fixes.what_a_repair_is_given(root, before, after, ["acceptance: notes.spec.js › [AC-14] health"])


def test_the_repair_of_a_build_the_fix_broke_reads_the_known_cause(tmp_path):
    given = _given(tmp_path, CAPTURED.read_text(encoding="utf-8"))

    assert "expected `()`, found `AppState`" in given
    assert KNOWN_CAUSE in given
    assert "drop `.with_state(state)` instead" in given
    assert not BANNED.search(given)


def test_an_error_stated_early_in_a_long_build_still_brings_its_cause(tmp_path):
    """The repair is shown the end of the start's output; the error named at its top is read from the whole."""
    problem = ("error[E0432]: unresolved import `tower::Limit`: no `Limit` in the root\n"
               + "warning: unused import: `serde_json::json`\n" * 200
               + "error: could not compile `notes-api` (lib) due to 1 previous error")

    given = _given(tmp_path, problem)

    assert "unresolved import `tower::Limit`" not in given.split(KNOWN_CAUSE)[0]
    assert "`.layer(axum::extract::DefaultBodyLimit::max(<bytes>))`" in given
