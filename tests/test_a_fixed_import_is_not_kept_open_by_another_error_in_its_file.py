"""A fixed compiler finding is not kept open by a different error in the same file.

Measured on two Rust runs: a defect that had merged other checks' reports of the same import was recorded "left open -
the language service still reports it" after the import was fixed, because any other error in the file - a borrow
error forty lines on - counted as the merged defect's.
"""
from __future__ import annotations

import pytest

from app.analysis import compiler_check
from app.graph import engineering

IMPORT = ("unresolved import `axum::extract::DefaultBodyLayer`: no `DefaultBodyLayer` in `extract`, "
          "help: a similar name exists in the module: `DefaultBodyLimit`")
DESCRIPTION = (f"notes-api/src/lib.rs line 3: {IMPORT}{engineering.FAILS_WHEN_IT_RUNS}{engineering.SAME_PROBLEM_ELSEWHERE}"
               f"- [language service] notes-api/src/lib.rs line 3: {IMPORT[:120]}")


@pytest.mark.parametrize("reported, still", [
    ([("notes-api/src/lib.rs", "cannot borrow `notes` as immutable because it is also borrowed as mutable")], False),
    ([("notes-api/src/lib.rs", IMPORT)], True),
    ([], False),
], ids=["only-another-error-is-left", "the-import-is-still-there", "nothing-is-left"])
def test_the_finding_holds_only_while_its_own_message_is_reported(tmp_path, monkeypatch, reported, still):
    (tmp_path / "notes-api" / "src").mkdir(parents=True)
    (tmp_path / "notes-api" / "src" / "lib.rs").write_text("use axum::Router;\n")
    monkeypatch.setattr(compiler_check, "findings",  # the compiler is the edge
                        lambda root, project, files: [{"file": f, "line": 1, "message": m} for f, m in reported])

    assert engineering.still_underlined(str(tmp_path), DESCRIPTION) is still
