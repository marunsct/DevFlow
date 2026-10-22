"""Content that is a diff of the file is refused even when it parses.

A fix stage sent this as a `replace_lines` content for three lines of
`src/model.js`:

    this.tasks.push(task);
    -      this._emitUpdate();
    +      storage.saveTasks(this.tasks);
    +      this._emitUpdate();

JavaScript reads `-x()` and `+x()` as unary minus and plus, so the parser
accepted it, the edit was written, and the product shipped with the diff in it.
"""

from __future__ import annotations

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    replace_approved_lines,
    write_approved_artifact,
)

MODEL = """\
export class Model {
  addTask(task) {
    this.tasks.push(task);
    this._emitUpdate();
  }
}
"""

DIFF = (
    "    this.tasks.push(task);\n"
    "-    this._emitUpdate();\n"
    "+    storage.saveTasks(this.tasks);\n"
    "+    this._emitUpdate();\n"
)


@pytest.fixture
def model(tmp_path):
    write_approved_artifact(tmp_path, "app/model.js", MODEL)
    return tmp_path


def test_a_line_edit_that_is_a_diff_is_refused(model) -> None:
    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(model, "app/model.js", 3, 4, DIFF)

    message = str(refused.value)
    assert "line 2 of what you sent is `-this._emitUpdate();`" in message
    assert "this is a diff" in message
    assert (model / "app" / "model.js").read_text(encoding="utf-8") == MODEL


def test_a_find_and_replace_that_is_a_diff_is_refused(model) -> None:
    with pytest.raises(RepositoryToolError, match="this is a diff"):
        edit_approved_artifact(
            model, "app/model.js", "    this.tasks.push(task);\n    this._emitUpdate();\n", DIFF
        )


def test_a_whole_file_that_is_a_diff_is_refused(model) -> None:
    with pytest.raises(RepositoryToolError, match="this is a diff"):
        write_approved_artifact(
            model, "app/model.js", "export class Model {\n  addTask(task) {\n" + DIFF + "  }\n}\n"
        )


def test_the_same_change_without_markers_is_written(model) -> None:
    replace_approved_lines(
        model, "app/model.js", 3, 4,
        "    this.tasks.push(task);\n    storage.saveTasks(this.tasks);\n    this._emitUpdate();\n",
    )

    assert "storage.saveTasks" in (model / "app" / "model.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("content", [
    # A negation and a sum: no '-' line is a line the file already holds.
    "    const a = -offset;\n    -delta;\n    +count;\n",
    # Only additions: left to the rules for edits that fail to parse.
    "    this.tasks.push(task);\n+    this._emitUpdate();\n",
])
def test_code_that_only_looks_like_one_is_written(model, content: str) -> None:
    replace_approved_lines(model, "app/model.js", 3, 3, content)


def test_a_document_may_hold_both_kinds_of_bullet(tmp_path) -> None:
    write_approved_artifact(tmp_path, "app/NOTES.md", "- keep\n")
    write_approved_artifact(tmp_path, "app/NOTES.md", "- keep\n+ added\n")

    assert (tmp_path / "app" / "NOTES.md").read_text(encoding="utf-8") == "- keep\n+ added\n"
