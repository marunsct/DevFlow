"""Telling a stage it is repeating a dead call is not enough on its own.

The repeat note already says "It will fail this way again. Change the arguments,
create what is missing, or carry on without it." Measured across two runs, a
stage read that and carried straight on:

    One run  specialist_backend_0  15 identical `edit_artifact` calls, each
                  refused because the file would not parse afterwards
    one run  specialist_backend_3   7 identical `replace_lines` calls, the
                  same refusal every time

The first was the largest single class of failed call in its run, and neither was
visible until the audit tool was fixed: its failure regex was anchored, so the
bracketed repeat note pushed the error off the start of the string and the
counting stopped exactly when the repeating began. One run's true total was
29 failed calls against the 15 first reported.

Reads already escalate from a note to withholding the tool after
`READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL`. A mutation that cannot succeed had
no such step, so the only thing bounding it was the stage's model-call budget.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.settled_answer import (
    IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL,
    _a_tool_refused_identically,
    _a_tool_withheld_notice,
    _without_that_tool_in,
    _without_the_read_tools_in,
)


class _ToolMessage:
    type = "tool"

    def __init__(self, content: str, call_id: str = "") -> None:
        self.content = content
        self.tool_call_id = call_id


class _AiMessage:
    type = "ai"
    content = ""

    def __init__(self, calls: list[dict]) -> None:
        self.tool_calls = calls


def _conversation(
    times: int,
    *,
    tool: str = "replace_lines",
    args: dict | None = None,
    result: str = '{"error": "Refusing to change \'app.js\': Node cannot parse this file"}',
    vary: bool = False,
) -> list[object]:
    """`times` turns of one tool call and its result, as a transcript holds them."""
    messages: list[object] = []
    for n in range(times):
        call_args = dict(args or {"relative_path": "app.js", "start_line": 78})
        if vary:
            call_args["start_line"] = 78 + n
        messages.append(_AiMessage([{"name": tool, "args": call_args, "id": f"c{n}"}]))
        messages.append(_ToolMessage(result, f"c{n}"))
    return messages


class TestCountingTheRepeats:
    def test_a_call_repeated_to_the_threshold_is_named(self) -> None:
        enough = _conversation(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL)

        assert _a_tool_refused_identically(enough) == (
            "replace_lines",
            IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL,
        )

    def test_one_short_of_the_threshold_is_left_alone(self) -> None:
        """The guard's own note is what lets a stage fix nearly-right arguments."""
        nearly = _conversation(IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL - 1)

        assert _a_tool_refused_identically(nearly) is None

    def test_any_guard_s_wording_counts(self) -> None:
        """The first version matched one phrase and missed every other guard.

        Measured on one run: `specialist_testing_2` called
        `read_command_output` seven times with a workspace path where a journal
        reference belongs. Its guard answered well - "looks like a path rather
        than a journal reference ... read it with `read_file`" - in its own
        words, so a matcher keyed on `repeated_queries`' phrasing escalated
        nothing.
        """
        journal = _conversation(
            7,
            tool="read_command_output",
            args={"reference": "task-manager/package.json"},
            result=(
                '{"error": "No journalled output named '
                "'task-manager/package.json'"
                ', and this run has nothing journalled"}'
            ),
        )

        assert _a_tool_refused_identically(journal) == ("read_command_output", 7)

    def test_a_repeat_note_in_front_of_the_error_still_counts(self) -> None:
        """A transcript carries the note first; an anchored match lost the error."""
        noted = _conversation(
            IDENTICAL_FAILURES_BEFORE_WITHHOLDING_THE_TOOL,
            result=(
                "[This `replace_lines` failed the same way the 2 previous times]"
                '\n\n{"error": "Refusing to change this file"}'
            ),
        )

        assert _a_tool_refused_identically(noted) is not None

    def test_the_same_tool_with_different_arguments_is_not_a_loop(self) -> None:
        """A stage working through a file calls one tool many times, legitimately."""
        working = _conversation(7, vary=True)

        assert _a_tool_refused_identically(working) is None

    def test_calls_that_succeeded_are_not_counted(self) -> None:
        answered = _conversation(7, result="@@ lines 1-20 of 20 @@\nconst a = 1;")

        assert _a_tool_refused_identically(answered) is None

    def test_an_ordinary_conversation_withholds_nothing(self) -> None:
        assert _a_tool_refused_identically([_ToolMessage("@@ lines 1-3 of 3 @@")]) is None

    def test_two_different_tools_do_not_add_up(self) -> None:
        """Each call is counted on its own; a stage using two is not looping."""
        messages = [
            *_conversation(2),
            *_conversation(2, tool="ls", args={"path": "app"}, result="Error: Path 'app': path_not_found"),
        ]

        assert _a_tool_refused_identically(messages) is None

    def test_the_busiest_offender_is_the_one_named(self) -> None:
        messages = [
            *_conversation(5),
            *_conversation(1, tool="ls", args={"path": "app"}, result="Error: Path 'app': path_not_found"),
        ]
        named = _a_tool_refused_identically(messages)

        assert named is not None and named[0] == "replace_lines"

    def test_a_result_with_no_call_to_pair_with_is_ignored(self) -> None:
        """A trimmed conversation can open on a result whose call is gone."""
        orphan = [_ToolMessage('{"error": "nope"}', "missing")] * 9

        assert _a_tool_refused_identically(orphan) is None


class TestWhatIsTakenAway:
    TOOLS: list[dict[str, Any]] = [
        {"name": "read_file"},
        {"name": "read_repository_file"},
        {"name": "edit_artifact"},
        {"name": "write_artifact"},
        {"name": "replace_lines"},
    ]

    def test_only_the_repeated_tool_goes(self) -> None:
        """A stage with no way to change a file at all could only give up."""
        kept = _without_that_tool_in(self.TOOLS, "edit_artifact")

        assert kept is not None
        names = {tool["name"] for tool in kept}
        assert "edit_artifact" not in names
        assert {"write_artifact", "replace_lines"} <= names

    def test_both_rungs_compose_on_one_call(self) -> None:
        """The reason they are separate functions over one list.

        `repeated` used to be computed only when nothing else had set a
        correction, and the read rung sets one constantly - 114 times in
        one run - so a stage looping on `edit_artifact` never lost it.
        Measured on one run, which repeated one past the threshold and was
        never withheld once.
        """
        without_reads = _without_the_read_tools_in(self.TOOLS)
        assert without_reads is not None

        both = _without_that_tool_in(without_reads, "edit_artifact")
        assert both is not None
        assert [tool["name"] for tool in both] == ["write_artifact", "replace_lines"]

    def test_removing_the_only_tool_is_declined(self) -> None:
        """Leaving the model nothing to call is worse than the loop."""
        assert _without_that_tool_in([{"name": "edit_artifact"}], "edit_artifact") is None

    def test_a_tool_that_is_not_there_is_not_reported_as_removed(self) -> None:
        assert _without_that_tool_in(self.TOOLS, "run_terminal_command") is None

    def test_no_tools_at_all_is_declined(self) -> None:
        assert _without_that_tool_in([], "edit_artifact") is None
        assert _without_the_read_tools_in([]) is None

    def test_a_list_with_no_readers_is_left_alone(self) -> None:
        assert _without_the_read_tools_in([{"name": "edit_artifact"}]) is None

    def test_a_tool_object_is_named_like_a_mapping(self) -> None:
        """Providers hand these over as objects as well as dicts."""

        class Tool:
            def __init__(self, name: str) -> None:
                self.name = name

        kept = _without_that_tool_in([Tool("edit_artifact"), Tool("write_artifact")], "edit_artifact")

        assert kept is not None and [t.name for t in kept] == ["write_artifact"]


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
    the run. Measured on one run: `specialist_testing_5` made 11 read calls
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


def test_the_read_rung_does_not_starve_the_repeat_rung() -> None:
    """Both rungs must be evaluated on the same call.

    `repeated` was computed only when nothing else had set a correction, and the
    read rung sets one whenever a stage has been refused three redundant reads -
    114 times in one run. A stage that loops on `edit_artifact` loops on
    reads too, so the reads always won and the mutation loop was never bounded.
    One run repeated an `edit_artifact` past the threshold and was never
    withheld it once.
    """
    import inspect

    from app.agents import settled_answer

    source = inspect.getsource(settled_answer.build_settled_answer_middleware)
    guarded = source.split("reading_nothing_new = _refused_reads(messages)", 1)[1]

    assert "repeated = None if correction else" not in guarded, (
        "the repeat rung is gated on no other correction existing, which the "
        "read rung above it almost always provides"
    )
    read_rung = guarded.find("READ_REFUSALS_BEFORE_WITHHOLDING_THE_TOOL")
    repeat_rung = guarded.find("_a_tool_refused_identically(messages)")

    assert read_rung != -1 and repeat_rung != -1
    assert "if not correction:" in guarded[:read_rung], (
        "a schema or budget correction should still take priority over both"
    )


class TestAQueryThatKeepsAnsweringTheSame:
    """One run's technical lead called `ls {"path": "./"}` about twenty times in
    three minutes; every call succeeded with the same listing, so the refusal
    rung never saw it."""

    SAME = "['/docs/', '/shop/']\n\n[This `ls` returned exactly what it returned the 3 previous times ...]"

    def test_it_is_named_at_the_threshold(self) -> None:
        from app.agents.settled_answer import (
            IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL,
            _a_query_answered_identically,
        )

        messages = _conversation(
            IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL, tool="ls", args={"path": "./"}, result=self.SAME
        )
        assert _a_query_answered_identically(messages) == ("ls", IDENTICAL_ANSWERS_BEFORE_WITHHOLDING_THE_TOOL)
        assert _a_query_answered_identically(messages[:-2]) is None

    def test_a_listing_without_the_note_is_not_counted(self) -> None:
        from app.agents.settled_answer import _a_query_answered_identically

        messages = _conversation(8, tool="ls", args={"path": "./"}, result="['/docs/', '/shop/']")
        assert _a_query_answered_identically(messages) is None

    def test_the_middleware_takes_that_tool_away(self) -> None:
        from types import SimpleNamespace

        from pydantic import BaseModel

        from app.agents.settled_answer import build_settled_answer_middleware

        class _Answer(BaseModel):
            ok: bool = True

        class _Request:
            def __init__(self, messages, tools):
                self.messages, self.tools, self.model, self.model_settings = messages, tools, None, {}

            def override(self, **changes):
                request = _Request(changes.get("messages", self.messages), changes.get("tools", self.tools))
                return request

        sent: list = []
        tools = [SimpleNamespace(name="ls"), SimpleNamespace(name="read_file"), SimpleNamespace(name="glob")]
        messages = [
            SimpleNamespace(type="human", content="Plan the milestone."),
            *_conversation(5, tool="ls", args={"path": "./"}, result=self.SAME),
        ]
        middleware = build_settled_answer_middleware(_Answer, "technical_lead", step_limit=60)
        middleware.wrap_model_call(_Request(messages, tools), lambda request: sent.append(request))

        assert [tool.name for tool in sent[0].tools] == ["read_file", "glob"]
        assert "`ls` has been withheld" in str(sent[0].messages[-1]["content"])
