"""Fixers after a fix undone because the product stopped starting are told so, and what it raised.

Measured over 37 stored runs: 128 fixes were reverted as "the product no longer builds or starts after it", 11 runs
with three or more in a row; each next fixer saw only its own criterion and made the same change again.
"""
from __future__ import annotations

import re

from app.agents import start_breaks
from app.agents.shared_facts import the_facts_section


def test_the_streak_is_told_with_the_last_error_and_cleared_by_a_kept_fix(tmp_path):
    assert the_facts_section(tmp_path) == ""
    start_breaks.record(tmp_path, "defect_fix_1_0", "The product did not start ... ValueError: one")
    start_breaks.record(tmp_path, "defect_fix_1_1", "The product did not start ... TypeError: responder must be async")
    text = the_facts_section(tmp_path)
    assert "2 fixes in a row" in text and "defect_fix_1_1" in text
    assert "TypeError: responder must be async" in text
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", text, re.I)
    start_breaks.clear(tmp_path)
    assert the_facts_section(tmp_path) == ""


def test_the_revert_of_a_fix_that_stopped_the_start_records_it():
    import inspect

    from app.graph import engineering

    source = inspect.getsource(engineering.after_a_fix)
    assert "start_breaks.record(root, stage_name" in source and "start_breaks.clear(root)" in source
