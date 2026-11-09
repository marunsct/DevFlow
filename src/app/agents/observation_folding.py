"""Old tool results folded to their opening lines once a conversation is large (behind `OBSERVATION_FOLDING`).

A stage's history grows by every result it is handed: each file read, search
and command output stays whole in every later request until the summariser
runs at the compaction trigger. Arguments of old calls were already shortened
behind the kept tail (`compaction.RequestKeepingSummarization._truncate_args`);
their results never were, and on a large codebase they are most of what a
stage carries - reads of files thousands of lines long, searches over
thousands of files. SWE-agent folds observations older than its last few turns
into a line each, and measured a higher solve rate for it than with the whole
history; OpenHands' condenser does the same before each call.

So behind the same kept tail, a result longer than `MOST_KEPT_CHARACTERS` is
cut to its opening `OPENING_KEPT_CHARACTERS` and a line saying what was folded.
It is decided by size, so a small stage is untouched: nothing folds before the
argument-shortening trigger, half the window, is reached.

Folding edits the history, and the model server reuses its cache only for an
unchanged opening of the request. The boundary therefore moves in steps of
`FOLD_STEP` messages, not one message a call: the folded part is identical for
that many calls and the cache holds across them.
"""

from __future__ import annotations

from typing import Any

from app.switches import is_on

#: `OBSERVATION_FOLDING` set to on or off overrides this.
ON_BY_DEFAULT = False
#: A result at most this long is kept whole however old it is.
MOST_KEPT_CHARACTERS = 1_200
#: What a folded result keeps of its opening: a command's exit code and first
#: lines, a read's path and first lines, a search's first matches.
OPENING_KEPT_CHARACTERS = 300
#: Messages the folded part grows by at a time, so the request's opening stays
#: the same - and cached - between steps.
FOLD_STEP = 10
#: How a folded result says so; also how one already folded is known.
FOLDED = "[Folded by the harness to keep this conversation small"


def enabled() -> bool:
    return is_on("OBSERVATION_FOLDING", ON_BY_DEFAULT)


def boundary(cutoff: int) -> int:
    """`cutoff` moved back to the last whole `FOLD_STEP`: what is before it is handled the same way for that many calls."""
    return max(0, cutoff - cutoff % FOLD_STEP)


def _text(content: Any) -> str | None:
    return content if isinstance(content, str) else None


def folded_result(name: str, text: str) -> str:
    """`text` cut to its opening, with a line saying how much was left out and how to have it again."""
    lines = text.count("\n") + 1
    return (
        text[:OPENING_KEPT_CHARACTERS].rstrip()
        + f"\n{FOLDED}: this result of `{name or 'a tool'}` was {len(text):,} characters and {lines:,} lines; "
        "the rest was left out because it is older than the latest steps. Run the same call again if you "
        "need what it said.]"
    )


def fold(messages: list[Any], before: int) -> tuple[list[Any], int]:
    """`messages` with each long tool result before index `before` folded, and how many were. Never raises."""
    out: list[Any] = []
    count = 0
    for index, message in enumerate(messages):
        text = _text(getattr(message, "content", None))
        if (
            index < before
            and getattr(message, "type", None) == "tool"
            and text is not None
            and len(text) > MOST_KEPT_CHARACTERS
            and FOLDED not in text
        ):
            try:
                message = message.model_copy(update={"content": folded_result(getattr(message, "name", "") or "", text)})
                count += 1
            except Exception:  # noqa: BLE001 - kept whole
                pass
        out.append(message)
    return out, count


def a_read_was_folded(count: int) -> None:
    """Forget what the stage was handed when the folded part has grown, so a read again is not called a repeat.

    The repeat notices (`workspace_backend`) say "this returned nothing you did
    not already have" about a file read twice; after a fold the conversation no
    longer has it, which is the compaction's case (`compaction`) too.
    """
    try:
        from app.agents import stage_memory
        from app.agents.workspace_backend import WHAT_THE_CONVERSATION_WAS_GIVEN

        slot = stage_memory.store("observation_folding", {})
        if count > int(slot.get("folded") or 0):
            stage_memory.forget(*WHAT_THE_CONVERSATION_WAS_GIVEN)
            slot["folded"] = count
    except Exception:  # noqa: BLE001 - the notices stay as they were
        pass


__all__ = ["FOLDED", "FOLD_STEP", "MOST_KEPT_CHARACTERS", "ON_BY_DEFAULT", "OPENING_KEPT_CHARACTERS", "a_read_was_folded",
           "boundary", "enabled", "fold", "folded_result"]
