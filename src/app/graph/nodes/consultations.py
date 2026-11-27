"""The specialists' consultations before the specification, side by side in parallel mode (LF.1595).

    specialist_consultation -> consultation_worker x N -> consultation_gather -> principal_architect

Each consultation reads only the brief, the intake, the stack and the repository, never another specialist's advice,
so in parallel mode with more than one request allowed at once they are asked together, up to the server's slots
(`concurrent_requests`). Measured on one run: four consultations one after another took about seven minutes with two
model slots free. Linear mode, and a cap of one, still ask them one at a time in `specialist_consultation_node`.

The fan-out works as the sprint's reviews do (`app.graph.nodes.reviews`): a worker that pauses or is handed back
queues its update in `specialist_pauses`, the gather surfaces the oldest, and a resume re-enters
`specialist_consultation`, which sends again only the consultations without an answer.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.graph.context import GraphContext
from app.graph.workflow import WorkflowGraphState

#: The workflow's logger: the nodes log as they did inside the builder.
logger = logging.getLogger("app.graph.workflow")

#: The stage value that tells the router to fan the consultations out. Not a node.
FAN_OUT = "consultation_parallel"


def side_by_side() -> bool:
    """Whether consultations are asked together: the owner's parallel mode, with more than one request at once."""
    from app.graph.workflow import _in_parallel_mode, concurrent_requests

    return _in_parallel_mode() and concurrent_requests() > 1


def pending(state: Any) -> list[str]:
    """The consultations in flight that have no answer yet, in the order they were asked for."""
    done = {**(state.get("specialist_advice") or {}), **(state.get("consultation_results") or {})}
    return [role for role in (state.get("consultations_in_flight") or []) if role not in done]


def one_consultation(
    state: Any, config: RunnableConfig, ctx: GraphContext, role: str,
) -> tuple[dict[str, Any], list[str] | None]:
    """Ask one specialist: (the stage's update, its advice), the advice None when the update must be handed back.

    Handed back as it came when the stage paused or must retry (`_hand_back`).
    """
    from app.graph.workflow import (
        _as_text, _fast_delivery, _hand_back, _run_gated_agent, create_specialist_advice_agent,
    )

    from app.agents import domain_craft
    from app.agents.advice_sized import sized
    from app.agents.specialist_advice import advice_from, build_advice_request
    from app.stacks import framework_guidance

    brief = getattr(state.get("document"), "text", "") or ""
    agent = create_specialist_advice_agent(
        role, model=ctx.model if _fast_delivery() else ctx.judgement_model, checkpointer=ctx.checkpointer,
        repo_root=ctx.repo_root, allow_subdirectories=ctx.allow_subdirectories,
    )
    update = _run_gated_agent(
        state,
        config,
        stage_name=f"consult_{role}",
        agent=agent,
        # The framework's own security or testing guidance for its release, for those two roles (plan HK.9); the
        # data and service bars and the pack's design tokens (SK.2 with PQ.6 and PQ.9, off until measured).
        initial_request=framework_guidance.for_a_consultant(domain_craft.for_an_adviser(build_advice_request(
            role, brief, _as_text(state.get("product_intake")), _as_text(state.get("stack_selection"))
        ), role, state.get("stack_pack")), role, getattr(state.get("stack_selection"), "technology_stack", None),
            getattr(state.get("repository"), "root_path", None)),
        output_key="__advice__",
        next_stage="specialist_consultation",
    )
    if _hand_back(update, "__advice__"):
        return update, None
    advice = sized(advice_from(update.pop("__advice__")), role, brief)
    logger.info("Consulted the %s specialist before the specification: %d recommendation(s)", role, len(advice))
    return update, advice


def consultation_worker_node(state: dict, config: RunnableConfig, ctx: GraphContext) -> dict[str, Any]:
    """One specialist's consultation, beside the others. See `specialist_consultation_node`."""
    from app.graph.workflow import _as_a_queued_pause, _only_this_worker_s_pause

    role = state["__consult_role"]
    stage_name = f"consult_{role}"
    own: Any = dict(state)
    # A worker may only answer its own approval gate: see `specialist_worker_node`.
    own.update(_only_this_worker_s_pause(state, stage_name))
    update, advice = one_consultation(own, config, ctx, role)
    answered_in_a_batch = bool((state.get("queued_decisions") or {}).get(stage_name))
    if advice is None:
        return {"specialist_pauses": {stage_name: _as_a_queued_pause(
            state, stage_name, update, answered=answered_in_a_batch
        )}}
    finished: dict[str, Any] = {"consultation_results": {role: advice}}
    if answered_in_a_batch:
        finished["specialist_pauses"] = {stage_name: None}
    return finished


def consultation_gather_node(state: WorkflowGraphState, config: RunnableConfig) -> dict[str, Any]:  # noqa: ARG001
    """Where the consultations join: keep every answer, then surface a pause, send what is left, or hand on."""
    from app.graph.workflow import _QUEUED_AT, _handing_on, _queued_pauses, _the_pause_to_surface

    # Each answer is kept at once, so a resume or a switch to linear mode never asks that specialist again.
    kept = {
        "specialist_advice": {**(state.get("specialist_advice") or {}), **(state.get("consultation_results") or {})},
        "consultation_results": {},
    }
    pauses = _queued_pauses(state)
    if pauses:
        first = _the_pause_to_surface(pauses)
        surfaced = {key: value for key, value in pauses[first].items() if key != _QUEUED_AT}
        return {**surfaced, **kept, "specialist_pauses": {first: None}, "queued_decisions": {}}
    if pending(state):
        return {
            **kept,
            "stage": FAN_OUT,
            "pending_decision": None,
            "pending_inner_thread_id": None,
            "pending_approval": None,
            "queued_decisions": {},
        }
    return _handing_on(**kept, stage="principal_architect", consultations_in_flight=[])
