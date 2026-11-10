"""A capped reply whose text opens a reasoning tag it never closes is answered from that reasoning, not continued.

Measured on one run: a fix stage's reply, its thinking switched off, opened `<think>` in its text, reached the cap and
was continued twice more to 29,570 tokens - more reasoning, and no answer.
"""
from __future__ import annotations

import inspect

from app.models import reply_salvage


def test_an_unclosed_tag_is_reasoning():
    assert reply_salvage.reasoning_left_open("<think>\nThe accessible name is ...") == "The accessible name is ..."
    assert reply_salvage.reasoning_left_open("  <thinking>weighing it") == "weighing it"


def test_a_closed_tag_or_plain_text_is_not():
    assert reply_salvage.reasoning_left_open("<think>done</think>\n{\"fixed\": true}") is None
    assert reply_salvage.reasoning_left_open("The fix changes the handler.") is None
    assert reply_salvage.reasoning_left_open("<|begin_of_thought|>x") is None


def test_salvage_treats_it_as_cut_while_reasoning():
    source = inspect.getsource(reply_salvage.salvaged)
    assert "reasoning_left_open(str(message.content or \"\")) if cut else None" in source
    assert "lost, cut, reasoning = True, False, unclosed" in source


# Measured on one run: a fix stage, its thinking switched off, wrote 45,000 characters of "Wait - ...", "Actually, let me
# re-read ...", "So what can I do?" to the cap, twice, with no call and no answer; each was continued, about 11 minutes.
SPIRAL = (
    "Now I can see the full file. The tests show two failures.\n\n"
    "Wait - `getByRole('listitem').last()` returns the last item.\n\nActually, let me re-read the defect.\n\n"
    "Hmm, the filter reads `tasks` from the closure.\n\nSo what can I do? I can't modify the test.\n\n"
    "But wait, `init()` runs twice.\n\nLet me check the handler again.\n\nOkay so the order is task 1, task 2."
)


def test_prose_that_reasons_is_reasoning_and_an_answer_is_not():
    assert reply_salvage.reasoning_in_prose(SPIRAL) == SPIRAL.strip()
    answer = ("## Changes\n\nThe handler now reads the filter once. Let me note the files: app.js and styles.css.\n\n"
              "The test for the filter passes. Actually the list is drawn once per change.")
    assert reply_salvage.reasoning_in_prose(answer) is None


def test_salvage_reads_capped_prose_without_calls_as_reasoning():
    source = inspect.getsource(reply_salvage.salvaged)
    assert 'unclosed = reasoning_in_prose(str(message.content or ""))' in source
    assert 'if unclosed is None and cut and not getattr(message, "tool_calls", None):' in source
