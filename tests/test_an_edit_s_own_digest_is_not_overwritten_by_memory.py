"""The project memory does not overwrite what the stage's own edit recorded (plan item AM).

The memory middleware hands a stage the files it holds on every model call and
recorded their visit-start text as "seen" each time. After the stage's own
edit recorded the new text, the next call put the old text back, so a later
edit was judged against text the stage had since changed and the failure was
blamed on "a command you ran". The first sighting now stands; and a note about
files changed since the memory was taken shows what changed when the stage's
read tool has been taken away, instead of asking for a read it cannot make.
"""
from __future__ import annotations

import re

from app.agents import project_memory, settled_answer
from app.tools import seen_content

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_first_sighting_stands_and_an_edit_still_overwrites():
    seen_content.remember_if_unseen("app/a.js", "one\n")
    seen_content.remember_if_unseen("app/a.js", "visit start\n")
    assert seen_content.changed_since_seen("app/a.js", "one\n") is False

    seen_content.remember("app/a.js", "two\n")  # the stage's own edit
    seen_content.remember_if_unseen("app/a.js", "one\n")  # the next call's memory

    assert seen_content.changed_since_seen("app/a.js", "two\n") is False
    assert seen_content.changed_since_seen("app/a.js", "one\n") is True


def test_the_memory_uses_the_first_writer_wins_call():
    import inspect

    source = inspect.getsource(project_memory.build_project_memory_middleware)
    assert "remember_if_unseen(held_path, held_content)" in source
    assert "remember(held_path, held_content)" not in source.replace("remember_if_unseen(held_path, held_content)", "")


def test_a_withheld_read_tool_is_shown_what_changed_not_told_to_read(monkeypatch):
    before = {"app/a.js": "const a = 1;\nconst b = 2;\nexport { a, b };\n"}
    after = {"app/a.js": "const a = 1;\nconst b = 3;\nexport { a, b };\n"}
    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: True)

    note = project_memory.changes_since(before, after)

    assert "-const b = 2;" in note and "+const b = 3;" in note
    assert "read for the current text" not in note
    assert not BANNED.search(note)


def test_a_stage_that_can_read_is_still_told_to_read(monkeypatch):
    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: False)

    note = project_memory.changes_since({"app/a.js": "x\n"}, {"app/a.js": "y\n"})

    assert "read for the current text" in note and "app/a.js (1 lines now)" in note


def test_a_long_change_is_cut_and_says_how_to_find_the_rest(monkeypatch):
    monkeypatch.setattr(settled_answer, "the_read_tool_is_withheld", lambda: True)
    before = {"app/a.js": "".join(f"line {n}\n" for n in range(200))}
    after = {"app/a.js": "".join(f"changed {n}\n" for n in range(200))}

    note = project_memory.changes_since(before, after)

    assert "more changed lines" in note and "grep" in note
    assert len(note.splitlines()) < project_memory.MOST_DIFF_LINES_PER_FILE + 10
