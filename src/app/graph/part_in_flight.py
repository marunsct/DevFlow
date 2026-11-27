"""The part of a stage written in parts that was still going when its node was entered again.

A stage written in parts (the acceptance suite a batch or a file at a time) runs each part as a stage call of its
own, one after another, inside one entry of its node. Every gated tool call pauses the node (under auto-approve too),
and the node is entered again with the decision; a stopped worker enters it again with the part's conversation cut
off. A part is otherwise taken as done when its criteria have tests, but a part's tests are on disk as soon as it
writes them, before it has run them or answered.

Measured on one run (18 criteria in three files): part 1 wrote its file, and its next tool call paused the node. On
the decision the loop found part 1's criteria covered, went on to part 2, and the stage call made for part 2 resumed
the pending conversation - part 1's, with part 1's opening - which ran the suite and gave part 1's answer under part
2's name. The decision was still in the state the node was handed, so part 3 and the fill resumed the same finished
conversation and gave the same answer again; no part 2 or 3 was ever written, and the suite went to its review with
twelve criteria untested.

So the part in flight - the one whose gate the pending decision answers, or whose conversation a stopped worker cut
off - goes on first, whatever is on disk; the parts before it are done (parts run in order); and every part after it
is handed the state without the pause, so it starts its own conversation.
"""

from __future__ import annotations

from typing import Any, Sequence


def going_on(state: Any, config: Any, agent: Any, stages: Sequence[str]) -> str | None:
    """The one of `stages` (in order) that was still going when the node was entered again, or None."""
    from app.graph import abandoned_threads
    from app.graph.workflow import APPROVAL_PAUSE_PREFIX, _the_stage_that_paused

    paused = state.get("pending_decision") is not None or str(state.get("stage") or "").startswith(APPROVAL_PAUSE_PREFIX)
    if paused and (stage := _the_stage_that_paused(state)) in stages:
        return stage
    root = getattr(state.get("repository"), "root_path", None)
    outer = ((config or {}).get("configurable") or {}).get("thread_id")
    for stage in stages:
        if abandoned_threads.cut_off(root, outer, stage, agent):
            return stage
    return None


def without_the_pause(state: Any) -> dict[str, Any]:
    """`state` as a part after the one in flight is handed it: no gate's decision, and no conversation to resume."""
    return {**state, "pending_decision": None, "pending_inner_thread_id": None, "pending_approval": None}


__all__ = ["going_on", "without_the_pause"]
