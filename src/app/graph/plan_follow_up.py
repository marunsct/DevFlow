"""A lead's plan that still needs judgement is asked again in the lead's own conversation (plan PA.6).

Measured on a medium run: 12 plans in 4 visits, and each plan sent back started a fresh conversation of about
147,000 characters - the specification, the sprint, the files - to fix one or two lines of the plan. The lead has
just written the plan it is asked to fix, in a conversation that still holds everything it read, so one more turn
there carries only what is wrong with it. The harness makes the mechanical repairs first
(`app.analysis.plan_repairs`); a turn that does not answer better leaves the plan to the fresh visit, as before.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: What the turn adds to the readiness note: the plan is in the conversation already.
_WHOLE_PLAN_AGAIN = (
    "\n\nThe plan you just returned is above in this conversation; the harness has already made the repairs it can "
    "make itself. Return the whole plan again through your answer, with these problems fixed and the rest as it was."
)


def asked_again(agent: Any, update: dict[str, Any], config: Any, problems: list[str]) -> Any | None:
    """The plan the lead returns when asked once more in the conversation that wrote `update`'s plan, or None.

    None when the conversation is not known, the turn fails, pauses for an approval, or returns no plan. Never
    raises.
    """
    threads = [str(thread) for thread in update.get("inner_thread_ids") or [] if str(thread)]
    if not threads or not problems:
        return None
    try:
        from app.analysis.work_orders import readiness_feedback
        from app.graph.workflow import APP_RUN_ID_KEY, _nudge_for_the_structured_response
        from app.server.agent_stream import build_activity_callbacks

        run_id = ((config or {}).get("configurable") or {}).get(APP_RUN_ID_KEY)
        followed = _nudge_for_the_structured_response(
            agent, threads[-1], build_activity_callbacks(run_id, "technical_lead"), None,
            getattr(agent, "workflow_response_format", None), run_id, "technical_lead",
            text=readiness_feedback(problems).strip() + _WHOLE_PLAN_AGAIN,
        )
    except Exception:  # noqa: BLE001 - the fresh visit follows, as before
        logger.warning("Could not ask the lead again in its own conversation", exc_info=True)
        return None
    if not followed or followed.get("__interrupt__"):
        return None
    plan = followed.get("structured_response")
    if plan is None or not hasattr(plan, "delegated_tasks"):
        return None
    from app.agents.model_output import answer_without_leaked_turns

    return answer_without_leaked_turns(plan)


__all__ = ["asked_again"]
