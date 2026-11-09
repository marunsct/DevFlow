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
