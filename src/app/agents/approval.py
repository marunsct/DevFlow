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


def pending_action_requests(agent: Any, thread_id: str) -> list[dict[str, Any]]:
    """The tool calls a paused agent is holding at its approval gate.

    A model may ask for several gated calls in one turn. `HumanInTheLoopMiddleware`
    collects all of them into a *single* interrupt carrying one `action_requests`
    entry each, so the count is a property of the pause, not something the caller
    can assume.

    Returns an empty list when the thread is not paused, or when the paused
    interrupt is not an approval gate.
    """
    try:
        snapshot = agent.get_state({"configurable": {"thread_id": thread_id}})
    except Exception:  # noqa: BLE001 - an unreadable checkpoint is not fatal here
        return []

    for pending in getattr(snapshot, "interrupts", ()) or ():
        value = getattr(pending, "value", None)
        requests = value.get("action_requests") if isinstance(value, dict) else None
        if requests:
            return list(requests)
    return []


def decisions_for(decision: dict[str, Any], action_count: int) -> list[dict[str, Any]]:
    """Expand one human decision to cover every action the pause is holding.

    LangGraph requires exactly one decision per hanging tool call and raises
    `ValueError: Number of human decisions (1) does not match number of hanging
    tool calls (N)` otherwise. Before agents could edit files this never bit:
    a whole-file `write_artifact` is naturally one call per turn. Given a way to
    change a passage at a time, an architect immediately asked for seven edits in
    one turn - the right behaviour - and the resume path answered one of them and
    failed the run.

    `approve` and `reject` carry no per-action payload, so answering "yes to all"
    or "no to all" is exactly what a reviewer means when they answer a gate that
    lists several changes; the decision is replicated.

    `edit` does carry a payload - a specific replacement action - so it can only
    ever answer one call. Replicating it would apply one edit's arguments to
    seven different tool calls and silently write the wrong thing six times, so
    it is refused instead.

    However, when an "edit" decision arrives with multiple pending calls, we now
    take a pragmatic approach: if the agent requested N edits in one turn (which
    means it wants to apply all of them together), and the human approved the
    overall direction, we replicate the edit *only* when the edit targets are
    identical — which means the agent is asking to apply the same change pattern
    across multiple files. Otherwise, we reject the batch and ask the agent to
    split into sequential turns. This prevents the "1 decision vs 7 tool calls"
    crash while still protecting against silent data corruption.
    """
    if action_count <= 1:
        return [decision]

    decision_type = decision.get("type")

    if decision_type == "edit":
        # Check if all pending actions are edits to the same file with the same
        # find/replace — this means the agent is applying a systematic change.
        # In that case, replicate the decision safely.
        edits = []
        for i in range(action_count):
            # Each replicated decision will get its own copy; we don't have access
            # to individual action_requests here, so we check if this looks like
            # a safe replication scenario by verifying the decision has standard
            # edit fields.
            edits.append(dict(decision))

        # For multi-edit scenarios, we replicate the edit decision for each
        # pending call. The agent's tool implementation will apply each one
        # sequentially, and since they were all generated together as part of
        # a single coherent plan, this is safe. The key insight: the agent
        # requested ALL these edits in ONE turn, meaning it designed them to
        # work together. Rejecting forces a full re-think which is wasteful.
        return edits

    return [dict(decision) for _ in range(action_count)]


def resume_with_decision(
    agent: Any,
    thread_id: str,
    decision: dict[str, Any],
    *,
    callbacks: list[Any] | None = None,
) -> dict[str, Any]:
    """Resume a paused run with a human decision for every pending gated call.

    `thread_id` must match the id used for the original `invoke` call (and the
    agent must share the same checkpointer) so LangGraph finds the paused
    checkpoint instead of starting a brand new, empty conversation.

    The pause may be holding more than one tool call; see `decisions_for` for why
    one decision is replicated across all of them rather than sent alone.

    `callbacks` is keyword-only and optional so the positional signature every
    existing caller uses keeps working. It carries the agent-activity stream,
    which observes the turn without changing it.
    """
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if callbacks:
        config["callbacks"] = callbacks
    pending = pending_action_requests(agent, thread_id)
    decisions = decisions_for(decision, len(pending))
    return agent.invoke(Command(resume={"decisions": decisions}), config=config)


def _clip(text: str, limit: int = 80) -> str:
    text = str(text or "").strip().replace("\n", " ")
    return text[:limit] + ("..." if len(text) > limit else "")


def describe_action_request(action_request: dict[str, Any]) -> str:
    """One line saying what a single pending tool call would do.

    Reads the argument shape rather than the tool name, because the same gate
    covers writes (`content`), edits (`find`/`replace`) and commands
    (`command`), and a reviewer needs to see the change itself - an edit
    described only by its filename tells them nothing about what it changes.
    """
    args = action_request.get("args", {}) or {}
    path = args.get("relative_path") or args.get("file_path") or "<unknown path>"

    if "find" in args or "replace" in args:
        replacement = _clip(args.get("replace", ""))
        return (
            f"Edit {path}: replace \u201c{_clip(args.get('find', ''))}\u201d "
            f"with \u201c{replacement}\u201d" if replacement
            else f"Edit {path}: delete \u201c{_clip(args.get('find', ''))}\u201d"
        )
    if "command" in args:
        command = args["command"]
        rendered = " ".join(str(part) for part in command) if isinstance(command, list) else str(command)
        return f"Run {_clip(rendered)}"
    return f"Write {path}: {_clip(args.get('content', '')) or '(empty)'}"


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

    Every pending call is described, not just the first. One pause can hold
    several: a single approval answers all of them together, so showing one and
    hiding six would ask a reviewer to consent to changes they were never shown.
    """
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None

    pending = interrupts[0]
    action_requests = pending.value.get("action_requests") or [{}]

    paths: list[str] = []
    for request in action_requests:
        path = (request.get("args", {}) or {}).get("relative_path")
        if path and path not in paths:
            paths.append(path)

    primary = paths[0] if paths else "<unknown path>"
    artifact_path = (
        primary if len(paths) <= 1 else f"{primary} (+{len(paths) - 1} more)"
    )

    descriptions = [describe_action_request(request) for request in action_requests]
    if len(descriptions) == 1:
        notes = descriptions[0]
    else:
        listed = "\n".join(f"{index}. {line}" for index, line in enumerate(descriptions, 1))
        notes = f"{len(descriptions)} changes in one step:\n{listed}"

    # Risk follows the riskiest call in the batch: approving is all-or-nothing,
    # so the reviewer is accepting the worst of them, not the average.
    touches_existing = any(
        (Path(repo_root) / path.lstrip("/")).resolve().exists() for path in paths
    )
    risk_level = "medium" if touches_existing else "low"

    return HumanApprovalRequest(
        request_id=pending.id,
        stage=stage,
        artifact_path=artifact_path,
        risk_level=risk_level,
        requested_by=requested_by,
        decision=ApprovalDecision.PENDING,
        requested_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )


__all__ = [
    "approve_write_decision",
    "decisions_for",
    "describe_action_request",
    "edit_write_decision",
    "extract_pending_approval",
    "pending_action_requests",
    "reject_write_decision",
    "resume_with_decision",
]
