"""A stage's opening leaves it room to work before its first summary (plan PA.1, always on, by measured size).

Measured on a medium run's first-sprint builders (91,776-token slot, 32,000 held for the reply, summary trigger
43,020 tokens): the opening request was a 21,451-character system prompt, 23,564 characters of tool descriptions and
a 134,786-character first message (102,415 of it the project memory, 30,784 of that the specification), which the
server counted as 47,124 tokens - 110% of the trigger before the stage read anything. The summariser fires on the
server's reported count as soon as the conversation has enough messages to cut, so the backend builder was summarised
8 times in 48 replies and read schemas.py 9 times; the UI builder 4 times in 20, styles.css 8 times. Every builder's
`request_budget` record said the memory would be cut from 128,334 characters to 76,313, and nothing was cut:
`REQUEST_BUDGET_FOR_EVERY_STAGE` is off, because small runs open past the budget too and score full marks.

What tells the two apart is the framing the budget never counted. Where the system prompt, the tool descriptions, the
request and the memory together reach `OPENING_SHARE` of the stage's summary trigger, the memory is cut to the budget
the request already has (`project_memory._within_its_budget`, `request_budget.opening_target`), whatever the switch
says. Measured on four small runs (182,272-token slot): every stage's opening was at most 0.70 of its trigger, so
nothing there changes; on the medium run, the builders (1.38), the lead (1.35), the suite writers (1.15-1.28) and the
QA lead (1.24) pass it.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: The share of the summary trigger an opening may fill before its memory is cut to the budget: a stage left at least
#: a fifth of the trigger, a few command outputs, before its first summary.
OPENING_SHARE = 0.8

#: What a record of a memory cut by size says (`request_budget.noted`): not the switch's words, so the switch-firing
#: check does not count it as `REQUEST_BUDGET_FOR_EVERY_STAGE`.
SAID = "The stage's opening filled {share:.2f} of its summary trigger, so its memory was cut to the request's budget"


def framing_of(request: Any) -> int:
    """The characters of a model call's system prompt and tool descriptions: what every call of the stage carries
    before its messages. 0 when they cannot be read."""
    size = 0
    try:
        system = getattr(request, "system_message", None)
        text = getattr(system, "content", None) if system is not None else getattr(request, "system_prompt", None)
        if isinstance(text, list):
            text = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in text)
        size += len(str(text or ""))
    except Exception:  # noqa: BLE001 - no system prompt counted
        pass
    for tool in list(getattr(request, "tools", None) or []):
        try:
            if isinstance(tool, dict):
                size += len(json.dumps(tool, default=str))
                continue
            from langchain_core.utils.function_calling import convert_to_openai_tool

            size += len(json.dumps(convert_to_openai_tool(tool), default=str))
        except Exception:  # noqa: BLE001 - a tool that cannot be described counts its name alone
            size += len(str(getattr(tool, "name", "") or ""))
    return size


def share_of_the_trigger(characters: int, model: Any = None) -> float:
    """`characters` of an opening as a share of `model`'s summary trigger (the deployment's when None)."""
    from app.agents.context_budget import CHARS_PER_TOKEN, ContextBudget

    try:
        from app.models import environment_of

        budget = ContextBudget.resolve(environment_of(model))
    except Exception:  # noqa: BLE001 - the deployment's own window
        budget = ContextBudget.resolve()
    trigger = max(1, budget.trigger_tokens)
    return characters / CHARS_PER_TOKEN / trigger


def leaves_no_room(characters: int, model: Any = None) -> float | None:
    """The opening's share of its trigger when it reaches `OPENING_SHARE`; None when it leaves room. Never raises."""
    try:
        share = share_of_the_trigger(characters, model)
    except Exception:  # noqa: BLE001 - nothing is cut when the trigger cannot be read
        logger.debug("Could not read a stage's summary trigger", exc_info=True)
        return None
    return share if share >= OPENING_SHARE else None


__all__ = ["OPENING_SHARE", "SAID", "framing_of", "leaves_no_room", "share_of_the_trigger"]
