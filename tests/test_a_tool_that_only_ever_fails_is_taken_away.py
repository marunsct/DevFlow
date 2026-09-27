"""Telling a stage it is repeating a dead call is not enough on its own.

The repeat note already says "It will fail this way again. Change the arguments,
create what is missing, or carry on without it." Measured across two runs, a
stage read that and carried straight on:

    run-83bd156a  specialist_backend_0  15 identical `edit_artifact` calls, each
                  refused because the file would not parse afterwards
    run-1bdbc08a  specialist_backend_3   7 identical `replace_lines` calls, the
                  same refusal every time

The first was the largest single class of failed call in its run, and neither was
visible until the audit tool was fixed: its failure regex was anchored, so the
bracketed repeat note pushed the error off the start of the string and the
counting stopped exactly when the repeating began. run-83bd156a's true total was
29 failed calls against the 15 first reported.

Reads already escalate from a note to withholding the tool after
`READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL`. A mutation that cannot succeed had
no such step, so the only thing bounding it was the stage's model-call budget.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.repeated_queries import REPEATED_FAILURE_MARKER
from app.agents.settled_answer import (
    IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL,
    _a_tool_refused_identically,
    _a_tool_withheld_notice,
    _without_that_tool,
)


class _ToolMessage:
    type = "tool"

    def __init__(self, content: str) -> None:
        self.content = content


def _refusal_note(tool: str, count: int) -> _ToolMessage:
    """A refusal carrying the repeat note, as the guard writes it."""
    return _ToolMessage(
        '{"error": "Refusing to change \'app.js\': Node cannot parse this file"}'
        f"\n\n[This `{tool}` {REPEATED_FAILURE_MARKER} the {count} previous times "
        "you ran it in this stage, and nothing has changed it since. It will fail "
        "this way again. Change the arguments, create what is missing, or carry "
        "on without it.]"
    )


class TestCountingTheRepeats:
    def test_a_tool_repeated_to_the_threshold_is_named(self) -> None:
        messages = [
            _refusal_note("edit_artifact", n + 2)
            for n in range(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL)
        ]

        assert _a_tool_refused_identically(messages) == (
            "edit_artifact",
            IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL,
        )

    def test_one_short_of_the_threshold_is_left_alone(self) -> None:
        """The note is what lets a stage correct nearly-right arguments itself."""
        messages = [
            _refusal_note("replace_lines", n + 2)
            for n in range(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL - 1)
        ]

        assert _a_tool_refused_identically(messages) is None

    def test_an_ordinary_conversation_withholds_nothing(self) -> None:
        messages = [
            _ToolMessage("@@ lines 1-20 of 20 @@\nconst a = 1;"),
            _ToolMessage('{"path": "app.js", "status": "edited"}'),
        ]

        assert _a_tool_refused_identically(messages) is None

    def test_the_read_guard_s_own_phrase_is_not_claimed(self) -> None:
        """The backend writes the same words for a read, with no tool named.

        Reads have their own escalation, which says more about the file than
        this one can, so this must not take that path over.
        """
        messages = [
            _ToolMessage(
                f"This read {REPEATED_FAILURE_MARKER} the {n} previous times."
            )
            for n in range(2, 9)
        ]

        assert _a_tool_refused_identically(messages) is None

    def test_two_different_tools_do_not_add_up(self) -> None:
        """Each tool is counted on its own; a stage using two is not looping."""
        messages = [_refusal_note("edit_artifact", 2), _refusal_note("ls", 2)] * 2

        assert _a_tool_refused_identically(messages) is None

    def test_the_busiest_offender_is_the_one_named(self) -> None:
        messages = [
            *[_refusal_note("replace_lines", n) for n in range(2, 8)],
            _refusal_note("ls", 2),
        ]
        named = _a_tool_refused_identically(messages)

        assert named is not None and named[0] == "replace_lines"


class TestWhatIsTakenAway:
    TOOLS: list[dict[str, Any]] = [
        {"name": "edit_artifact"},
        {"name": "write_artifact"},
        {"name": "replace_lines"},
        {"name": "read_file"},
    ]

    class _Request:
        def __init__(self, tools: list[Any]) -> None:
            self.tools = tools

    def test_only_the_repeated_tool_goes(self) -> None:
        """A stage with no way to change a file at all could only give up."""
        kept = _without_that_tool(self._Request(self.TOOLS), "edit_artifact")

        assert kept is not None
        names = {tool["name"] for tool in kept}
        assert "edit_artifact" not in names
        assert {"write_artifact", "replace_lines", "read_file"} <= names

    def test_removing_the_only_tool_is_declined(self) -> None:
        """Leaving the model nothing to call is worse than the loop."""
        assert _without_that_tool(self._Request([{"name": "edit_artifact"}]), "edit_artifact") is None

    def test_a_tool_that_is_not_there_is_not_reported_as_removed(self) -> None:
        assert _without_that_tool(self._Request(self.TOOLS), "run_terminal_command") is None

    def test_no_tools_at_all_is_declined(self) -> None:
        assert _without_that_tool(self._Request([]), "edit_artifact") is None


class TestTheNotice:
    def test_it_names_the_tool_the_count_and_a_way_forward(self) -> None:
        """A tool that vanishes unexplained is a tool the model keeps calling."""
        notice = _a_tool_withheld_notice("edit_artifact", 15)

        assert "`edit_artifact`" in notice
        assert "15 times" in notice
        assert "write_artifact" in notice
        assert "blockers" in notice

    @pytest.mark.parametrize("tool", ("edit_artifact", "replace_lines", "run_terminal_command"))
    def test_the_notice_does_not_claim_everything_is_gone(self, tool: str) -> None:
        notice = _a_tool_withheld_notice(tool, 7)

        assert "Everything else still works" in notice


def test_the_threshold_leaves_room_for_the_note_to_work() -> None:
    """The note has to get a chance before the tool is taken.

    It starts at `REPEATS_BEFORE_SAYING_SO`, and the arguments that fail are
    sometimes nearly right - the note is what lets a stage fix them itself.
    """
    from app.agents.repeated_queries import REPEATS_BEFORE_SAYING_SO

    assert IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL > REPEATS_BEFORE_SAYING_SO
