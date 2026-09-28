"""A parallel worker must not resume a sibling's paused inner thread.

Measured on one run. One `call_id` appeared three times in the transcript
under three different stage names, with three `tool_result` records microseconds
apart - `specialist_ui_ux_1` got `"status": "edited"` and the other two got
"already contains the text you asked to put there", because the first execution
had applied the edit the other two were still asking for:

    05:23:51.760  specialist_ui_ux_1    edit_artifact   W36iNNhb...
    05:23:51.765  specialist_testing_2  edit_artifact   W36iNNhb...
    05:23:51.774  specialist_ui_ux_0    edit_artifact   W36iNNhb...

Which calls were multiplied says where it came from. Every one was gated:

    write_artifact 4, replace_lines 5, edit_artifact 3, run_terminal_command 2

and every ungated call ran exactly once - read_file 50, ls 11, glob 5, grep 3,
read_command_output 7. Three models choosing the same call in the same
microsecond is not a thing; one shared field is. `pending_inner_thread_id` is a
single value, the dispatcher re-sends every task that has no output yet on a
resume, and each of those workers resumed whatever thread that field held.

`run_terminal_command` in that list is the sharp end: the shell commands ran
three times too. And because every repeat counter in this harness counts per
stage, three executions raised each counter three times - the repeated-read
tally reached 21 for what was around seven real reads, so the read refusals and
the withholding rungs fired at a third of the repetition they describe.

Nothing here is about any language or framework. It is the fan-out's own
bookkeeping.
"""

from __future__ import annotations

from app.graph.workflow import (
    APPROVAL_PAUSE_PREFIX,
    _only_this_worker_s_pause,
    _queued_pauses,
)

#: The three stages that shared one thread, as the run named them.
OWNER = "specialist_testing_2"
OTHERS = ("specialist_ui_ux_0", "specialist_ui_ux_1")

OWNER_THREAD = "thread-48170b27:specialist_testing_2:4c718ab9"
UI_UX_0_THREAD = "thread-48170b27:specialist_ui_ux_0:11111111"


def _paused_state(**over):
    """The state as it stands when one pause has been surfaced."""
    state = {
        "stage": f"{APPROVAL_PAUSE_PREFIX}{OWNER}",
        "pending_decision": {"type": "approve"},
        "pending_inner_thread_id": OWNER_THREAD,
        "pending_approval": {"tool": "edit_artifact"},
        "specialist_pauses": {},
    }
    state.update(over)
    return state


class TestTheOwnerIsUntouched:
    def test_the_stage_whose_gate_it_is_keeps_everything(self) -> None:
        assert _only_this_worker_s_pause(_paused_state(), OWNER) == {}

    def test_so_its_own_resume_still_happens(self) -> None:
        """An empty override means the worker's state is left exactly as it was."""
        state = _paused_state()
        merged = {**state, **_only_this_worker_s_pause(state, OWNER)}

        assert merged["pending_decision"] == {"type": "approve"}
        assert merged["pending_inner_thread_id"] == OWNER_THREAD


class TestASiblingIsNotGivenTheDecision:
    def test_no_sibling_resumes_the_owner_s_thread(self) -> None:
        """The regression itself: three workers, one thread, three executions."""
        state = _paused_state()

        for other in OTHERS:
            override = _only_this_worker_s_pause(state, other)

            assert override["pending_inner_thread_id"] != OWNER_THREAD
            assert override["pending_decision"] is None

    def test_a_sibling_with_no_pause_of_its_own_starts_clean(self) -> None:
        state = _paused_state()

        override = _only_this_worker_s_pause(state, "specialist_ui_ux_0")

        assert override["pending_inner_thread_id"] is None
        assert override["pending_approval"] is None
        # No gate of its own to re-surface, so `stage` is left alone.
        assert "stage" not in override

    def test_the_owner_s_approval_is_not_handed_to_a_sibling(self) -> None:
        """A sibling inheriting `pending_approval` answers a call it never made."""
        state = _paused_state()

        assert _only_this_worker_s_pause(state, OTHERS[0])["pending_approval"] is None


class TestASiblingKeepsItsOwnPause:
    """A worker whose pause is queued behind another must not lose it."""

    def test_it_resumes_its_own_thread_and_not_the_owner_s(self) -> None:
        state = _paused_state(
            specialist_pauses={
                "specialist_ui_ux_0": {
                    "pending_inner_thread_id": UI_UX_0_THREAD,
                    "pending_approval": {"tool": "write_artifact"},
                }
            }
        )

        override = _only_this_worker_s_pause(state, "specialist_ui_ux_0")

        assert override["pending_inner_thread_id"] == UI_UX_0_THREAD
        assert override["pending_decision"] is None

    def test_it_declares_its_own_gate_so_the_pause_costs_no_model_call(self) -> None:
        """`_run_gated_agent` hands a recognised gate straight back."""
        state = _paused_state(
            specialist_pauses={
                "specialist_ui_ux_0": {"pending_inner_thread_id": UI_UX_0_THREAD}
            }
        )

        override = _only_this_worker_s_pause(state, "specialist_ui_ux_0")

        assert override["stage"] == f"{APPROVAL_PAUSE_PREFIX}specialist_ui_ux_0"

    def test_a_drained_pause_is_not_a_pause(self) -> None:
        """`None` is how a surfaced pause is marked answered."""
        state = _paused_state(specialist_pauses={"specialist_ui_ux_0": None})

        override = _only_this_worker_s_pause(state, "specialist_ui_ux_0")

        assert override["pending_inner_thread_id"] is None
        assert "stage" not in override


class TestTheQueueReader:
    def test_it_drops_the_drained_entries(self) -> None:
        pauses = {"a": {"pending_inner_thread_id": "x"}, "b": None}

        assert _queued_pauses({"specialist_pauses": pauses}) == {
            "a": {"pending_inner_thread_id": "x"}
        }

    def test_all_drained_reads_as_nothing_queued(self) -> None:
        """Otherwise the gather node surfaces a pause that was already answered."""
        assert _queued_pauses({"specialist_pauses": {"a": None, "b": None}}) == {}

    def test_no_channel_at_all_is_nothing_queued(self) -> None:
        assert _queued_pauses({}) == {}
        assert _queued_pauses({"specialist_pauses": None}) == {}


class TestLinearModeIsUnaffected:
    def test_a_stage_running_alone_owns_its_gate(self) -> None:
        """Linear mode reaches `_run_gated_agent` directly; this is the parallel
        site only, and the owner path must be a no-op so it stays that way."""
        # The marker and the thread come from the same pause update, so they
        # always name the same stage; a fixture where they disagree describes
        # no state the graph produces.
        state = _paused_state(
            stage=f"{APPROVAL_PAUSE_PREFIX}test_round_0",
            pending_inner_thread_id="thread-48170b27:test_round_0:5a5a5a5a",
        )

        assert _only_this_worker_s_pause(state, "test_round_0") == {}


class TestDrainingOnePauseKeepsTheRest:
    """`specialist_gather` surfaces one pause per superstep.

    It used to return `specialist_pauses: {}`, which `_merge_or_reset` reads as
    "start again" and which threw away the other workers' paused inner threads.
    They then had nothing of their own to resume, and the single
    `pending_inner_thread_id` field is what they reached for instead.
    """

    def test_one_key_set_to_none_leaves_the_others_queued(self) -> None:
        from app.graph.workflow import _merge_or_reset

        queue = {
            "specialist_testing_2": {"pending_inner_thread_id": OWNER_THREAD},
            "specialist_ui_ux_0": {"pending_inner_thread_id": UI_UX_0_THREAD},
        }

        after = _merge_or_reset(queue, {"specialist_testing_2": None})

        assert after["specialist_testing_2"] is None
        assert after["specialist_ui_ux_0"] == {"pending_inner_thread_id": UI_UX_0_THREAD}
        assert _queued_pauses({"specialist_pauses": after}) == {
            "specialist_ui_ux_0": {"pending_inner_thread_id": UI_UX_0_THREAD}
        }

    def test_an_empty_update_would_have_dropped_them_all(self) -> None:
        """Why the fix cannot simply return the remaining subset or `{}`."""
        from app.graph.workflow import _merge_or_reset

        queue = {"specialist_ui_ux_0": {"pending_inner_thread_id": UI_UX_0_THREAD}}

        assert _merge_or_reset(queue, {}) == {}

    def test_a_subset_cannot_remove_a_key_either(self) -> None:
        from app.graph.workflow import _merge_or_reset

        queue = {"a": {"pending_inner_thread_id": "x"}, "b": {"pending_inner_thread_id": "y"}}

        # Returning only what should remain merges the surfaced one back.
        assert "a" in _merge_or_reset(queue, {"b": {"pending_inner_thread_id": "y"}})


class TestTheStateAWorkerReallySees:
    """What reaches a worker on a parallel resume.

    `specialist_dispatch` returns `stage: specialist_dispatch_parallel` before
    the router fans out, so the `awaiting_approval:<name>` marker every fixture
    above carries is gone by the time a worker runs. The first version of the
    ownership check read that marker, matched nobody, and took the decision
    away from its owner as well - the one run livelock.
    """

    @staticmethod
    def _as_dispatched() -> dict:
        return {
            "stage": "specialist_dispatch_parallel",
            "pending_decision": {"type": "approve"},
            "pending_inner_thread_id": OWNER_THREAD,
            "pending_approval": {"tool": "edit_artifact"},
            "specialist_pauses": {OWNER: None},
        }

    def test_the_owner_is_still_recognised(self) -> None:
        assert _only_this_worker_s_pause(self._as_dispatched(), OWNER) == {}

    def test_a_sibling_is_still_refused_the_decision(self) -> None:
        for other in OTHERS:
            override = _only_this_worker_s_pause(self._as_dispatched(), other)

            assert override["pending_decision"] is None
            assert override["pending_inner_thread_id"] != OWNER_THREAD


class TestNamingTheStageThatPaused:
    def test_from_the_thread_id(self) -> None:
        from app.graph.workflow import _the_stage_that_paused

        assert _the_stage_that_paused({"pending_inner_thread_id": OWNER_THREAD}) == OWNER

    def test_an_outer_id_with_colons_of_its_own(self) -> None:
        from app.graph.workflow import _the_stage_that_paused

        thread = "tenant:a:b:specialist_backend_1:0123abcd"

        assert _the_stage_that_paused({"pending_inner_thread_id": thread}) == "specialist_backend_1"

    def test_the_marker_when_there_is_no_thread(self) -> None:
        from app.graph.workflow import _the_stage_that_paused

        state = {"stage": f"{APPROVAL_PAUSE_PREFIX}test_round_0"}

        assert _the_stage_that_paused(state) == "test_round_0"

    def test_nothing_paused(self) -> None:
        from app.graph.workflow import _the_stage_that_paused

        assert _the_stage_that_paused({"stage": "specialist_dispatch_parallel"}) is None
