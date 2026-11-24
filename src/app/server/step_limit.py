"""A run that reaches the outer graph's step limit goes on from its checkpoint, unless it has stopped moving.

`app.graph.workflow.DEFAULT_RECURSION_LIMIT` bounds the supersteps of one `invoke`. A run with no human gate is one
invoke from its first stage to its release, so the limit was in effect a budget for the whole run: measured on one
medium run, a sprint with many fix stages reached it with every stage healthy, the runner had nothing to catch it
with, and the run was recorded failed. LangGraph raises the error at a superstep boundary with the next step already
checkpointed, so a fresh `invoke(None)` on the same thread goes on from exactly there - the path a resume takes.

The limit still has a job: it is how often a run's progress is looked at. A run that stops on it again with nothing
moved since the stop before - no new sprint, no new test or acceptance round, no defect closed or worked on, no stage
output it did not have - is a loop, and after `MOST_STOPS_WITHOUT_PROGRESS` of those it is left paused for a person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Stops on the step limit in a row with nothing moved before the run is left for a person. Each stop is one full
#: step limit of supersteps, so two is twice that many with no round, sprint, defect closed or worked on, or new stage
#: output. The first stop of a segment always goes on: there is no earlier stop to compare it with.
MOST_STOPS_WITHOUT_PROGRESS = 2

#: The stage outputs whose first appearance is progress in the stages before the sprints.
_MILESTONE_OUTPUTS = (
    "product_intake", "tools_models", "stack_selection", "technical_specification", "architecture_review",
    "sprint_plan", "milestone_plan", "security_review", "milestone_review",
)


def a_step_limit_stop(graph: Any, thread_id: str) -> bool:
    """Whether the graph's last invoke ended on its own step limit, with work left to go on with.

    A `GraphRecursionError` from a stage's own agent passes up through the outer graph as the same error type; that
    one left its node failed (the checkpoint's pending task carries the error), and is not this. Never raises.
    """
    try:
        snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    except Exception:  # noqa: BLE001 - unreadable: not a stop that can be gone on from
        return False
    if snapshot is None or not tuple(getattr(snapshot, "next", ()) or ()):
        return False
    try:
        # LangGraph's `StateSnapshot.tasks`: each pending node of the checkpoint, with the error it raised, if any.
        pending = tuple(snapshot.tasks or ())
    except AttributeError:
        pending = ()
    return not any(getattr(entry, "error", None) for entry in pending)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def progress_mark(values: dict[str, Any] | None) -> tuple:
    """What a run has done that only moves forward: its sprint, its rounds, its closed defects, the fix stages run on
    them, its stage outputs.

    A fix stage that ran counts even when it closed nothing: each defect's fix stages are bounded on their own, so
    the count cannot grow for ever, and a round of many fixers that close nothing is slow, not a loop. Read from the
    checkpointed state alone. A count that a new sprint resets (the closed defects of its remediation)
    still marks a change, because the sprint index changes with it. Never raises.
    """
    values = values or {}
    try:
        defects = _field(values.get("remediation"), "defects", None) or []
        closed = sum(1 for defect in defects if str(_field(defect, "status", "open")) != "open")
        worked = sum(len(_field(defect, "attempts", None) or []) for defect in defects)
        return (
            int(values.get("current_sprint_index") or 0),
            len(values.get("sprint_attempts") or []),
            int(values.get("test_round") or 0),
            int(values.get("acceptance_round") or 0),
            closed,
            worked,
            tuple(name for name in _MILESTONE_OUTPUTS if values.get(name) is not None),
        )
    except Exception:  # noqa: BLE001 - an unreadable state shows no progress
        return ()


@dataclass
class StepLimitStops:
    """The step-limit stops of one segment of a run, and whether the next one may be gone on from."""

    most_without_progress: int = MOST_STOPS_WITHOUT_PROGRESS
    stops: int = 0
    without_progress: int = 0
    _last: tuple | None = field(default=None, repr=False)

    def go_on_after(self, mark: tuple) -> bool:
        """Count one stop at `mark`; whether the run goes on from it (False: it is left for a person)."""
        self.stops += 1
        if self._last is not None and mark == self._last:
            self.without_progress += 1
        else:
            self.without_progress = 0
        self._last = mark
        return self.without_progress < self.most_without_progress


__all__ = ["MOST_STOPS_WITHOUT_PROGRESS", "StepLimitStops", "a_step_limit_stop", "progress_mark"]
