"""A stage reasoned until its reply was truncated, and the harness guessed.

One run failed after 3 hours 23 minutes at `defect_fix_2_4`. Fourteen
model responses across that run came back with `finish_reason: length`, no
text and no tool call - nine of them in that one stage. Settings were
`model_max_output_tokens = 20000` with `thinking_effort = high`, and the
defect-fix stages are where reasoning runs longest, so those nine calls
produced literally nothing.

What the operator was told:

    Agent 'defect_fix_2_4' finished without returning its structured response.
    It produced no final message at all. This was tried 3 times, each on a
    fresh conversation.
    Common causes, in the order worth checking:
    - The model answered in prose rather than calling the response schema...
    - The reply was cut off by MODEL_MAX_OUTPUT_TOKENS. Raise it if the last
      message ends mid-sentence.
    ...

Four guesses, the right one second, and the test it offers - does the last
message end mid-sentence - cannot be applied, because there was no last
message. Meanwhile `finish_reason: length` sat on that very message saying
which guess was correct.

The message now reads the flag. It also says plainly that a fresh
conversation cannot help, because the ceiling is per reply rather than per
conversation - which is what the harness did next, three times, for over an
hour.
"""

from __future__ import annotations

import pytest

from app.graph.workflow import (
    _it_spent_its_whole_output_budget,
    _missing_structured_response,
    _the_reply_was_cut_off_before_it_began,
)


class _Message:
    """An AI message as a provider hands it back."""

    type = "ai"

    def __init__(self, content: str = "", finish: str = "stop", where: str = "response_metadata"):
        self.content = content
        setattr(self, where, {"finish_reason": finish})


def test_a_truncated_reply_is_recognised():
    assert _the_reply_was_cut_off_before_it_began(_Message(finish="length"))


def test_it_is_read_from_either_place_a_provider_puts_it():
    """Some providers use `additional_kwargs` rather than `response_metadata`."""
    assert _the_reply_was_cut_off_before_it_began(
        _Message(finish="length", where="additional_kwargs")
    )


@pytest.mark.parametrize("finish", ["stop", "tool_calls", "content_filter", ""])
def test_any_other_ending_is_not_this(finish: str):
    assert not _the_reply_was_cut_off_before_it_began(_Message("some text", finish))


def test_a_message_with_no_metadata_at_all_is_not_this():
    class Bare:
        type = "ai"
        content = ""

    assert not _the_reply_was_cut_off_before_it_began(Bare())


def test_the_failure_names_the_cause_rather_than_four_guesses():
    result = {"messages": [_Message(finish="length")]}

    message = _missing_structured_response("defect_fix_2_4", result, attempts=3)

    assert "spent its entire output budget" in message
    assert "finish_reason: length" in message
    assert "Common causes" not in message, "it is not a guess any more"


def test_it_says_a_restart_cannot_help():
    """The harness spent three attempts and over an hour learning this."""
    message = _it_spent_its_whole_output_budget("defect_fix_2_4", 3)

    assert "FRESH CONVERSATION CANNOT FIX THIS" in message
    assert "per reply, not" in message
    assert "attempt 3 at the stage" in message


def test_it_names_every_setting_that_would_change_the_outcome():
    message = _it_spent_its_whole_output_budget("a_stage", 1)

    assert "MODEL_MAX_OUTPUT_TOKENS" in message
    assert "thinking_effort" in message


def test_it_quotes_the_configured_budget_when_there_is_one(monkeypatch):
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "20000")

    assert "20000 output tokens" in _it_spent_its_whole_output_budget("a_stage", 1)


def test_it_stays_readable_when_the_budget_is_unset(monkeypatch):
    monkeypatch.delenv("MODEL_MAX_OUTPUT_TOKENS", raising=False)

    message = _it_spent_its_whole_output_budget("a_stage", 1)

    assert "its configured output limit" in message
    assert "None" not in message


def test_the_prose_diagnosis_still_works():
    """The other branch, unchanged: a model that wrote its answer out."""
    result = {"messages": [_Message("Here is my structured response: ...", "stop")]}

    message = _missing_structured_response("a_stage", result)

    assert "wrote the answer as prose" in message
    assert "output budget" not in message


def test_an_empty_stop_is_still_the_generic_message():
    """No content and a clean stop is a different fault with different fixes."""
    result = {"messages": [_Message("", "stop")]}

    message = _missing_structured_response("a_stage", result)

    assert "no final message at all" in message
    assert "Common causes" in message
