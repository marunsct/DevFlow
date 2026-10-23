"""Every refused call but the latest folded to a line in what the model is sent (behind `REFUSALS_FOLDED`).

A model reads its own earlier mistakes as a pattern to continue: measured
(Sinha et al., 2025), a non-thinking model makes more errors the more of its own
errors its context holds, and dropping them helps substantially; SWE-agent
keeps a refused command out of the history altogether and asks again. One run's
fixer had a dozen refused shell lines in its conversation - each with the
refusal's full explanation - and sent a thirteenth.

So in what each call is sent, every refusal but the latest keeps one line: what
kind of refusal it was. The latest stays whole, since it is the one the model is
answering. The stored conversation is untouched, and the counts the guards keep
(`settled_answer`) read it, not this.
"""

from __future__ import annotations

from typing import Any

from app.switches import is_on

#: `REFUSALS_FOLDED` set to on or off overrides this.
ON_BY_DEFAULT = False
#: How a folded refusal begins; also how one already folded is known.
FOLDED = "[An earlier call was refused:"
#: How much of the refusal a folded one keeps.
KEPT_CHARACTERS = 160


def enabled() -> bool:
    return is_on("REFUSALS_FOLDED", ON_BY_DEFAULT)


def folded(messages: list[Any]) -> tuple[list[Any], int]:
    """`messages` with every refused tool result but the latest cut to one line, and how many were. Never raises."""
    from app.agents.settled_answer import _REFUSED, _the_kind_of

    refused = [i for i, m in enumerate(messages)
               if getattr(m, "type", None) == "tool" and _REFUSED.match(str(getattr(m, "content", "") or ""))]
    if len(refused) < 2:
        return messages, 0
    out = list(messages)
    count = 0
    for index in refused[:-1]:
        message = out[index]
        text = str(getattr(message, "content", "") or "")
        if text.startswith(FOLDED):
            continue
        try:
            out[index] = message.model_copy(update={"content": f"{FOLDED} {_the_kind_of(text)[:KEPT_CHARACTERS]}]"})
            count += 1
        except Exception:  # noqa: BLE001 - kept whole
            continue
    return out, count


def with_old_refusals_folded(request: Any) -> Any:
    """`request` with its older refusals folded, when on; as it was otherwise. Never raises."""
    if not enabled():
        return request
    try:
        messages = list(getattr(request, "messages", None) or [])
        new, count = folded(messages)
        return request.override(messages=new) if count else request
    except Exception:  # noqa: BLE001
        return request


__all__ = ["FOLDED", "KEPT_CHARACTERS", "ON_BY_DEFAULT", "enabled", "folded", "with_old_refusals_folded"]
