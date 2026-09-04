"""Human-in-the-loop decision helpers shared by every role agent.

Step 3.2 gates every artifact write behind a human decision. These helpers are
plain, generic functions for building that decision and for resuming a paused
run — nothing here is specific to the Product Manager, so every future role
agent (Tools and Models Architect, Principal Architect, specialists, ...)
should import from here instead of re-implementing the same dict shapes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.types import Command

from app.state import ApprovalDecision, HumanApprovalRequest


def approve_write_decision() -> dict[str, Any]:
    """Build a resume decision that lets the pending artifact write proceed as-is."""
    return {"type": "approve"}


def edit_write_decision(relative_path: str, content: str) -> dict[str, Any]:
    """Build a resume decision that approves the write but changes its target or content."""
    return {
        "type": "edit",
        "edited_action": {
            "name": "write_artifact",
            "args": {"relative_path": relative_path, "content": content},
        },
    }


def reject_write_decision(message: str | None = None) -> dict[str, Any]:
    """Build a resume decision that blocks the pending artifact write.

    `message` becomes the human-readable reason relayed back to the model, so it
    understands why the write did not happen instead of retrying blindly.
    """
    decision: dict[str, Any] = {"type": "reject"}
    if message:
        decision["message"] = message
    return decision


def resume_with_decision(agent: Any, thread_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    """Resume a paused run with one human decision for the pending artifact write.

    `thread_id` must match the id used for the original `invoke` call (and the
    agent must share the same checkpointer) so LangGraph finds the paused
    checkpoint instead of starting a brand new, empty conversation.
    """
    return agent.invoke(
        Command(resume={"decisions": [decision]}),
        config={"configurable": {"thread_id": thread_id}},
    )


def extract_pending_approval(
    result: dict[str, Any],
    repo_root: str | Path,
    *,
    requested_by: str,
    stage: str,
) -> HumanApprovalRequest | None:
    """Turn a paused graph result into our typed approval contract, or None.

    `agent.invoke(...)` returns normally (it does not raise) when the graph
    pauses at an interrupt; the pending request lives under the `__interrupt__`
    key. This function converts that raw LangGraph payload into our own
    `HumanApprovalRequest` (see `app.state`) so the rest of the workflow, tests,
    and any future UI share one stable shape instead of reaching into LangGraph
    internals directly.
    """
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None

    pending = interrupts[0]
    action_request = pending.value["action_requests"][0]
    args = action_request.get("args", {})
    relative_path = args.get("relative_path", "<unknown path>")
    content = args.get("content", "")
    summary = content[:80] + ("..." if len(content) > 80 else "")

    target = (Path(repo_root) / relative_path).resolve()
    risk_level = "medium" if target.exists() else "low"

    return HumanApprovalRequest(
        request_id=pending.id,
        stage=stage,
        artifact_path=f"{relative_path}",
        risk_level=risk_level,
        requested_by=requested_by,
        decision=ApprovalDecision.PENDING,
        requested_at=datetime.now(timezone.utc).isoformat(),
        notes=summary,
    )


__all__ = [
    "approve_write_decision",
    "edit_write_decision",
    "extract_pending_approval",
    "reject_write_decision",
    "resume_with_decision",
]
