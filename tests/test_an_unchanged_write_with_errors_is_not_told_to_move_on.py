"""A file sent again unchanged while it still has errors is not told to move on.

Measured live: a fixer wrote a page that imported a module nothing had
written yet, and the write's note said "Fix these errors now". It then sent
the same page again. The reply said "Do not write it again; continue with
your response" beside the same note, and the stage spent its budget between
the two instructions.
"""
from __future__ import annotations

import re

from app.tools import repository
from app.tools.repository import write_approved_artifact

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PAGE = "import { load } from './missing';\nexport const page = load;\n"
FINDING = "IDE DIAGNOSTIC WARNING - line 1: Cannot find module './missing'.\nFix these errors now before completing this stage."


def _with_finding(monkeypatch, note):
    monkeypatch.setattr(repository, "_import_note", lambda root, target, content: note)


def test_the_unchanged_reply_agrees_with_the_errors(tmp_path, monkeypatch):
    _with_finding(monkeypatch, FINDING)
    write_approved_artifact(tmp_path, "p/page.js", PAGE)
    again = write_approved_artifact(tmp_path, "p/page.js", PAGE)

    assert again["status"] == "unchanged"
    assert "continue with your response" not in again["detail"]
    assert "still in it" in again["detail"]
    assert "Fix these errors now" in again["note"]
    assert not BANNED.search(again["detail"])


def test_an_unchanged_file_with_no_errors_is_still_told_to_move_on(tmp_path, monkeypatch):
    _with_finding(monkeypatch, "")
    write_approved_artifact(tmp_path, "p/page.js", PAGE)
    again = write_approved_artifact(tmp_path, "p/page.js", PAGE)

    assert again["status"] == "unchanged"
    assert "Do not write it again" in again["detail"]
