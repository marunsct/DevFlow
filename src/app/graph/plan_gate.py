"""The plan gate (plan WS.3): the sprint plan waits for the owner's go before any sprint is built.

A run's review policy holds it (`sprint_plan`, chosen per run with the other reviews, and changeable while the run is
live). With it on, the scrum master's plan goes to `user_review_sprint_plan` instead of straight to the technical
lead. The owner answers with a go, or with a direction: the scrum master then plans again with the owner's words in
its request. Nobody answering is an answer too: after the gate's time the run goes on by itself, and its decision
record says so (`app.server.approval_timeouts`).
"""

from __future__ import annotations

import os
from typing import Any

#: How long the plan gate waits for the owner before the run goes on by itself, when the run sets no time of its own.
DEFAULT_PLAN_GATE_MINUTES = 15
#: The stage a run waiting at the plan gate is in.
PLAN_GATE_STAGE = "awaiting_user_review:sprint_plan"


def plan_gate_minutes() -> int:
    """Minutes the plan gate waits: `PLAN_GATE_MINUTES`, else `DEFAULT_PLAN_GATE_MINUTES`; never less than 1."""
    raw = os.environ.get("PLAN_GATE_MINUTES", "").strip()
    try:
        return max(1, int(raw)) if raw else DEFAULT_PLAN_GATE_MINUTES
    except ValueError:
        return DEFAULT_PLAN_GATE_MINUTES


def _status_of(review: Any) -> str:
    status = review.get("status") if isinstance(review, dict) else getattr(review, "status", "")
    return str(getattr(status, "value", status) or "")


def owners_changes_to_the_plan(state: Any) -> list[str]:
    """What the owner asked to change at the plan gate, when the plan was sent back; [] otherwise.

    Only while the gate's review stands at "changes requested": a revision comment from any other review never
    reaches the scrum master through here.
    """
    from app.graph.workflow import SPRINT_PLAN_REVIEW

    review = (state.get("reviews") or {}).get(SPRINT_PLAN_REVIEW)
    if review is None or _status_of(review) != "changes_requested":
        return []
    return [str(comment).strip() for comment in state.get("revision_comments") or [] if str(comment).strip()]


def the_owners_direction(changes: list[str], previous_plan: str) -> str:
    """What the scrum master's request adds when the owner sent the plan back at the plan gate."""
    if not changes:
        return ""
    asked = "\n".join(f"- {change}" for change in changes)
    earlier = f"\n\nThe plan the owner read:\n{previous_plan.strip()}" if previous_plan.strip() else ""
    return (
        "\n\nTHE OWNER'S DIRECTION AT THE PLAN GATE\n"
        "The owner read your sprint plan before any sprint was built and asked for these changes:\n"
        f"{asked}\n"
        "Plan the sprints again so that every change asked for is made. Keep each part of the plan the owner "
        "did not ask to change, and keep every acceptance criterion in exactly one sprint."
        f"{earlier}"
    )


def after_the_plan(update: dict[str, Any], gate_on: bool, answered_the_owner: bool) -> dict[str, Any]:
    """The scrum master's finished update, sent to the plan gate when it is on.

    Only a plan handed to the technical lead goes to the gate: a planner asked once more, or a run failed for a plan
    that assigns nothing, goes where it was going. The owner's direction, once planned with, is cleared so the
    technical lead does not read it as a revision of its own plan.
    """
    if update.get("stage") != "technical_lead":
        return update
    if answered_the_owner:
        update["revision_comments"] = []
    if gate_on:
        update["stage"] = "user_review_sprint_plan"
    return update
