"""A criterion defect whose test received a 5xx while the server logged nothing tells the fixer the handler hides the cause.

Measured on one run: POST answered 500, the product's error handler returned JSON without logging, and ten fix stages
changed headers and middleware around a cause none could see, each ending "its own tests still fail".
"""
from __future__ import annotations

import inspect
import re

from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FIVE_HUNDRED = "expect(received).toBe(expected)\n\n    Expected: 201\n    Received: 500\n"


def test_a_5xx_with_an_empty_server_log_adds_the_note():
    note = acceptance_nodes.the_server_hid_the_cause([FIVE_HUNDRED], "")
    assert "logged nothing" in note and "standard error" in note
    assert not BANNED.search(note)


def test_a_logged_5xx_or_a_non_5xx_failure_adds_nothing():
    assert acceptance_nodes.the_server_hid_the_cause([FIVE_HUNDRED], "TypeError: x is undefined\n  at notes.ts:12") == ""
    assert acceptance_nodes.the_server_hid_the_cause(["Expected: 201\n    Received: 400\n"], "") == ""


def test_the_criterion_defect_carries_it():
    source = inspect.getsource(acceptance_nodes.failing_due_defects)
    assert 'the_server_hid_the_cause([t.get("message") or "" for t in failed], logged)' in source
