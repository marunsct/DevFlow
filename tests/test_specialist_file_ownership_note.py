"""Tests for explicit work order file ownership instructions to specialists.

Specialists must be explicitly instructed on which files they own to avoid
wasting model calls on rejected edits of files owned by other work orders.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock
from app.agents.specialists import _work_order_file_ownership_note, build_specialist_task_request


def test_work_order_file_ownership_note_lists_files() -> None:
    order = MagicMock()
    order.files = ["src/main.js", "src/view.js"]
    note = _work_order_file_ownership_note(order)
    assert "`src/main.js`" in note
    assert "`src/view.js`" in note
    assert "You may create or edit only these files" in note


def test_work_order_file_ownership_note_empty_when_no_files() -> None:
    order = MagicMock()
    order.files = []
    assert _work_order_file_ownership_note(order) == ""
    assert _work_order_file_ownership_note(None) == ""


def test_ownership_note_contains_no_forbidden_words() -> None:
    order = MagicMock()
    order.files = ["src/app.py"]
    note = _work_order_file_ownership_note(order)
    forbidden = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    words = {w.lower() for w in re.findall(r"\b\w+[\w-]*\b", note)}
    assert not (words & forbidden), f"Found forbidden words: {words & forbidden}"

