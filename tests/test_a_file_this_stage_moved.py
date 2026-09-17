"""A read or an edit at a path the stage renamed itself.

Run d6297b2f's `specialist_backend_0` moved `test/loadTasks.test.mjs` to
`test/loadTasks.test.js`, then spent a `read_file` and an `edit_artifact` on
the old name. Each was answered only "not found". That stage ran 47 model
calls; the next longest in the run ran 10.

The basename lookup that usually rescues a wrong path cannot help here: a
rename that changes the extension changes the basename too. The stage does
know the new name - it chose it - so the answer is a memo, not a search.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    move_approved_artifact,
    write_approved_artifact,
)
from app.tools.seen_content import record_move, where_this_stage_moved_it


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "todo").mkdir()
    write_approved_artifact(
        tmp_path, "todo/loadTasks.test.mjs", "import assert from 'node:assert';\n"
    )
    return tmp_path


def test_a_move_is_remembered(project: Path):
    move_approved_artifact(project, "todo/loadTasks.test.mjs", "todo/loadTasks.test.js")

    assert where_this_stage_moved_it("todo/loadTasks.test.mjs") == "todo/loadTasks.test.js"


def test_editing_the_old_name_says_where_it_went(project: Path):
    move_approved_artifact(project, "todo/loadTasks.test.mjs", "todo/loadTasks.test.js")

    with pytest.raises(RepositoryToolError) as raised:
        edit_approved_artifact(
            project, "todo/loadTasks.test.mjs", find="assert", replace="ok"
        )

    message = str(raised.value)
    assert "moved it to 'todo/loadTasks.test.js'" in message
    assert "Edit that instead" in message


def test_the_refusal_says_not_to_recreate_the_file(project: Path):
    """Writing the old path back would leave two copies of the same module."""
    move_approved_artifact(project, "todo/loadTasks.test.mjs", "todo/loadTasks.test.js")

    with pytest.raises(RepositoryToolError) as raised:
        edit_approved_artifact(project, "todo/loadTasks.test.mjs", find="a", replace="b")

    assert "two copies" in str(raised.value)


def test_a_file_that_was_never_moved_gets_the_ordinary_message(project: Path):
    with pytest.raises(RepositoryToolError) as raised:
        edit_approved_artifact(project, "todo/never-existed.js", find="a", replace="b")

    message = str(raised.value)
    assert "does not exist yet" in message
    assert "moved" not in message


def test_a_file_moved_twice_reports_where_it_is_now():
    record_move("a.mjs", "b.mjs")
    record_move("b.mjs", "c.js")

    assert where_this_stage_moved_it("a.mjs") == "c.js"
    assert where_this_stage_moved_it("b.mjs") == "c.js"


def test_the_read_hint_names_the_new_path():
    from app.agents.workspace_backend import _Suggesting

    record_move("todo/loadTasks.test.mjs", "todo/loadTasks.test.js")
    hint = _Suggesting._where_this_stage_moved_it(
        _Suggesting(), "/todo/loadTasks.test.mjs"
    )

    assert "todo/loadTasks.test.js" in hint
    assert "you renamed it" in hint


def test_the_read_hint_is_empty_for_a_file_nothing_moved():
    from app.agents.workspace_backend import _Suggesting

    assert _Suggesting._where_this_stage_moved_it(_Suggesting(), "/todo/other.js") == ""


def test_moving_a_file_this_stage_already_moved_says_so(project: Path):
    """A stage renaming a set of files loses track of which it has done.

    Run d6297b2f's `test_round_0` renamed test files one at a time and spent
    two `move_artifact` calls on sources it had already moved, each answered
    only "does not exist. Run `ls`" - a call to learn something it did itself.
    """
    move_approved_artifact(project, "todo/loadTasks.test.mjs", "todo/loadTasks.test.js")

    with pytest.raises(RepositoryToolError) as raised:
        move_approved_artifact(project, "todo/loadTasks.test.mjs", "todo/loadTasks.test.js")

    assert "already moved it" in str(raised.value)
    assert "nothing to do" in str(raised.value)


def test_moving_it_somewhere_else_names_where_it_went(project: Path):
    move_approved_artifact(project, "todo/loadTasks.test.mjs", "todo/loadTasks.test.js")

    with pytest.raises(RepositoryToolError) as raised:
        move_approved_artifact(project, "todo/loadTasks.test.mjs", "todo/other.test.js")

    assert "moved it to 'todo/loadTasks.test.js'" in str(raised.value)


def test_a_source_that_never_existed_still_says_to_look(project: Path):
    with pytest.raises(RepositoryToolError) as raised:
        move_approved_artifact(project, "todo/never.test.js", "todo/other.test.js")

    assert "Run `ls`" in str(raised.value)


def test_deleting_a_file_this_stage_already_deleted_says_so(project: Path):
    """A stage clearing up its own debugging scripts loses track of which went.

    Measured on run 551640d3: twelve failed deletes across two stages, ten of
    them on a path that same stage had deleted successfully a moment earlier.
    "Run `ls` to see what is actually there" sends it to look for an answer it
    already has.
    """
    from app.tools.repository import delete_approved_artifact

    write_approved_artifact(project, "todo/tmp_debug.mjs", "console.log('x');\n")
    assert delete_approved_artifact(project, "todo/tmp_debug.mjs")["status"] == "deleted"

    with pytest.raises(RepositoryToolError) as raised:
        delete_approved_artifact(project, "todo/tmp_debug.mjs")

    assert "this stage already deleted it" in str(raised.value)
    assert "nothing more is needed" in str(raised.value)


def test_a_file_that_never_existed_still_says_to_look(project: Path):
    from app.tools.repository import delete_approved_artifact

    with pytest.raises(RepositoryToolError) as raised:
        delete_approved_artifact(project, "todo/never_existed.mjs")

    assert "Run `ls`" in str(raised.value)
    assert "already deleted" not in str(raised.value)


def test_the_deletion_memo_is_kept_per_file(project: Path):
    from app.tools.repository import delete_approved_artifact

    write_approved_artifact(project, "todo/one.mjs", "x\n")
    write_approved_artifact(project, "todo/two.mjs", "x\n")
    delete_approved_artifact(project, "todo/one.mjs")

    assert delete_approved_artifact(project, "todo/two.mjs")["status"] == "deleted"
