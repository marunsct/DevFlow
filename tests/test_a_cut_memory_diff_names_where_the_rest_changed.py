"""A project-memory note that cuts a file's diff names where the rest of the changes are.

Measured on one run: a repair made three edits and the note showed only the first two before "... 33 more changed
lines". The model read that as all it had done, disbelieved the edit tool's "already applied" and sent the third edit
five times more.
"""
from __future__ import annotations

import re

from app.agents import project_memory

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

BEFORE = "\n".join(f"line {n}" for n in range(1, 301))


def _after():
    rows = BEFORE.splitlines()
    for at in (10, 40):
        rows[at:at] = [f"added near {at} part {k}" for k in range(12)]
    rows.insert(200, "test('[AC-6] survives a restart', async () => {")
    return "\n".join(rows)


def test_the_hidden_hunks_are_named_with_their_lines(monkeypatch):
    monkeypatch.setattr(project_memory, "_the_read_tool_is_withheld", lambda: True)
    note = project_memory.changes_since({"a/spec.js": BEFORE}, {"a/spec.js": _after()})
    tail = note.splitlines()[-1]
    assert "more changed lines, not shown, at" in tail
    assert "[AC-6] survives a restart" in tail
    assert "Those changes are in the file too" in tail
    assert not BANNED.search(tail)


def test_a_short_diff_is_not_cut(monkeypatch):
    monkeypatch.setattr(project_memory, "_the_read_tool_is_withheld", lambda: True)
    note = project_memory.changes_since({"a/spec.js": BEFORE}, {"a/spec.js": BEFORE.replace("line 5\n", "line five\n")})
    assert "not shown" not in note and "line five" in note
