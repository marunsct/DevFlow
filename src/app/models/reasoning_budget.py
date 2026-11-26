"""A per-request reasoning budget, where the model's server enforces one (IK.3, IK.4; behind `REASONING_BUDGET`).

A reply that reasons to its cap writes nothing, and reply salvage then answers from that reasoning in a second
request, after the whole cap is spent. Measured on one architect reply: 32,000 tokens of reasoning (7 minutes), then
a 12,097-token salvage (3 minutes), for an answer of about 10,000. Some model servers (llama.cpp's
`reasoning_budget_tokens`) end the thinking at a number of tokens the request names and make the model answer, so a
reply always has room to answer in the same request.

What a server does is measured by the model's diagnosis (`diagnostics._budget_probe`: a question that reasons past
the bound, unbounded, at 64 tokens, at 0 and at the share of the cap a real call gives reasoning) and kept with the
model; `diagnostics.apply` hands it here. Enforced (the reasoning stopped at the bound) and usable (a reply cut to
that share still answered right) are kept apart (LF.1588). Then, with the switch on:

- a stage call capped at N tokens on a self-hosted server that enforces a usable budget is sent a budget of N less the room
  an answer needs (`answer_room`), and `reply_salvage.ENOUGH` as the words written where the reasoning was ended -
  not a small budget: 74 good replies of an earlier model finished between 16,000 and 32,768 tokens, so the budget
  only removes the case where nothing is left to answer with. The budget is per thinking block, so a reply can
  still reach its cap: salvage stays the fallback;
- the calls that must answer without reasoning (`thinking.answering_without_reasoning`), on a model whose chat
  template has no thinking switch, are sent a budget of 0 where the diagnosis found a zero budget still answers,
  else `SMALL_BUDGET` (IK.4). Measured: a helper capped at 2,048 tokens spent 1,833 of them reasoning.

Off in code until measured (owner's rule for efficiency changes): an answer written after its reasoning was cut may
be worse, as one written by salvage may.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

NAME = "REASONING_BUDGET"
#: The budget field llama.cpp reads, and the words it writes where it ends the reasoning.
BUDGET_FIELD = "reasoning_budget_tokens"
MESSAGE_FIELD = "reasoning_budget_message"
#: The other spelling a server may read the budget under.
OTHER_BUDGET_FIELD = "thinking_budget_tokens"
#: A switched-off call's budget where a zero budget was not measured to answer.
SMALL_BUDGET = 256
#: The share of a stage call's cap kept for its answer: measured, an architect's answer was about 10,000 tokens of a
#: 32,000-token cap, so about 12,000 is kept there and reasoning ends at about 20,000.
ANSWER_SHARE = 0.375
#: The record a budget sent leaves in the run's transcript, once per stage visit, and its words (the firing signal).
RECORD_KIND = "reasoning_budget"
SAID = "reasoning held to a budget of"

#: (address, model) of servers measured to enforce a budget, and the budget that turns thinking off on each.
ENFORCED: set[tuple[str, str]] = set()
OFF_BUDGETS: dict[tuple[str, str], int] = {}
_NOTED: set[tuple[str, str]] = set()
_LOCK = threading.Lock()


class _ReasoningBudget:
    """`REASONING_BUDGET` as the switch registry reads one: off in code, on in the compose file to be measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("On a model server its diagnosis measured to enforce a per-request reasoning budget, a stage call "
                   "is sent a budget of its reply cap less the room its answer needs, so a reply always answers in "
                   "the same request; calls meant to answer without reasoning get a zero or 256-token budget where "
                   "the model's template has no thinking switch; and the effort levels the server's chat template "
                   "lists below low (minimal) are accepted. Measured: one architect reply reasoned 32,000 tokens, "
                   "then took a 12,097-token salvage, for a 10,000-token answer.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on(NAME, _ReasoningBudget.ON_BY_DEFAULT)


reasoning_budget_switch = _ReasoningBudget()


def learnt(server: tuple[str, str], settings: Any) -> None:
    """Keep what the diagnosis `settings` measured of `server`'s budget. Never raises."""
    try:
        with _LOCK:
            if getattr(settings, "reasoning_budget", False):
                # A stage call's budget only where a reply cut to its share of the cap still answered right; the
                # budget that turns thinking off is for calls meant to answer without reasoning (LF.1588).
                if getattr(settings, "reasoning_budget_usable", False):
                    ENFORCED.add(server)
                else:
                    ENFORCED.discard(server)
                if not getattr(settings, "template_thinking_switch", False):
                    OFF_BUDGETS[server] = 0 if getattr(settings, "zero_budget_answers", False) else SMALL_BUDGET
                else:
                    OFF_BUDGETS.pop(server, None)
            else:
                ENFORCED.discard(server)
                OFF_BUDGETS.pop(server, None)
    except Exception:  # noqa: BLE001
        logger.debug("Could not keep the server's reasoning budget", exc_info=True)


def fields(budget: int) -> dict[str, Any]:
    """The request fields that hold reasoning to `budget` tokens."""
    from app.models.reply_salvage import ENOUGH

    return {BUDGET_FIELD: int(budget), MESSAGE_FIELD: ENOUGH}


def off_budget(server: tuple[str, str]) -> int | None:
    """The budget that turns thinking off for `server`'s model, with the switch on; None to send none."""
    if not reasoning_budget_switch.enabled():
        return None
    with _LOCK:
        return OFF_BUDGETS.get(server)


def answer_room(cap: int) -> int:
    """The tokens of a reply capped at `cap` kept for its answer."""
    from app.agents.thinking import MIN_ANSWER_TOKENS

    return max(MIN_ANSWER_TOKENS, int(cap * ANSWER_SHARE))


def budget_for(cap: int) -> int | None:
    """The reasoning budget of a reply capped at `cap`, or None when the cap leaves no room to share."""
    from app.agents.thinking import MIN_THINKING_TOKENS

    budget = int(cap) - answer_room(int(cap))
    return budget if budget >= MIN_THINKING_TOKENS else None


def is_off(extra: dict) -> bool:
    """Whether `extra` (a request's `extra_body`) holds reasoning to a switched-off call's budget."""
    budget = extra.get(BUDGET_FIELD, extra.get(OTHER_BUDGET_FIELD)) if isinstance(extra, dict) else None
    return isinstance(budget, int) and not isinstance(budget, bool) and 0 <= budget <= SMALL_BUDGET


def with_the_reasoning_budget(payload: dict, server: tuple[str, str]) -> dict:
    """`payload` with a reasoning budget of its cap less its answer's room, where the switch is on, `server` is
    self-hosted and enforces one, and the call names a cap and no budget of its own; else as it was. Never raises."""
    try:
        if not reasoning_budget_switch.enabled():
            return payload
        with _LOCK:
            if server not in ENFORCED:
                return payload
        from app.models.endpoints import is_self_hosted

        if not is_self_hosted(server[0]):
            return payload
        extra = payload.get("extra_body") if isinstance(payload.get("extra_body"), dict) else {}
        if BUDGET_FIELD in extra or OTHER_BUDGET_FIELD in extra:
            return payload
        cap = payload.get("max_tokens") or payload.get("max_completion_tokens")
        if not isinstance(cap, int) or cap <= 0:
            return payload
        budget = budget_for(cap)
        if budget is None:
            return payload
        payload["extra_body"] = {**extra, **fields(budget)}
        _note(budget, cap)
    except Exception:  # noqa: BLE001 - the request as it was
        logger.debug("Could not add the reasoning budget", exc_info=True)
    return payload


def _note(budget: int, cap: int) -> None:
    """One transcript record a stage visit: the budget sent, in the words the switch register looks for."""
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config, record

        run, stage = _run_id_from_config(), _stage_from_config("")
        if not run:
            return
        with _LOCK:
            if (str(run), str(stage)) in _NOTED:
                return
            _NOTED.add((str(run), str(stage)))
        record(run, stage, RECORD_KIND, message=f"{SAID} {budget:,} tokens of a {cap:,}-token reply")
    except Exception:  # noqa: BLE001
        logger.debug("Could not record the reasoning budget", exc_info=True)


def effects_lines(records: Any) -> list[str]:
    """`loop.sh effects` (IK.3/IK.4): stage visits whose calls were sent a budget, and the replies that still reached
    their cap (salvaged), so a run with the switch on is read against one without."""
    budgeted = 0
    salvaged = 0
    for record in records or ():
        if not isinstance(record, dict):
            continue
        if record.get("kind") == RECORD_KIND:
            budgeted += 1
        elif record.get("kind") == "model_response" and str(record.get("salvaged") or "") == "reasoning":
            salvaged += 1
    head = "IK.3 stage visits whose replies were held to a reasoning budget"
    return [(f"  {budgeted:>4}  {head}" if budgeted else f"     -  {head}: not reached")
            + f" (replies cut off while reasoning and salvaged: {salvaged}; fewer expected)"]


__all__ = ["ANSWER_SHARE", "BUDGET_FIELD", "ENFORCED", "MESSAGE_FIELD", "NAME", "OFF_BUDGETS", "RECORD_KIND", "SAID",
           "SMALL_BUDGET", "answer_room", "budget_for", "effects_lines", "fields", "is_off", "learnt", "off_budget",
           "reasoning_budget_switch", "with_the_reasoning_budget"]
