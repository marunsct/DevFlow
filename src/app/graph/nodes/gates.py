"""The optional human reviews: where each one sends the run when approved and when changes are asked for.

Each is `_run_review_gate` with its review point, the artifact a person reviews,
and the two stages it hands on to. See `app.graph.nodes` for how these are
registered and why their helpers are imported from `app.graph.workflow` when
they run.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.graph.workflow import WorkflowGraphState


def user_review_product_intake_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    from app.graph.workflow import PRODUCT_INTAKE_REVIEW, _run_review_gate

    return _run_review_gate(
        state,
        config,
        review_point=PRODUCT_INTAKE_REVIEW,
        artifact_id="product-intake",
        approved_next="tools_models",
        changes_next="product_manager",
    )


def user_review_specification_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    from app.graph.workflow import SPECIFICATION_REVIEW, _run_review_gate

    return _run_review_gate(
        state,
        config,
        review_point=SPECIFICATION_REVIEW,
        artifact_id="technical-specification",
        approved_next="scaffold",
        changes_next="principal_architect",
    )


def user_review_acceptance_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    from app.graph.workflow import ACCEPTANCE_REVIEW, _run_review_gate

    return _run_review_gate(
        state,
        config,
        review_point=ACCEPTANCE_REVIEW,
        artifact_id="acceptance-tests",
        approved_next="scrum_master",
        changes_next="acceptance_author",
    )


def user_review_sprint_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    from app.graph.workflow import SPRINT_REVIEW, _run_review_gate

    sprint_index = state.get("current_sprint_index", 0)
    sprints = state.get("sprint_plan").sprints if state.get("sprint_plan") else []
    has_more_sprints = sprint_index < len(sprints) - 1

    return _run_review_gate(
        state,
        config,
        review_point=SPRINT_REVIEW,
        artifact_id="sprint-milestone",
        approved_next="sprint_advance" if has_more_sprints else "release",
        # A requested change becomes a change request with its own
        # acceptance test before the sprint is planned again. See
        # `app.graph.delivery.change_request`.
        changes_next="change_request",
    )


def user_review_escalation_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    from app.graph.workflow import ESCALATION_REVIEW, _run_review_gate

    return _run_review_gate(
        state,
        config,
        review_point=ESCALATION_REVIEW,
        artifact_id="escalation",
        approved_next="escalation_accept",
        changes_next="escalation_retry",
    )


def user_review_release_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:
    from app.graph.workflow import RELEASE_REVIEW, _run_review_gate

    return _run_review_gate(
        state,
        config,
        review_point=RELEASE_REVIEW,
        artifact_id="release",
        approved_next="complete",
        changes_next="change_request",
    )
