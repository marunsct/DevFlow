"""A reply that spent its whole output budget reasoning gets one forced answer.

Measured on one run: 7 of 543 responses came back with
`finish_reason: length`, no text and no tool call, each having burned the full
30,000-token output budget on reasoning nobody ever saw. The run died when
`test_round_2` ended that way.

It is not an input problem. Those seven replies had inputs of 34k-66k tokens,
while the largest input of the whole run - 77k - answered in 361 tokens. So
trimming context does not address it, and a larger output budget only makes the
same spiral more expensive.

What it is, is a reply with no room left to land in. The next call therefore gets
the tools withheld and is asked for the answer, which is the remedy this module
already applies at the end of the call budget, for the same reason. One spiral
costs one call instead of the stage.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.settled_answer import (
    _REASONED_PAST_THE_BUDGET_NOTICE,
    _the_last_reply_was_all_reasoning,
)


class _Ai:
    type = "ai"

    def __init__(
        self,
        *,
        finish: str = "stop",
        content: str = "",
        tool_calls: tuple[Any, ...] = (),
        where: str = "response_metadata",
    ) -> None:
        setattr(self, where, {"finish_reason": finish})
        self.content = content
        self.tool_calls = list(tool_calls)


class _Tool:
    type = "tool"

    def __init__(self, content: str = "ok") -> None:
        self.content = content
        self.tool_call_id = "c0"


class TestRecognisingTheSpiral:
    def test_the_measured_reply_is_recognised(self) -> None:
        assert _the_last_reply_was_all_reasoning([_Ai(finish="length")]) is True

    def test_it_reads_the_flag_from_additional_kwargs_too(self) -> None:
        reply = _Ai(finish="length", where="additional_kwargs")

        assert _the_last_reply_was_all_reasoning([reply]) is True

    def test_only_the_most_recent_reply_counts(self) -> None:
        """A spiral three calls ago was already answered for; this is about now."""
        messages = [_Ai(finish="length"), _Tool(), _Ai(finish="stop", content="fine")]

        assert _the_last_reply_was_all_reasoning(messages) is False

    def test_a_truncated_reply_that_wrote_something_is_not_a_spiral(self) -> None:
        """It landed near the budget; the next call may fit inside it."""
        reply = _Ai(finish="length", content="Here is the analysis so far")

        assert _the_last_reply_was_all_reasoning([reply]) is False

    def test_a_truncated_reply_that_called_a_tool_is_not_a_spiral(self) -> None:
        reply = _Ai(finish="length", tool_calls=({"name": "read_file", "id": "c1"},))

        assert _the_last_reply_was_all_reasoning([reply]) is False

    @pytest.mark.parametrize("finish", ("stop", "tool_calls", "", "content_filter"))
    def test_an_untruncated_reply_is_never_a_spiral(self, finish: str) -> None:
        assert _the_last_reply_was_all_reasoning([_Ai(finish=finish)]) is False

    def test_a_conversation_with_no_reply_yet_is_not_a_spiral(self) -> None:
        assert _the_last_reply_was_all_reasoning([_Tool()]) is False
        assert _the_last_reply_was_all_reasoning([]) is False

    def test_whitespace_is_not_content(self) -> None:
        assert _the_last_reply_was_all_reasoning([_Ai(finish="length", content=" \n ")]) is True


class TestWhatTheStageIsTold:
    def test_the_notice_says_why_reasoning_again_will_not_help(self) -> None:
        assert "per reply" in _REASONED_PAST_THE_BUDGET_NOTICE

    def test_the_notice_asks_for_an_answer_and_offers_blockers(self) -> None:
        assert "structured response" in _REASONED_PAST_THE_BUDGET_NOTICE
        assert "blockers" in _REASONED_PAST_THE_BUDGET_NOTICE

    def test_it_is_not_the_call_budget_notice(self) -> None:
        """A stage in a spiral may have plenty of calls left, so telling it that
        it is at the end of its budget would be false."""
        from app.agents.settled_answer import TOOLS_WITHHELD_NOTICE

        assert _REASONED_PAST_THE_BUDGET_NOTICE != TOOLS_WITHHELD_NOTICE
        assert "model-call budget" not in _REASONED_PAST_THE_BUDGET_NOTICE


def test_the_spiral_withholds_tools_where_thinking_cannot_be_switched_off(monkeypatch) -> None:
    """The next call after a reply spent wholly on reasoning is offered no tools, only its answer."""
    from types import SimpleNamespace

    from pydantic import BaseModel

    from app.agents.settled_answer import build_settled_answer_middleware

    monkeypatch.setenv("STABLE_TOOLS", "off")  # the bound tool list is what this reads

    class _Answer(BaseModel):
        ok: bool = True

    class _Request:
        def __init__(self, messages, tools):
            self.messages, self.tools, self.model, self.model_settings = messages, tools, None, {}

        def override(self, **changes):
            return _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))

    sent: list = []
    messages = [SimpleNamespace(type="human", content="Plan the milestone."), _Ai(finish="length")]
    middleware = build_settled_answer_middleware(_Answer, "technical_lead", step_limit=60)

    middleware.wrap_model_call(_Request(messages, [SimpleNamespace(name="ls"), SimpleNamespace(name="read_file")]),
                               sent.append)

    assert sent[0].tools == []
