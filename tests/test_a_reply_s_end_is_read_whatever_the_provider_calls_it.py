"""Why a reply ended is read whatever the provider calls it (harness review C7).

Measured: all 857 replies recorded with no finish reason came from one provider that reports `stop_reason`
(`end_turn`, `tool_use`, `max_tokens`); a reply cut off by the cap read as unknown, not as `length`.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.observability.transcript import finish_reason_of


def _reply(info=None, metadata=None):
    return SimpleNamespace(generation_info=info or {}), SimpleNamespace(response_metadata=metadata or {})


def test_a_stop_reason_is_read_in_the_openai_words():
    assert finish_reason_of(*_reply(metadata={"stop_reason": "max_tokens"})) == "length"
    assert finish_reason_of(*_reply(metadata={"stop_reason": "tool_use"})) == "tool_calls"
    assert finish_reason_of(*_reply(metadata={"stop_reason": "end_turn"})) == "stop"


def test_a_finish_reason_stands_and_silence_is_none():
    assert finish_reason_of(*_reply(info={"finish_reason": "length"})) == "length"
    assert finish_reason_of(*_reply(metadata={"finish_reason": "stop"})) == "stop"
    assert finish_reason_of(*_reply()) is None
