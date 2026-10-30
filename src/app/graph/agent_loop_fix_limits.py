"""An agent-loop fix stage ends at its call cap for good, and a repeated action changes what the model reads next (behind `AGENT_LOOP_FIX_LIMITS`).

Measured over ten runs: agent-loop fix stages took 26% of the run's time; the median productive fix was 12 calls and
the costliest were loops of 36-40 calls that ended in a surrender. `FIX_STAGE_CALL_CAP` already stops a fix stage at
16 model calls, but a stage stopped there with no answer is restarted on a fresh conversation (two restarts), and
each restart is a new 16: measured per stage name, one defect's fix cost up to 48 calls. And the guards that watch
for a repeat either block the call (`settled_answer`'s refusals and withheld tools) or wait for the same answer to
come back; a model refused a call reads the refusal and sends the next call that is nearly the same.

With the switch on:

- A defect-fix stage stopped at its call cap with no answer is not restarted (`ends_for_good`): the stage's
  last words become its blocker, like a stage whose retries are spent, and the workflow's surrender path takes the
  defect (`surrender_to_rewrite`).
- The same action - the same tool with the same arguments once whitespace and a leading `./` are set aside - sent
  `SAME_ACTION_BEFORE_SAYING_SO` times with no change to a file in between is a loop whatever the budget says
  (`repeat_notice`). The model's next input says what it has already done, how often, and that it gave nothing the
  conversation did not already hold, and asks for a different action or the answer. A call is not only refused:
  the model's next input is different.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.switches import is_on

#: `AGENT_LOOP_FIX_LIMITS` set to on or off overrides this.
ON_BY_DEFAULT = False

#: The same action this many times, with no write between, is a loop.
SAME_ACTION_BEFORE_SAYING_SO = 3
#: Distinct actions the notice lists, and the characters it spends on each.
MOST_ACTIONS_LISTED = 6
ACTION_CHARACTERS = 110

#: The tools whose success is a change to a file: a repeat after one is not a repeat, the files are different now.
_WRITING_TOOLS = frozenset({"write_artifact", "edit_artifact", "replace_lines", "delete_artifact", "move_artifact"})


def enabled() -> bool:
    return is_on("AGENT_LOOP_FIX_LIMITS", ON_BY_DEFAULT)


def is_a_fix_stage(stage_name: str) -> bool:
    return str(stage_name or "").startswith("defect_fix_")


def ends_for_good(stage_name: str, result: Any) -> bool:
    """Whether a stage that returned no answer is not restarted: a fix stage that ran out of model calls."""
    if not enabled() or not is_a_fix_stage(stage_name):
        return False
    from app.agents.settled_answer import was_stopped_by_the_budget

    return bool(was_stopped_by_the_budget(result))


def _plain(value: Any) -> Any:
    """`value` with whitespace collapsed and a leading `./` dropped from every string in it."""
    if isinstance(value, str):
        return re.sub(r"^(?:\./)+", "", " ".join(value.split()))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def action_key(call: Any) -> tuple[str, str]:
    """(tool, arguments) of a tool call as one action: two spellings of the same call are the same key."""
    call = call or {}
    return str(call.get("name") or ""), json.dumps(_plain(call.get("args") or {}), sort_keys=True, default=str)


def _already_done(messages: list[Any]) -> tuple[dict[tuple[str, str], int], tuple[str, str] | None]:
    """How often each action was sent since a file last changed, and the last action sent (None when none was)."""
    counts: dict[tuple[str, str], int] = {}
    last: tuple[str, str] | None = None
    for message in messages:
        for call in getattr(message, "tool_calls", None) or ():
            key = action_key(call)
            if not key[0]:
                continue
            if key[0] in _WRITING_TOOLS:
                counts, last = {}, None
                continue
            counts[key] = counts.get(key, 0) + 1
            last = key
    return counts, last


def _described(key: tuple[str, str]) -> str:
    arguments = key[1] if len(key[1]) <= ACTION_CHARACTERS else key[1][:ACTION_CHARACTERS] + "..."
    return f"`{key[0]}` {arguments}"


def repeat_notice(messages: list[Any], stage_name: str) -> str:
    """What the model is told when the action it just sent is one it already sent; "" when it is not (or the switch is off).

    Fires on each further repeat: the notice is appended to the model's input for the one call, not written into
    the conversation, so a model that goes on repeating reads it again with the count one higher.
    """
    if not enabled() or not is_a_fix_stage(stage_name):
        return ""
    counts, last = _already_done(messages)
    if last is None or counts[last] < SAME_ACTION_BEFORE_SAYING_SO:
        return ""
    tried = sorted(counts.items(), key=lambda item: -item[1])[:MOST_ACTIONS_LISTED]
    done = "\n".join(f"- {_described(key)}: {count} time(s)" for key, count in tried)
    return (
        f"You have now sent {_described(last)} {counts[last]} times, and no file has changed since the first. "
        "It gave nothing the conversation above does not already hold, so sending it again cannot move this fix "
        "forward.\n"
        f"What you have already done since your last change:\n{done}\n"
        "Do something you have not done: change a file from what you have read, run a different check, look at a "
        "different place, or return your structured response saying what stops you."
    )


__all__ = ["ON_BY_DEFAULT", "action_key", "ends_for_good", "enabled", "is_a_fix_stage", "repeat_notice"]
