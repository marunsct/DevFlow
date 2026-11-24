"""The ends of a sprint and of a run: on to the next sprint, complete, or failed with a reason.

See `app.graph.nodes` for how these are registered and why their helpers are
imported from `app.graph.workflow` when they run.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")


def sprint_advance_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    from app.graph.workflow import _record_sprint_summary

    summary = _record_sprint_summary(state, "Completed")
    # The best product of the sprint just accepted is not the next sprint's: found in a code review, its record
    # stayed, and the next sprint's first batch was undone for passing fewer tests than the last one's best.
    from app.graph import best_attempt

    if state.get("repository") is not None:
        best_attempt.forget(state["repository"].root_path)
    # What this sprint hands the next one's lead: findings it neither fixed
    # nor was blocked by, and what failed repeatedly. See `app.sprint.record`.
    latest = (summary.get("sprint_attempts") or [{}])[-1]
    # The next sprint's tests are written at its start where the suite is written a sprint at a time (LF.1266).
    from app.graph.acceptance_nodes import before_the_lead

    next_stage = before_the_lead(state) if state.get("repository") is not None else "technical_lead"
    return {
        **summary,
        "carried_forward": list(latest.get("carried_forward") or []),
        "lessons": list(latest.get("lessons") or []),
        "sprint_findings": [],
        "review_advice": [],
        "nothing_left_but_carried": None,
        "stage": next_stage,
        "current_sprint_index": state.get("current_sprint_index", 0) + 1,
        # clear previous sprint's milestone state so it doesn't pollute the next sprint
        "milestone_plan": None,
        "specialist_outputs": {},
        "remediation": None,
        "defect_cursor": 0,
        "test_round": 0,
        "revision_comments": [],
        "milestone_revision_count": 0,
        "sprint_replan_count": 0,
        "sprint_best_history": [],
    }


def complete_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
    """The run is done - and the sprint that finished it needs its summary.

    Only `sprint_advance_node` recorded one, and the last sprint never
    advances: it routes straight here. So a three-sprint plan wrote
    `sprint_1` and `sprint_2` and stopped, and the sprint that actually
    delivered the product was the one with nothing to show for it.
    """
    from app.graph.workflow import (
        _commit_the_last_records, _record_sprint_summary, _sprint_already_summarised,
    )

    if _sprint_already_summarised(state):
        _commit_the_last_records(state["repository"].root_path)
        return {"stage": "complete"}
    summary = _record_sprint_summary(state, "Completed")
    _commit_the_last_records(state["repository"].root_path)
    return {**summary, "stage": "complete"}


def failed_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
    """Terminal failure - always with a reason, even when nothing set one.

    Every deliberate route to this node carries an `error`. One route does
    not, and cannot: `_owning_node` answers `"failed"` for a stage no node
    owns, which is what stops an unrecognised stage raising `KeyError` inside
    LangGraph and taking the run down. It is a router. It has no state to
    write a reason to.

    So the run arrived here with `error` unset, and the runner records
    `record.error = state.get("error")` - leaving a row that says `failed`
    and nothing else. One run is one of those: 73 minutes of work,
    approvals answered every 30 seconds, then `failed` at 11:53 with a null
    error, no event and no way to tell what had happened. Diagnosing it
    started by ruling out the three causes it was not.

    `stage` still holds whatever routed here - nothing has overwritten it yet
    - so the reason can name it.
    """
    if str(state.get("error") or "").strip():
        return {"stage": "failed"}

    routed_from = str(state.get("stage") or "").strip()
    if routed_from and routed_from != "failed":
        reason = (
            f"The run was routed to failure from stage '{routed_from}', which no "
            "node owns, so nothing recorded why.\n\n"
            "A stage value is set either by a node handing on or by a resume "
            "reading the checkpoint. One that no node answers for means a stage "
            "name was written that the graph has no node for - check "
            "`_NODE_NAMES`, `_ITERATED_STAGE_OWNERS` and whatever last set "
            "`stage`. The work already done is on disk and the checkpoint is "
            "intact."
        )
    else:
        reason = (
            "The run reached its failure state without recording a reason. "
            "Every deliberate failure names one, so this is a route that does "
            "not - the stage it came from is in the run's events and its "
            "transcript."
        )
    logger.error("Run failed with no reason recorded; routed from %r", routed_from)
    return {"stage": "failed", "error": reason}
