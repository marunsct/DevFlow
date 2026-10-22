"""Tests for IDE diagnostic warning format (Pillar 7 & Change 3).

The language service note returned on file edits must be explicit and direct,
warning the model of high-confidence errors so they are fixed immediately.
"""

from __future__ import annotations

import re
from app.analysis.language_service import Underlined

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def test_ide_diagnostic_note_is_direct_and_imperative() -> None:
    findings = [
        {"line": 15, "message": "Cannot find name 'missingVar'", "text": "missingVar()"}
    ]
    u = Underlined(here=findings, elsewhere=[])
    note = u.note()
    assert "IDE DIAGNOSTIC WARNING" in note
    assert "Fix these errors now before completing this stage" in note
    assert "missingVar" in note


def test_ide_diagnostic_note_has_no_banned_words() -> None:
    findings = [
        {"line": 15, "message": "Cannot find name 'missingVar'", "text": "missingVar()"}
    ]
    u = Underlined(here=findings, elsewhere=[])
    note = u.note()
    outside = re.sub(r"`[^`]*`", "", note).lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", outside), f"Banned word '{word}' found in IDE note"

