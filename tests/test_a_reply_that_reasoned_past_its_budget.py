"""A restart the harness says cannot work must not be attempted.

`_it_spent_its_whole_output_budget` tells the operator, in capitals, that a
fresh conversation cannot fix a reply truncated at the output ceiling: the
ceiling is per reply, so a restart reasons from the beginning and reaches it
again. Its own docstring then records what happened next on run-fbe23618 -
"That is what the harness did next, three times, for over an hour."

The message was fixed there and the futile restart was left in, so
run-be25a68e reproduced it: `test_round_2`, after four sprints of work and 747
tool calls, was restarted three times on fresh conversations and hit the same
ceiling each time. The run failed with an accurate diagnosis an hour after it
could have been given.

The remedy is a setting - a larger `model_max_output_tokens`, or a lower
`thinking_effort` - and no number of attempts substitutes for one. Failing
straight away says the same thing sooner and leaves the artifacts on disk
either way.

A truncation that happened *after* the model wrote something is a different
case, and is still retried: that reply landed close to the budget, and a second
pass may well fit inside it.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.graph.workflow import (
    _nothing_but_reasoning,
    _the_reply_was_cut_off_before_it_began,
)


class _Reply:
    type = "ai"

    def __init__(
        self,
        *,
        finish: str = "stop",
        content: str = "",
        tool_calls: tuple[Any, ...] = (),
    ) -> None:
        self.response_metadata = {"finish_reason": finish}
        self.content = content
        self.tool_calls = list(tool_calls)


class TestNothingButReasoning:
    def test_the_run_be25a68e_reply_is_recognised(self) -> None:
        """Truncated, no text, no tool call: a restart cannot help."""
        assert _nothing_but_reasoning(_Reply(finish="length")) is True

    def test_a_truncated_reply_that_wrote_something_is_not_this_case(self) -> None:
        """It reached the ceiling at the end, not before starting."""
        cut_off = _Reply(finish="length", content="Here is the analysis so far...")

        assert _the_reply_was_cut_off_before_it_began(cut_off) is True
        assert _nothing_but_reasoning(cut_off) is False

    def test_a_truncated_reply_that_called_a_tool_is_not_this_case(self) -> None:
        acted = _Reply(finish="length", tool_calls=({"name": "read_file", "id": "c1"},))

        assert _nothing_but_reasoning(acted) is False

    @pytest.mark.parametrize("finish", ("stop", "tool_calls", "", "content_filter"))
    def test_a_reply_that_was_not_truncated_is_never_this_case(self, finish: str) -> None:
        assert _nothing_but_reasoning(_Reply(finish=finish)) is False

    def test_a_missing_message_is_not_this_case(self) -> None:
        """A stage with no AI message at all failed some other way."""
        assert _nothing_but_reasoning(None) is False

    def test_whitespace_is_not_content(self) -> None:
        assert _nothing_but_reasoning(_Reply(finish="length", content="   \n ")) is True

    def test_the_flag_is_read_from_additional_kwargs_too(self) -> None:
        """Providers put it in either place; the looser check reads both."""

        class Elsewhere:
            type = "ai"
            content = ""
            tool_calls: list = []
            additional_kwargs = {"finish_reason": "length"}

        assert _nothing_but_reasoning(Elsewhere()) is True


def test_the_restart_is_skipped_for_this_one_failure() -> None:
    """The change itself: this failure reaches the raise without restarting.

    Asserted against the source because the surrounding node needs a whole graph
    run to reach, and what matters is that the restart is conditional on exactly
    this check rather than unconditional as it was.
    """
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow._run_gated_agent)
    guarded = source.split("if structured_response is None:")[-1].split(
        "raise ValueError", 1
    )[0]

    assert "_nothing_but_reasoning(" in guarded
    assert "_restart_on_a_fresh_conversation" in guarded
    restart = guarded.find("_restart_on_a_fresh_conversation")
    decision = guarded.find("if out_of_room")

    assert decision != -1 and decision < restart, (
        "the restart must be conditional on the reply having produced nothing, "
        "not attempted and then explained"
    )


def test_the_message_still_names_the_settings_that_fix_it() -> None:
    """Failing sooner is only an improvement if the remedy is still stated."""
    from app.graph.workflow import _it_spent_its_whole_output_budget

    message = _it_spent_its_whole_output_budget("test_round_2", 1)

    assert "MODEL_MAX_OUTPUT_TOKENS" in message
    assert "thinking_effort" in message
    assert "FRESH CONVERSATION CANNOT FIX THIS" in message


def test_the_attempt_count_reads_as_one_when_nothing_was_retried() -> None:
    """Three attempts were reported because three were made. One now."""
    from app.graph.workflow import _it_spent_its_whole_output_budget

    assert "retried" not in _it_spent_its_whole_output_budget("test_round_2", 1)
    assert "retried 3 times" in _it_spent_its_whole_output_budget("test_round_2", 3)
