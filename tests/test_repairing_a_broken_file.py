"""A file that is already broken must be repairable a piece at a time.

The write guard refuses any change that leaves a file the parser cannot read.
That is right when the change is what breaks it. It is a trap when the file
arrived broken: every partial repair still leaves the file broken, so every
partial repair is refused, and the only move left is rewriting the whole file
correctly in one call - which `write_artifact` also refuses if it is not
perfect.

Measured live on run-eb48de7a. `todo-app/main.js` had a duplicate `li`
declaration. `specialist_ui_ux_2` and `specialist_ui_ux_3` were refused four
consecutive edits, reported at lines 22, 59, 83 and 72. The moving line number
is the evidence: the model was getting closer each time and every step was
rejected for not finishing the job.

The rule here is the one a pre-merge gate uses: you may not make it worse. An
edit to an already-broken file is allowed through, and what remains wrong is
reported as a note so the model can take the next step.
"""

from __future__ import annotations

import pathlib

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    replace_approved_lines,
    write_approved_artifact,
)


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "p").mkdir()
    (tmp_path / ".project-directory").write_text("p", encoding="utf-8")
    return tmp_path


#: (filename, already-broken content, line to change, replacement)
BROKEN = [
    ("main.js", "const li = 1;\nconst li = 2;\nfunction f() {\n", 2, "const other = 2;"),
    ("a.py", "def f():\n    return (\nx = 1\n", 3, "y = 2"),
    ("b.json", '{\n  "a": 1,\n  "b":\n}\n', 3, '  "b": 2'),
    ("m.go", "package m\nfunc f() {\n", 1, "package main"),
]


@pytest.mark.parametrize("name,body,line,replacement", BROKEN, ids=lambda v: str(v)[:10])
def test_a_step_of_a_repair_is_allowed(workspace, name, body, line, replacement):
    target = workspace / "p" / name
    target.write_text(body, encoding="utf-8")

    result = replace_approved_lines(workspace, f"p/{name}", line, line, replacement)

    assert result["status"] == "edited"
    assert replacement.strip() in target.read_text(encoding="utf-8")


@pytest.mark.parametrize("name,body,line,replacement", BROKEN, ids=lambda v: str(v)[:10])
def test_the_model_is_told_what_is_still_wrong(workspace, name, body, line, replacement):
    target = workspace / "p" / name
    target.write_text(body, encoding="utf-8")

    result = replace_approved_lines(workspace, f"p/{name}", line, line, replacement)
    note = result.get("note") or ""

    if note:
        assert "still does not parse" in note or "already broken" in note
        assert "Nothing was written" not in note, (
            "the change is on disk; saying otherwise is the tool lying about what it did"
        )


def test_an_edit_that_breaks_a_healthy_file_is_still_refused(workspace):
    target = workspace / "p" / "ok.py"
    target.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        replace_approved_lines(workspace, "p/ok.py", 1, 1, "def f(:")

    assert target.read_text(encoding="utf-8") == "x = 1\n", "the file must be untouched"


def test_the_same_holds_for_edit_artifact(workspace):
    """Both targeted-change tools share the guard, so both must share the rule."""
    target = workspace / "p" / "t.js"
    target.write_text("const li = 1;\nconst li = 2;\nfunction f() {\n", encoding="utf-8")

    result = edit_approved_artifact(workspace, "p/t.js", "const li = 2;", "const b = 2;")

    assert result.get("status") in {"edited", "written"}
    assert "const b = 2;" in target.read_text(encoding="utf-8")


def test_a_whole_file_write_must_still_be_valid(workspace):
    """A targeted change is a repair step; a whole file is the finished article."""
    target = workspace / "p" / "w.py"
    target.write_text("def f():\n    return (\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        write_approved_artifact(workspace, "p/w.py", "def g(:\n")


def test_a_repair_that_completes_the_fix_reports_no_problem(workspace):
    target = workspace / "p" / "fix.py"
    target.write_text("def f():\n    return (\n", encoding="utf-8")

    result = replace_approved_lines(workspace, "p/fix.py", 2, 2, "    return 1")

    assert result["status"] == "edited"
    assert "still does not parse" not in (result.get("note") or "")
