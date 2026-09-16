"""A stage that toggles one passage back and forth is told so.

Nothing else here catches it. The repeat guard wants byte-identical
consecutive calls; the no-op refusal wants `replace` to equal what it
replaces. Both see a *successful* edit with new arguments and let it through,
so the file oscillates and the stage spends its budget.

Measured on run 8d28ee3f, `defect_fix_1_0`: 67 tool calls against a 40-call
budget, 23 edits and 16 reads of one file. Its edits to `app.js` ran
`console.log(...)` -> `global.console.log(...)` -> `console.log(...)` ->
`console.log(...)`, each reported "edited".
"""

import pytest

from app.tools.repository import edit_approved_artifact, read_text_file, write_approved_artifact

SOURCE = "export function add(text) {\n  console.log(`Adding: ${text}`);\n  return text;\n}\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app.js").write_text(SOURCE, encoding="utf-8")
    return tmp_path


def _edit(root, find, replace):
    return edit_approved_artifact(root, "app.js", find, replace)


def test_the_measured_oscillation_is_named(project):
    read_text_file(project, "app.js")

    there = _edit(project, "console.log(`Adding", "global.console.log(`Adding")
    assert "back into a state it already had" not in (there.get("note") or "")

    back = _edit(project, "global.console.log(`Adding", "console.log(`Adding")

    note = back.get("note") or ""
    assert "back into a state it already had earlier in this stage" in note
    assert "undoes a change made here" in note


def test_an_edit_that_moves_forward_says_nothing(project):
    read_text_file(project, "app.js")

    _edit(project, "console.log(`Adding", "global.console.log(`Adding")
    onward = _edit(project, "return text;", "return text.trim();")

    assert "back into a state it already had" not in (onward.get("note") or "")


def test_a_return_to_a_state_a_write_created_is_caught(tmp_path):
    """The first state of a file is often a `write_artifact`, not a read.

    Written inside a project directory because a bare root write is refused
    for its own reason - the workspace needs one top-level project folder.
    """
    write_approved_artifact(tmp_path, "todo-app/app.js", SOURCE)

    edit_approved_artifact(
        tmp_path, "todo-app/app.js", "console.log(`Adding", "global.console.log(`Adding"
    )
    back = edit_approved_artifact(
        tmp_path, "todo-app/app.js", "global.console.log(`Adding", "console.log(`Adding"
    )

    assert "back into a state it already had" in (back.get("note") or "")


def test_the_very_first_edit_of_a_stage_is_never_flagged(project):
    read_text_file(project, "app.js")

    first = _edit(project, "return text;", "return text.trim();")

    assert "back into a state it already had" not in (first.get("note") or "")


def test_a_three_way_cycle_is_caught_on_the_return(project):
    """A -> B -> C -> A is the same mistake with one more step."""
    read_text_file(project, "app.js")

    _edit(project, "return text;", "return text.trim();")
    _edit(project, "return text.trim();", "return String(text);")
    back = _edit(project, "return String(text);", "return text;")

    assert "back into a state it already had" in (back.get("note") or "")


def test_the_note_does_not_replace_the_result(project):
    """It is a note on a successful edit, not a refusal."""
    read_text_file(project, "app.js")
    _edit(project, "console.log(`Adding", "global.console.log(`Adding")
    back = _edit(project, "global.console.log(`Adding", "console.log(`Adding")

    assert back["status"] == "edited"
    assert "console.log(`Adding" in (project / "app.js").read_text(encoding="utf-8")


def test_another_stage_does_not_inherit_this_ones_history(project, monkeypatch):
    """The history is per stage, like every other counter here."""
    from app.tools import seen_content

    read_text_file(project, "app.js")
    _edit(project, "console.log(`Adding", "global.console.log(`Adding")

    seen_content.forget_everything()

    back = _edit(project, "global.console.log(`Adding", "console.log(`Adding")
    assert "back into a state it already had" not in (back.get("note") or "")
