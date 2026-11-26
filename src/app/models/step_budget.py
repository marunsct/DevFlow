"""A smaller reasoning budget for the steps of a working stage's agent loop (LF.1593; behind `STEP_SIZED_REASONING_BUDGET`).

Measured live on one model with `REASONING_BUDGET` on (a budget of 20,000 tokens of a 32,000-token cap): an
acceptance-suite author's replies of 17,427, 20,076, 20,078, 18,626, 17,636 and 20,755 output tokens, four to five
minutes each, each ending in one small call (`ls .venv`, `cat requirements-dev.txt`). The budget was sized for a
stage's answer, and the model spent all of it on every step of the loop.

What a step needs was measured over every captured transcript, on models whose replies were not cut at a budget or
held to one: 55,056 replies that followed tool results in a stage offering a tool that writes or runs, with a reply
not cut at its cap, reasoned a median of 220 tokens, 2,290 at the 90th percentile, 5,467 at the 95th and 15,640 at the
99th; 96.8% within 8,000 (writes 96.2%, commands 97.2%, the stage's answer given from a step 99.4%). The model the
live case was measured on: 89.5% of its 38 such steps within 8,000. Of all the reasoning those steps spent, 23% was
past 8,000 tokens. A stage offering only reads and its answer is a review: its steps are its thinking (median 1,783,
90th percentile 12,887, 79% within 8,000), so it keeps the stage's budget.

So, with the switch on, on a server the diagnosis measured to enforce a budget (`reasoning_budget`), a call of a
working stage (one offered a tool that changes a file or runs a command) whose conversation already holds tool
results is sent `STEP_BUDGET` - never more than the stage's own budget. The stage's first call, any call where only
the answer is allowed (`named_answer`), and every call of a stage that only reads keep the stage's budget. A step
whose reply was cut at its budget and did nothing but read (or called nothing) raises the next step's budget,
doubling it, at most `MOST_RAISES` times and never past the stage's budget; a reply that acted, or was not cut,
brings the next step back to `STEP_BUDGET`. Each budget a stage is sent leaves one transcript record when it changes
(`RECORD_KIND`, the firing signal), and `loop.sh effects` reads each stage kind's step replies, tokens and budget hits.

Off in code until measured (owner's rule for efficiency changes): a step held to less reasoning may act worse.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Iterable

logger = logging.getLogger(__name__)

NAME = "STEP_SIZED_REASONING_BUDGET"
#: A working stage's step budget: 96.8% of 55,056 measured steps reasoned within it (module docstring).
STEP_BUDGET = 8_000
#: How many times a step cut at its budget with nothing done raises the next one (8,000, 16,000, then the stage's).
MOST_RAISES = 2
#: A reply counts as cut at its budget when its reasoning reached this share of it: reasoning is estimated from its
#: characters (4 to a token) where the server reports no reasoning tokens, and one model writes 3.6 to a token.
CUT_SHARE = 0.8
#: The transcript record of a step budget sent, when it changes for a stage, and its words (the firing signal).
RECORD_KIND = "step_reasoning_budget"
SAID = "reasoning held to a step budget of"

#: Characters of reasoning to a token, for a transcript record with no reasoning tokens reported.
_CHARS_PER_TOKEN = 4
#: The tools that change a file or run a command: a stage offered one works in its loop.
_ACTING_TOOLS = frozenset({"write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines",
                           "delete_artifact", "move_artifact", "run_terminal_command", "run_validation"})
_LAST_SENT: dict[tuple[str, str], int] = {}
_LOCK = threading.Lock()


class _StepSized:
    """`STEP_SIZED_REASONING_BUDGET` as the switch registry reads one: off in code, on in the compose file."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("Where a reasoning budget is enforced, a call of a stage that writes or runs, once its "
                   "conversation holds tool results, is sent a reasoning budget of 8,000 tokens instead of the stage's; "
                   "the first call, answer calls and stages that only read keep the stage's budget. A step cut at its "
                   "budget that did nothing but read doubles the next one's, twice at most. Measured: replies of "
                   "17,000-20,000 tokens (4-5 minutes) before one listing each; 96.8% of 55,056 steps needed under "
                   "8,000.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on(NAME, _StepSized.ON_BY_DEFAULT)


step_sized_switch = _StepSized()


def _read_tools() -> frozenset[str]:
    from app.agents.repeated_queries import QUERY_TOOLS

    return QUERY_TOOLS | {"read_file", "read_repository_file"}


def _type(message: Any) -> str:
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "")
        return {"assistant": "ai", "user": "human"}.get(role, role)
    return str(getattr(message, "type", "") or "")


def _calls(message: Any) -> list[str]:
    calls = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
    names = []
    for call in calls or ():
        call = call if isinstance(call, dict) else {}
        names.append(str(call.get("name") or (call.get("function") or {}).get("name") or ""))
    return [name for name in names if name]


def _was_cut(message: Any, budget: int) -> bool:
    """Whether `message`'s reasoning was ended at `budget`: the server's words for an ended reasoning at its end, or
    reasoning of at least `CUT_SHARE` of the budget."""
    from app.agents.deliberated_reads import reasoning_tokens
    from app.models import REASONING_FIELD
    from app.models.reply_salvage import ENOUGH

    kept = (getattr(message, "additional_kwargs", None) or {}).get(REASONING_FIELD)
    if isinstance(kept, str) and ENOUGH in kept[-2 * len(ENOUGH):]:
        return True
    return reasoning_tokens(message) >= CUT_SHARE * budget


def _acted(message: Any) -> bool:
    """Whether `message` called anything but a read: a write, a command, its answer."""
    return any(name not in _read_tools() for name in _calls(message))


def budget_for_the_step(base: int, messages: Iterable[Any]) -> int:
    """The reasoning budget of the next step of a loop whose conversation is `messages`, the stage's budget `base`.

    `STEP_BUDGET`, doubled for each reply in a row, from the last, that was cut at its budget and did nothing but
    read, at most `MOST_RAISES` times, never past `base`."""
    raises = 0
    seen_a_result = False
    for message in messages or ():
        kind = _type(message)
        if kind == "tool":
            seen_a_result = True
            continue
        if kind != "ai" or not seen_a_result:
            continue
        sent = min(int(base), STEP_BUDGET * 2 ** raises)
        if _was_cut(message, sent) and not _acted(message):
            raises = min(raises + 1, MOST_RAISES)
        else:
            raises = 0
    return min(int(base), STEP_BUDGET * 2 ** raises)


def _is_a_working_step(payload: dict, messages: list[Any]) -> bool:
    offered = {str((tool.get("function") or {}).get("name") or tool.get("name") or "")
               for tool in payload.get("tools") or () if isinstance(tool, dict)}
    if not offered & _ACTING_TOOLS:
        return False
    from app.models.named_answer import asked_for

    if asked_for() or isinstance(payload.get("tool_choice"), dict):
        return False
    held = messages or payload.get("messages") or []
    return any(_type(message) == "tool" for message in held)


def sized_to_the_step(payload: dict, base: int, messages: list[Any] | None = None) -> int:
    """The reasoning budget for `payload`, whose stage's budget is `base`: a step's where the switch is on and the call
    is a step of a working stage (`messages` its conversation, else the payload's), else `base`. Never raises."""
    try:
        if not step_sized_switch.enabled() or not _is_a_working_step(payload, list(messages or [])):
            return base
        budget = budget_for_the_step(base, list(messages or payload.get("messages") or []))
        _note(budget, base)
        return budget
    except Exception:  # noqa: BLE001 - the stage's budget
        logger.debug("Could not size the reasoning budget to the step", exc_info=True)
        return base


def _note(budget: int, base: int) -> None:
    """One transcript record each time a stage's step budget changes. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config, record

        run, stage = _run_id_from_config(), _stage_from_config("")
        if not run:
            return
        with _LOCK:
            if _LAST_SENT.get((str(run), str(stage))) == budget:
                return
            _LAST_SENT[(str(run), str(stage))] = budget
        raised = "" if budget <= STEP_BUDGET else ", raised after replies cut at their budget that only read"
        record(run, stage, RECORD_KIND, switch=NAME, budget=budget, stage_budget=base,
               message=f"{SAID} {budget:,} tokens of the stage's {base:,}{raised}")
    except Exception:  # noqa: BLE001
        logger.debug("Could not record the step budget", exc_info=True)


_BUDGET_WORDS = re.compile(r"budget of ([\d,]+) tokens")


def _record_budget(record: dict) -> int:
    if isinstance(record.get("budget"), int):
        return int(record["budget"])
    found = _BUDGET_WORDS.search(str(record.get("message") or ""))
    return int(found.group(1).replace(",", "")) if found else 0


def _reasoned(record: dict) -> int:
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    details = usage.get("output_token_details") if isinstance(usage.get("output_token_details"), dict) else {}
    if int(details.get("reasoning") or 0) > 0:
        return int(details["reasoning"])
    estimated = int(record.get("reasoning_chars") or 0) // _CHARS_PER_TOKEN
    output = int(usage.get("output_tokens") or 0)
    return min(estimated, output) if output > 0 else estimated


def _stage_kind(stage: str) -> str:
    return re.sub(r"(_\d+)+$", "", str(stage or "")) or "(no stage)"


def effects_lines(records: Any) -> list[str]:
    """`loop.sh effects` (LF.1593): whether the switch was on in the run, and per stage kind the replies that followed
    tool results (steps), their reasoning and output tokens, and how many reached the budget they were sent - the
    numbers a run with the switch on is read against one with it off."""
    records = [record for record in records or () if isinstance(record, dict)]
    on = any(record.get("kind") == "provenance" and NAME in str(record.get("switches_on") or "") for record in records)
    last: dict[str, str] = {}
    step_call: dict[str, bool] = {}
    budgets: dict[str, int] = {}
    stats: dict[str, list[int]] = {}
    for record in records:
        kind, stage = record.get("kind"), str(record.get("stage") or "")
        if kind in ("reasoning_budget", RECORD_KIND):
            if _record_budget(record):
                budgets[stage] = _record_budget(record)
        elif kind == "tool_result":
            last[stage] = "tool_result"
        elif kind == "model_request":
            step_call[stage] = last.get(stage) == "tool_result" and str(record.get("tools") or "[]") != "[]"
            last[stage] = "model_request"
        elif kind == "model_response":
            if step_call.pop(stage, False):
                usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
                reasoned, budget = _reasoned(record), budgets.get(stage, 0)
                row = stats.setdefault(_stage_kind(stage), [0, 0, 0, 0])
                row[0] += 1
                row[1] += reasoned
                row[2] += int(usage.get("output_tokens") or 0)
                row[3] += int(bool(budget) and reasoned >= CUT_SHARE * budget)
            last[stage] = "model_response"
    head = f"LF.1593 step replies by stage kind, {NAME} {'on' if on else 'off'} in this run"
    if not stats:
        return [f"     -  {head}: not reached"]
    sent = sum(1 for record in records if record.get("kind") == RECORD_KIND)
    lines = [f"  {sum(row[0] for row in stats.values()):>4}  {head} (step budgets sent: {sent}; "
             "replies, reasoning tokens, output tokens, at their budget):"]
    for stage, row in sorted(stats.items(), key=lambda item: -item[1][1]):
        lines.append(f"          {stage}: {row[0]} replies, {row[1]:,} reasoning, {row[2]:,} output, "
                     f"{row[3]} at their budget")
    return lines


__all__ = ["CUT_SHARE", "MOST_RAISES", "NAME", "RECORD_KIND", "SAID", "STEP_BUDGET", "budget_for_the_step",
           "effects_lines", "sized_to_the_step", "step_sized_switch"]
