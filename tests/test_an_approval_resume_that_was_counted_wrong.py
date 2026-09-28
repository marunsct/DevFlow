"""A miscounted resume must not end a run that has done all its work.

`decisions_for` counts the actions the paused checkpoint records;
`HumanInTheLoopMiddleware` counts the tool calls still hanging when the resume
arrives. One run ended because those two disagreed inside a parallel worker:

    ValueError: Number of human decisions (2) does not match number of hanging
    tool calls (1).
    During task with name 'HumanInTheLoopMiddleware.after_model'
    During task with name 'specialist_worker'

It is rare and it is not new - one run ended the same way on 2026-09-11,
before any of this session's changes - and why the counts differ is not
established. So this recovers rather than claiming a cure: answer the number the
middleware says it is holding. The alternative is losing every stage that came
before over bookkeeping, and one run had four sprints of work behind it.

Only for `approve` and `reject`. They carry no per-action payload and mean the
same thing however many calls they answer. An `edit` names one specific
replacement, and `decisions_for` records what happened the last time somebody
replicated one to clear this crash: the wrong content is written to every other
call. That one re-raises.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.approval import _the_count_it_wanted, resume_with_decision

#: The message LangGraph actually produced, not a paraphrase.
REAL = (
    "Number of human decisions (2) does not match number of hanging tool calls (1)."
)


class TestReadingTheCountItWants:
    def test_the_real_message_is_understood(self) -> None:
        assert _the_count_it_wanted(ValueError(REAL), 2) == 1

    def test_a_message_about_some_other_offer_is_ignored(self) -> None:
        """If the numbers do not describe the call just made, this is not ours."""
        assert _the_count_it_wanted(ValueError(REAL), 3) is None

    @pytest.mark.parametrize(
        "message",
        (
            "Number of human decisions (2) does not match number of hanging tool calls (2).",
            "Number of human decisions (2) does not match number of hanging tool calls (0).",
            "something else entirely",
            "",
        ),
    )
    def test_nothing_actionable_returns_none(self, message: str) -> None:
        assert _the_count_it_wanted(ValueError(message), 2) is None


class _Agent:
    """An agent that refuses the first resume the way LangGraph does."""

    def __init__(self, *, actions: int, hanging: int) -> None:
        self._actions = actions
        self._hanging = hanging
        self.attempts: list[int] = []

    def get_state(self, _config: dict) -> Any:
        class Interrupt:
            value = {"action_requests": [{} for _ in range(self._actions)]}

        class Snapshot:
            interrupts = (Interrupt(),)

        return Snapshot()

    def invoke(self, command: Any, config: dict) -> dict:  # noqa: ARG002
        sent = len(command.resume["decisions"])
        self.attempts.append(sent)
        if sent != self._hanging:
            raise ValueError(
                f"Number of human decisions ({sent}) does not match number of "
                f"hanging tool calls ({self._hanging})."
            )
        return {"ok": sent}


class TestTheResumeRecovers:
    def test_an_approve_is_retried_with_the_count_it_wants(self) -> None:
        agent = _Agent(actions=2, hanging=1)

        result = resume_with_decision(agent, "t:specialist_backend_0:ab", {"type": "approve"})

        assert result == {"ok": 1}
        assert agent.attempts == [2, 1], "first the counted number, then the real one"

    def test_a_reject_is_retried_too(self) -> None:
        agent = _Agent(actions=3, hanging=1)

        assert resume_with_decision(agent, "t:x:1", {"type": "reject"}) == {"ok": 1}

    def test_an_edit_is_never_replicated(self) -> None:
        """The failure mode `decisions_for` documents: six wrong writes."""
        agent = _Agent(actions=1, hanging=2)

        with pytest.raises(ValueError, match="hanging tool calls"):
            resume_with_decision(agent, "t:x:1", {"type": "edit", "args": {"a": 1}})

        assert agent.attempts == [1], "no retry was attempted"

    def test_a_resume_that_was_counted_right_is_one_call(self) -> None:
        """The ordinary path must not gain a retry."""
        agent = _Agent(actions=2, hanging=2)

        assert resume_with_decision(agent, "t:x:1", {"type": "approve"}) == {"ok": 2}
        assert agent.attempts == [2]

    def test_an_unrelated_value_error_still_raises(self) -> None:
        class Broken(_Agent):
            def invoke(self, command: Any, config: dict) -> dict:  # noqa: ARG002
                self.attempts.append(len(command.resume["decisions"]))
                raise ValueError("the checkpointer is unreachable")

        agent = Broken(actions=1, hanging=1)

        with pytest.raises(ValueError, match="checkpointer"):
            resume_with_decision(agent, "t:x:1", {"type": "approve"})

    def test_the_retry_is_not_retried(self) -> None:
        """One recovery, not a loop: a second refusal propagates.

        This agent moves the goalposts - it asks for a different count each time -
        so the retry is refused as well and must be allowed to fail.
        """

        class NeverSatisfied(_Agent):
            def invoke(self, command: Any, config: dict) -> dict:  # noqa: ARG002
                sent = len(command.resume["decisions"])
                self.attempts.append(sent)
                raise ValueError(
                    f"Number of human decisions ({sent}) does not match number "
                    f"of hanging tool calls ({sent + 1})."
                )

        agent = NeverSatisfied(actions=2, hanging=99)

        with pytest.raises(ValueError, match="hanging tool calls"):
            resume_with_decision(agent, "t:x:1", {"type": "approve"})

        assert agent.attempts == [2, 3], "one retry, then the failure stands"
