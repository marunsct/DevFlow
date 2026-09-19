"""A whole file escaped twice over was fatal; the same fault in an edit was not.

Measured live on run-eb48de7a at 03:37, two minutes into the run.
`test_round_0` sent

    write_artifact(relative_path="todo-app/package.json",
                   content='{\\n  "name": "todo-app", ... }')

where every newline is the two characters backslash-n. `json.loads` stops at
column 2, the write is refused - correctly, since a broken `package.json`
breaks every module in its directory - and the model sent the identical bytes
three times before the repeat guard answered it. The stage made no progress.

The repairs for exactly this fault have existed since run-95ca3f72 and
run-0b55ad49, and were reachable only from `edit_artifact`'s `find`.
`write_artifact` had none. Twelve of thirteen again, with the thirteenth being
the path that carries whole files.

The rule is the one the edit repairs already use, and it is what keeps this
safe: repair only when the content is structurally invalid as sent AND
structurally valid after. Content that legitimately holds a literal
backslash-n already parses, so it is never touched.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.tools.repository import (
    RepositoryToolError,
    _content_a_model_escaped_twice,
    write_approved_artifact,
)


@pytest.fixture()
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "app").mkdir()
    (tmp_path / ".project-directory").write_text("app", encoding="utf-8")
    return tmp_path


def test_the_exact_run_eb48de7a_content_is_written(workspace):
    sent = (
        '{\\n  "name": "todo-app",\\n  "version": "1.0.0",\\n  "type": "module",'
        '\\n  "scripts": {\\n    "test": "node --test"\\n  }\\n}'
    )

    result = write_approved_artifact(workspace, "app/package.json", sent)

    assert result["status"] == "written"
    on_disk = (workspace / "app" / "package.json").read_text(encoding="utf-8")
    assert json.loads(on_disk)["scripts"]["test"] == "node --test"


def test_the_model_is_told_what_was_repaired(workspace):
    """A silent repair teaches nothing and the next file is escaped the same way."""
    result = write_approved_artifact(
        workspace, "app/package.json", '{\\n  "name": "a"\\n}'
    )

    note = result.get("note") or ""
    assert "escaped twice over" in note
    assert "`find`" not in note, "that is the edit tool's argument, not this one's"


def test_content_that_legitimately_holds_a_backslash_n_is_untouched(workspace):
    """Valid content is never repaired, because it never fails the check."""
    valid = json.dumps({"pattern": "a\\nb"})
    assert _content_a_model_escaped_twice("app/x.json", valid) is None

    write_approved_artifact(workspace, "app/x.json", valid)
    assert json.loads((workspace / "app" / "x.json").read_text(encoding="utf-8")) == {
        "pattern": "a\\nb"
    }


def test_a_file_with_no_structural_check_is_never_repaired(workspace):
    """Prose may contain anything; there is no grammar to say it is broken."""
    assert _content_a_model_escaped_twice("app/notes.txt", "one\\ntwo") is None


def test_content_broken_for_a_real_reason_is_still_refused(workspace):
    """A repair that does not fix the problem is discarded, not written."""
    with pytest.raises(RepositoryToolError):
        write_approved_artifact(workspace, "app/package.json", '{"name": "a",,,}')


@pytest.mark.parametrize(
    "name,sent,check",
    [
        ("app/package.json", '{\\n  "a": 1\\n}', lambda s: json.loads(s)["a"] == 1),
        ("app/m.py", "def f():\\n    return 1", lambda s: "\n" in s and "\\n" not in s),
    ],
)
def test_the_repair_is_not_json_specific(workspace, name, sent, check):
    """Python is parsed with `ast`, JSON with `json.loads`; both are real grammars."""
    write_approved_artifact(workspace, name, sent)
    assert check((workspace / name).read_text(encoding="utf-8"))


def test_the_repair_and_the_edit_path_share_one_definition():
    """The bug was two paths and one implementation, so the fix must not fork it."""
    import inspect

    from app.tools import repository

    source = inspect.getsource(repository._content_a_model_escaped_twice)
    assert "_transcription_repairs" in source, (
        "the write path must reuse the edit path's repairs, not copy them"
    )
