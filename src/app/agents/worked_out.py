"""A stage's conclusion survives its reply cap and its summaries; without thinking it is offered only what acts
(LF.1421, plan FX.5).

Measured on one medium run's failing fixers: two replies in each reasoned to the 12,000-token cap, about five minutes
apiece. Reply salvage asked for the answer from that reasoning and the reply then made one call, but the reasoning
itself - the analysis of the migration code the defect turned on - was carried at most in part, in messages the next
summary deleted. After the summary the fixer began again: "Now let me read the full content of the key files". And
after the second capped reply thinking was switched off for the rest of the stage with every tool still offered:
24 of 55 calls ran without reasoning, and one fixer asked for the same held file six times running.

So:

- the end of a reply's reasoning that reached its cap is kept for the stage (`keep`, from `models.reply_salvage`) and
  pinned at the end of every later request as "What you worked out" (`with_it_pinned`). It is added to the request,
  never to the stored conversation, so no summary can take it; a later capped reply replaces it.
- once thinking is off for the rest of a stage, each call is offered only the tools that change a file, run a command
  or give the answer (`acting_tools_only`, applied in `settled_answer`), and told why (`ACTING_ONLY_NOTICE`).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Where the stage keeps it (`app.agents.stage_memory`).
PURPOSE = "what the stage worked out"
#: The most of a capped reply's reasoning kept: its end, where a conclusion is.
KEPT_CHARACTERS = 3_000
#: Reasoning shorter than this says too little to pin.
LEAST_KEPT_CHARACTERS = 200
#: How the pinned section opens; also how a request already carrying it is known.
HEADING = "What you worked out"
PINNED = (
    HEADING + ": the end of your own reasoning in an earlier reply of this stage, which reached its length limit. The "
    "harness keeps it here, past every summary of this conversation, so the conclusion is not lost. Build on it; do "
    "not work it out again.\n\n"
)
#: The tools that change a file, run a command or give the answer; the answer tool is bound by the agent itself.
ACTING_TOOLS = frozenset({
    "write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines", "delete_artifact", "move_artifact",
    "run_terminal_command",
})
#: What a call offered only those tools is told.
ACTING_ONLY_NOTICE = (
    "Thinking is off for the rest of this stage, and without it a reply tends to repeat the call before it. So this "
    "call offers only what changes a file, runs a command or gives your answer: make the change your work so far "
    f"settled on (under \"{HEADING}\" below, when it is there), run the check that shows whether it held, or return "
    "your structured response."
)


def _its_end(text: str) -> str:
    """The last `KEPT_CHARACTERS` of `text`, started at a paragraph or a sentence where one is near."""
    text = str(text or "").strip()
    if len(text) <= KEPT_CHARACTERS:
        return text
    tail = text[-KEPT_CHARACTERS:]
    for mark in ("\n\n", "\n", ". "):
        at = tail.find(mark)
        if 0 <= at < KEPT_CHARACTERS // 3:
            return tail[at + len(mark):].strip()
    return tail.strip()


def keep(reasoning: str) -> None:
    """Keep the end of a capped reply's `reasoning` for the running stage, in place of any kept before. Never raises."""
    try:
        end = _its_end(reasoning)
        if len(end) < LEAST_KEPT_CHARACTERS:
            return
        from app.agents.stage_memory import store

        store(PURPOSE, {})["text"] = end
    except Exception:  # noqa: BLE001 - the reply stands either way
        logger.debug("Could not keep a capped reply's reasoning", exc_info=True)


def kept() -> str:
    """What the running stage worked out in its latest capped reply; "" for none or outside a graph run."""
    try:
        from app.agents.stage_memory import store

        return str(store(PURPOSE, {}).get("text") or "")
    except Exception:  # noqa: BLE001
        return ""


def section() -> str:
    """The pinned section for the running stage's next request; "" when it has nothing kept."""
    text = kept()
    return PINNED + text if text else ""


def with_it_pinned(request: Any) -> Any:
    """`request` with what the stage worked out appended as its last message; `request` itself when there is none."""
    try:
        pinned = section()
        messages = getattr(request, "messages", None)
        if not pinned or not isinstance(messages, list):
            return request
        return request.override(messages=[*messages, {"role": "user", "content": pinned}])
    except Exception:  # noqa: BLE001 - never fail a call over a note
        return request


def _named(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name") or (tool.get("function") or {}).get("name") or "")
    return str(getattr(tool, "name", "") or "")


def acting_tools_only(tools: list[Any]) -> list[Any] | None:
    """`tools` kept to those that change a file or run a command; None when that removes nothing, or when the stage
    has no tool that changes a file (a stage that only reads is left as it is)."""
    kept_tools = [tool for tool in tools if _named(tool) in ACTING_TOOLS]
    if len(kept_tools) == len(tools) or not any(_named(t) in ACTING_TOOLS - {"run_terminal_command"} for t in kept_tools):
        return None
    return kept_tools


__all__ = ["ACTING_ONLY_NOTICE", "ACTING_TOOLS", "HEADING", "KEPT_CHARACTERS", "PINNED", "acting_tools_only", "keep",
           "kept", "section", "with_it_pinned"]
