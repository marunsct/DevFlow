"""Parallel approval pauses are answered in the order they were queued.

On one run a testing task and three interface tasks paused in one superstep.
`specialist_gather` surfaced `sorted(pauses)[0]` - the stage name - so
`specialist_testing_4` went first, ran one gated call, paused again and went
first again, at least eleven times, while the three `specialist_ui_ux_*`
pauses, queued since the fan-out began, never came up. Nothing here names a
language, a framework or a kind of product.
"""
from __future__ import annotations

from app.graph.workflow import _QUEUED_AT, _as_a_queued_pause, _the_pause_to_surface


def _pause(stage: str) -> dict:
    return {"stage": f"awaiting_approval:{stage}", "pending_inner_thread_id": f"t:{stage}:0000"}


class TestTheQueue:
    def test_the_longest_waiting_pause_is_surfaced_whatever_its_name(self) -> None:
        pauses = {
            "specialist_testing_4": {**_pause("specialist_testing_4"), _QUEUED_AT: 300.0},
            "specialist_ui_ux_0": {**_pause("specialist_ui_ux_0"), _QUEUED_AT: 100.0},
            "specialist_ui_ux_1": {**_pause("specialist_ui_ux_1"), _QUEUED_AT: 101.0},
        }
        assert _the_pause_to_surface(pauses) == "specialist_ui_ux_0"

    def test_entries_without_a_time_come_after_and_fall_back_to_name(self) -> None:
        pauses = {"b": _pause("b"), "a": _pause("a"), "c": {**_pause("c"), _QUEUED_AT: 5.0}}
        assert _the_pause_to_surface(pauses) == "c"
        assert _the_pause_to_surface({"b": _pause("b"), "a": _pause("a")}) == "a"


class TestAPlaceInTheQueue:
    def test_a_pause_still_waiting_keeps_its_place(self) -> None:
        state = {"specialist_pauses": {"specialist_ui_ux_0": {**_pause("specialist_ui_ux_0"), _QUEUED_AT: 100.0}}}
        entry = _as_a_queued_pause(state, "specialist_ui_ux_0", _pause("specialist_ui_ux_0"))
        assert entry[_QUEUED_AT] == 100.0

    def test_a_new_gate_after_an_answered_one_joins_the_back(self) -> None:
        state = {"specialist_pauses": {"specialist_testing_4": None}}
        entry = _as_a_queued_pause(state, "specialist_testing_4", _pause("specialist_testing_4"))
        assert entry[_QUEUED_AT] > 1_000_000_000

    def test_the_repeat_offender_no_longer_jumps_the_queue(self) -> None:
        """The run's shape: the testing task re-pauses after every answer."""
        queue = {
            "specialist_ui_ux_0": {**_pause("specialist_ui_ux_0"), _QUEUED_AT: 100.0},
            "specialist_ui_ux_1": {**_pause("specialist_ui_ux_1"), _QUEUED_AT: 101.0},
        }
        answered = {"specialist_pauses": {"specialist_testing_4": None}}
        queue["specialist_testing_4"] = _as_a_queued_pause(answered, "specialist_testing_4", _pause("specialist_testing_4"))
        order = []
        while queue:
            first = _the_pause_to_surface(queue)
            order.append(first)
            queue.pop(first)
        assert order == ["specialist_ui_ux_0", "specialist_ui_ux_1", "specialist_testing_4"]
