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
    """A refusal carrying the repeat note, in the order a transcript holds it.

    Note first, then the error. Copied from run-1bdbc08a rather than composed:
    `repeated_queries` returns the note as a suffix, and what reaches the model
    has it in front, so a fixture built from the returning code would have tested
    the wrong string.
    """
    return _ToolMessage(
        f"[This `{tool}` {REPEATED_FAILURE_MARKER} the {count} previous times you "
        "ran it in this stage, and nothing has changed it since. It will fail this "
        "way again. Change the arguments, create what is missing, or carry on "
        "without it.]\n\n"
        '{"error": "Refusing to change \'simple-to-do-list-app/app.js\': Node '
        'cannot parse this file on line 92: SyntaxError: Unexpected token"}'
    )


def test_the_fixture_matches_what_a_transcript_really_holds() -> None:
    """Guards the fixture above against drifting from production.

    The tool name has to sit before the marker for the name to be found, and the
    count has to read as "the N previous times".
    """
    content = _refusal_note("replace_lines", 12).content
    marker = content.find(REPEATED_FAILURE_MARKER)

    assert marker > 0
    assert "`replace_lines`" in content[:marker]
    assert "the 12 previous times" in content[marker:]
    assert content.lstrip().startswith("[This ")


class TestCountingTheRepeats:
    def test_a_tool_repeated_to_the_threshold_is_named(self) -> None:
        notes = [
            _refusal_note("edit_artifact", n)
            for n in range(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL)
        ]

        assert _a_tool_refused_identically(notes) == (
            "edit_artifact",
            IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL,
        )

    def test_one_short_of_the_threshold_is_left_alone(self) -> None:
        """The note is what lets a stage correct nearly-right arguments itself."""
        notes = [
            _refusal_note("replace_lines", n)
            for n in range(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL - 1)
        ]

        assert _a_tool_refused_identically(notes) is None

    def test_the_number_the_note_quotes_is_not_trusted(self) -> None:
        """It counts the run, not the stage, so it must not stand in for a tally.

        Measured on run-1bdbc08a: `specialist_ui_ux_0` made one `edit_artifact`
        call and was told it had failed the same way the 3 previous times;
        `specialist_testing_4` made two and was told 5. The count lives on the
        middleware instance, which outlives the stage. Believing it would take a
        tool away from a stage on its first use of it.
        """
        assert _a_tool_refused_identically([_refusal_note("replace_lines", 12)]) is None

    def test_a_note_without_a_number_still_counts_as_one(self) -> None:
        """Each note is one call this stage really made, number or not."""
        message = _ToolMessage(
            f"[This `edit_artifact` {REPEATED_FAILURE_MARKER} before.]"
        )
        enough = [message] * IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL

        assert _a_tool_refused_identically(enough) == (
            "edit_artifact",
            IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL,
        )

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
        messages = [_refusal_note("edit_artifact", 1), _refusal_note("ls", 1)] * 3

        assert _a_tool_refused_identically(messages) is None

    def test_the_busiest_offender_is_the_one_named(self) -> None:
        messages = [
            *[_refusal_note("replace_lines", n) for n in range(5)],
            _refusal_note("ls", 1),
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


class TestTheReadOrdinalIsNotTheStages:
    """The refusal quotes a number that looks like the stage's tally and is not.

    "it is the 34th time this stage has asked for content it already has" counts
    the run. Measured on run-1bdbc08a: `specialist_testing_5` made 11 read calls
    in total and was told 34; `specialist_ui_ux_1` made 14 and was told 29;
    `specialist_ui_ux_0` was refused once and told 33.

    `workspace_backend._the_repeated_read_tally` keeps the count in
    `stage_memory.store("repeated_reads", own)`, and `store` hands back the
    per-instance fallback whenever `current_stage_key()` cannot resolve a thread.
    That instance outlives the stage, so the tally is the run's.

    This is a guard against using it. A withholding keyed on that number would
    take a stage's read tool away on its first refusal, as soon as any earlier
    stage in the run had pushed the shared count past three.
    """

    @staticmethod
    def _refusal(ordinal: str) -> _ToolMessage:
        from app.agents.workspace_backend import READ_REFUSED_MARKER

        return _ToolMessage(
            f"{READ_REFUSED_MARKER} 'app.js' again: this returns nothing you have "
            f"not already been given, and it is the {ordinal} time this stage has "
            "asked for content it already has."
        )

    def test_a_single_refusal_quoting_a_high_ordinal_counts_as_one(self) -> None:
        from app.agents.settled_answer import (
            READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL,
            _refused_reads,
        )

        counted = _refused_reads([self._refusal("34th")])

        assert counted == 1, (
            "the ordinal counts the run, not the stage, so one refusal must not "
            "read as thirty-four"
        )
        assert counted < READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL

    def test_refusals_actually_present_are_what_counts(self) -> None:
        from app.agents.settled_answer import _refused_reads

        assert _refused_reads([self._refusal("2nd")] * 5) == 5

    def test_a_conversation_with_no_refusal_is_untouched(self) -> None:
        from app.agents.settled_answer import _refused_reads

        assert _refused_reads([_ToolMessage("@@ lines 1-20 of 20 @@\nconst a = 1;")]) == 0
