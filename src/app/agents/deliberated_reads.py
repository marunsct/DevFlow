"""The reply after one that reasoned at length and then only read goes without thinking (`LONG_REASONING_BEFORE_A_READ`).

Measured on local Qwen3.6 models in one run: many replies reasoned 12,000-33,000 tokens, five to seven minutes each,
and then made one or two `read_file` calls - a testing builder five times over, an acceptance-suite author three
times, a fix stage once. None of them was lost, since each ended in a tool call, so the rules that turn thinking off
after a reply lost or salvaged from its reasoning (`settled_answer._thinking_is_off_here`) never reached them. When
thinking was off, the same stage made each read in about five seconds and then wrote. A read is the cheapest step;
minutes of deliberation over which file to open buy nothing.

So in any stage, the reply right after one whose reasoning reached `REASONING_TOKENS` and whose only calls were reads
goes without thinking, and thinking is back on for the reply after that - the one-reply shape of the rule for a reply
lost to reasoning. A reply that wrote or ran anything never turns it off. Each time it does, the run's transcript
records it (`RECORD_KIND`), which is what `loop.sh effects` reads as the switch having acted.
"""
from __future__ import annotations

import logging
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "LONG_REASONING_BEFORE_A_READ"
#: `LONG_REASONING_BEFORE_A_READ` set to on or off overrides this.
ON_BY_DEFAULT = False

#: Reasoning tokens in one reply from which a reply that only read counts as a long deliberation over a read. Two
#: thirds of the smallest reply cap a stage is given (`app.models.FIX_STAGE_REPLY_TOKENS`, 12,000), so a fix stage's
#: reply reasoned to its cap is reached; nearly twice a fix-stage specialist's whole reply at the 90th percentile
#: (4,425 tokens, `app.agents.reply_room`), so an ordinary reply is not. The smallest measured case was 12,000.
REASONING_TOKENS = 8_000

#: Characters of reasoning to a token, for a server that reports no reasoning tokens (as `run_kpis` estimates them).
CHARS_PER_TOKEN = 4

#: The tools that only read: a file, a listing, a search, a command's kept output, documentation.
_READ_FILE_TOOLS = frozenset({"read_file", "read_repository_file"})

#: The transcript record of one reply sent without thinking by this rule; the switch-firing check reads its `message`.
RECORD_KIND = "thinking_off_after_a_read"
SAID = "Thinking switched off for the reply after one that reasoned at length and then only read"


class _LongReasoningBeforeARead:
    """`LONG_REASONING_BEFORE_A_READ` as the switch registry reads one: off in code, the compose file turns it on."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("In any stage, the reply after one that reasoned 8,000 tokens or more and then only read (a file, a "
                   "listing, a search) goes without thinking; thinking is back on for the reply after. Measured on "
                   "local models: replies reasoned 12-33k tokens, 5-7 minutes each, to make one or two reads.")

    @staticmethod
    def enabled() -> bool:
        return is_on(NAME, ON_BY_DEFAULT)


long_reasoning_switch = _LongReasoningBeforeARead()


def _read_tools() -> frozenset[str]:
    from app.agents.repeated_queries import QUERY_TOOLS

    return QUERY_TOOLS | _READ_FILE_TOOLS


def reasoning_tokens(message: Any) -> int:
    """How many tokens `message` reasoned: as the server reported them, else estimated from the reasoning's length."""
    usage = getattr(message, "usage_metadata", None)
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("output_token_details")
    details = details if isinstance(details, dict) else {}
    reported = int(details.get("reasoning") or 0)
    if reported > 0:
        return reported
    from app.models import REASONING_CHARS

    estimated = int((getattr(message, "response_metadata", None) or {}).get(REASONING_CHARS) or 0) // CHARS_PER_TOKEN
    output = int(usage.get("output_tokens") or 0)
    return min(estimated, output) if output > 0 else estimated


def _called(message: Any) -> list[str]:
    calls = [*(getattr(message, "tool_calls", None) or ()), *(getattr(message, "invalid_tool_calls", None) or ())]
    return [str((call or {}).get("name") or "") for call in calls]


def the_last_reply_deliberated_over_a_read(messages: list[Any]) -> int:
    """The reasoning tokens of the last reply when, with the switch on, it reasoned at length and only read; else 0."""
    try:
        if not long_reasoning_switch.enabled():
            return 0
        last = next((m for m in reversed(messages) if getattr(m, "type", None) == "ai"), None)
        names = _called(last) if last is not None else []
        if not names or not set(names) <= _read_tools():
            return 0
        tokens = reasoning_tokens(last)
        return tokens if tokens >= REASONING_TOKENS else 0
    except Exception:  # noqa: BLE001 - then thinking is decided as before
        return 0


def note(messages: list[Any], stage: str) -> None:
    """Record that this call goes without thinking for the last reply's deliberation over a read. Never raises."""
    try:
        from app.models.model_pin import current_run_id
        from app.observability.transcript import record

        tokens = the_last_reply_deliberated_over_a_read(messages)
        run = current_run_id()
        if not tokens or not run:
            return
        last = next(m for m in reversed(messages) if getattr(m, "type", None) == "ai")
        tools = _called(last)
        record(run, stage, RECORD_KIND, switch=NAME, reasoning_tokens=tokens, tools=tools,
               message=f"{SAID}: {tokens:,} reasoning tokens before {', '.join(tools)}")
    except Exception:  # noqa: BLE001 - a record never fails a call
        logger.debug("Could not record the thinking switched off after a read", exc_info=True)


#: How many replies in one stage may deliberate at length over a read before thinking stays off for the rest of it.
TIMES_BEFORE_IT_STAYS_OFF = 2


def stays_off_in(stage: str) -> bool:
    """With the switch on, whether this stage has already turned thinking off `TIMES_BEFORE_IT_STAYS_OFF` times, so it
    stays off. Never raises.

    Measured on one run: a test round's replies reasoned 35,000 tokens (six minutes) before a read twice, thinking
    coming back on after each - the one-reply shape left the next deliberation free. As for replies lost to reasoning
    (`settled_answer.LOST_REPLIES_BEFORE_THINKING_STAYS_OFF`), a second time keeps it off; the transcript holds the
    count, so a restart or a compaction keeps it.
    """
    try:
        if not stage or not long_reasoning_switch.enabled():
            return False
        from app.observability.transcript import _run_id_from_config, read_transcript

        run = _run_id_from_config()
        if not run:
            return False
        times = sum(1 for entry in read_transcript(run, {RECORD_KIND}) if entry.get("stage") == stage)
        return times >= TIMES_BEFORE_IT_STAYS_OFF
    except Exception:  # noqa: BLE001 - then thinking is decided as before
        return False


__all__ = ["NAME", "TIMES_BEFORE_IT_STAYS_OFF", "stays_off_in", "ON_BY_DEFAULT", "REASONING_TOKENS", "RECORD_KIND", "SAID", "long_reasoning_switch", "note",
           "reasoning_tokens", "the_last_reply_deliberated_over_a_read"]
