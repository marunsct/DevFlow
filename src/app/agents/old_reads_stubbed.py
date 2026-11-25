"""Fix stages keep old reads as one-line notes instead of being summarised by a model (LF.1420, plan FX.4).

Behind `FIX_STAGES_STUB_OLD_READS`, off until measured.

Measured on one medium run's three failing fixers: 91 reads, 63 of them reads again of a file that had not changed.
Each was summarised twice, and a summary did not free room - the request before the first was 41,578 tokens, the
first after it 42,243, because the opening is carried whole and the kept tail was the last three reads - while it
kept descriptions of the files instead of the fixer's findings, lost a 12,000-token analysis and added a false lead
("add passlib") that the next steps followed. Published work on agent harnesses ("The Complexity Trap", 2025) found
that replacing old tool outputs with a placeholder matched a model summary's solve rate at half the cost.

With the switch on, in a `defect_fix_*` stage:

- a read whose lines a later read shows again, unchanged, becomes one line: "read `path` lines a-b, unchanged" -
  nothing is lost, the later read has the text;
- at the trigger, every read before the kept tail becomes such a line, saying whether the file still holds those
  lines (compared with the file on disk) - in steps of `observation_folding.FOLD_STEP` messages, so the request's
  opening stays the same, and cached, between steps;
- the fixer's own words, its carried reasoning, command results and refusals stay as they are; only reads are
  shortened, and the model summary runs only when the request is still past the trigger after that;
- the trigger is computed from the fix stage's own reply cap (`app.models.FIX_STAGE_REPLY_TOKENS`, when that cap is
  in force) rather than the 32,000 tokens every stage holds back for a reply.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "FIX_STAGES_STUB_OLD_READS"
#: `FIX_STAGES_STUB_OLD_READS` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The stages this concerns.
FIXING_STAGES = ("defect_fix_",)
#: What the admin page says this switch does.
explanation = ("A fix stage keeps an earlier read of a file as one line ('read path lines a-b, unchanged') instead of "
               "having its conversation summarised by a model; its own words, command results and refusals stay. Its "
               "summary trigger follows its own 12,000-token reply cap.")
#: What the harness records once per stage visit it shortens reads in; the switch-firing check reads it.
SAID = "A fix stage's earlier reads kept as one-line notes"
RECORD_KIND = "old_reads_stubbed"
#: How a shortened read says so; also how one already shortened is known.
TAKEN_OUT = "taken out by the harness"
_READS = frozenset({"read_file", "read_repository_file"})
#: A row as the read tool numbers it: the line number (a long line's continuation `12.1`), two spaces, the text.
_ROW = re.compile(r"^ *(\d+)(?:\.(\d+))?  (.*)$")
_SLOT = "old reads stubbed"


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def _stage() -> str:
    try:
        from app.observability.transcript import _stage_from_config

        return str(_stage_from_config("") or "")
    except Exception:  # noqa: BLE001
        return ""


def applies_here() -> bool:
    """Whether the running stage is a fix stage with the switch on."""
    return enabled() and _stage().startswith(FIXING_STAGES)


def fix_stage_trigger(input_ceiling: int, reserved: int, soft_ratio: float, ceiling_is_set: bool) -> int | None:
    """The tokens a fix stage's conversation may reach before it is shortened, from its own reply cap rather than the
    `reserved` tokens every stage holds back; None when the ceiling was set by hand or the cap leaves no more room.

    `input_ceiling` is the window less `reserved` for the reply; the fix stage's ceiling gives back what its smaller cap
    does not use. On a 91,776-token window holding back 32,000: 53,775 becomes 73,775, the trigger 43,020 becomes
    59,020 at the usual 0.8."""
    from app.models import FIX_STAGE_REPLY_TOKENS

    if ceiling_is_set or reserved <= FIX_STAGE_REPLY_TOKENS or input_ceiling <= 0:
        return None
    ceiling = input_ceiling + reserved - FIX_STAGE_REPLY_TOKENS
    from app.agents import summarise_later

    return summarise_later.trigger_tokens(int(ceiling * soft_ratio), ceiling)


def trigger_here(usual: int | None, fix_trigger: int | None) -> int | None:
    """The trigger for the running call: `fix_trigger` in a fix stage with the switch on and its reply cap in force,
    when it is later than `usual`; else `usual`."""
    if not fix_trigger or not usual or fix_trigger <= usual or not applies_here():
        return usual
    try:
        from app.models import fix_stage_reply_cap

        if fix_stage_reply_cap(None) is None:
            return usual  # its replies are not capped: they need the room every stage keeps
    except Exception:  # noqa: BLE001
        return usual
    return fix_trigger


def _text(content: Any) -> str | None:
    return content if isinstance(content, str) else None


def rows_of(text: str) -> dict[int, str]:
    """The file's lines a read's result shows, by number, a long line's continuations joined; {} when it numbers none."""
    rows: dict[int, str] = {}
    for line in str(text or "").split("\n"):
        found = _ROW.match(line)
        if not found:
            continue
        number = int(found.group(1))
        if found.group(2) is not None:
            if number in rows:
                rows[number] += found.group(3)
            continue
        rows[number] = found.group(3)
    return rows


def _span(rows: dict[int, str]) -> str:
    first, last = min(rows), max(rows)
    return f"{first}-{last}" if first != last else str(first)


def _reads(messages: list[Any]) -> list[tuple[int, str, dict[int, str]]]:
    """(index, path, rows) of each read result in `messages` that numbers lines, in order."""
    paths: dict[str, str] = {}
    for message in messages:
        if getattr(message, "type", None) == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                if call.get("name") in _READS:
                    args = call.get("args") or {}
                    path = str(args.get("file_path") or args.get("path") or args.get("relative_path") or "")
                    paths[str(call.get("id") or "")] = path.strip().lstrip("/")
    found = []
    for index, message in enumerate(messages):
        if getattr(message, "type", None) != "tool":
            continue
        path = paths.get(str(getattr(message, "tool_call_id", "") or ""))
        text = _text(getattr(message, "content", None))
        if not path or text is None or TAKEN_OUT in text:
            continue
        rows = rows_of(text)
        if rows:
            found.append((index, path, rows))
    return found


def _on_disk(repo_root: str | Path | None, path: str) -> list[str] | None:
    if not repo_root:
        return None
    try:
        return (Path(repo_root) / path).read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _still_there(rows: dict[int, str], lines: list[str] | None) -> bool | None:
    if lines is None:
        return None
    return all(0 < number <= len(lines) and lines[number - 1] == text for number, text in rows.items())


def _note(path: str, rows: dict[int, str], unchanged: bool | None, *, shown_later: bool = False) -> str:
    where = f"read `{path}` lines {_span(rows)}"
    if shown_later:
        return f"[{where}, unchanged; a later read below shows the same lines. Its text was {TAKEN_OUT} here.]"
    if unchanged:
        return (f"[{where}, unchanged since. Its text was {TAKEN_OUT} to keep this conversation small; read those "
                "lines again only if you need them word for word.]")
    if unchanged is False:
        return (f"[{where}; the file has changed since, so its text was {TAKEN_OUT}. Read the lines you need as "
                "they are now.]")
    return f"[{where}. Its text was {TAKEN_OUT} to keep this conversation small; read it again if you need it.]"


def _with(message: Any, content: str) -> Any:
    try:
        return message.model_copy(update={"content": content})
    except Exception:  # noqa: BLE001 - kept whole
        return message


def stubbed(messages: list[Any], repo_root: str | Path | None = None, before: int = 0) -> tuple[list[Any], int, int]:
    """`messages` with each read a later read shows again unchanged made a one-line note, and - when `before` is past
    0 - every read before index `before` too; with how many of each. Never raises: `messages` as they were."""
    try:
        reads = _reads(messages)
        out = list(messages)
        repeated = masked = 0
        for at, (index, path, rows) in enumerate(reads):
            later = [r for i, p, r in reads[at + 1:] if p == path]
            if any(all(r.get(number) == text for number, text in rows.items()) for r in later):
                out[index] = _with(out[index], _note(path, rows, True, shown_later=True))
                repeated += 1
            elif index < before:
                out[index] = _with(out[index], _note(path, rows, _still_there(rows, _on_disk(repo_root, path))))
                masked += 1
        return out, repeated, masked
    except Exception:  # noqa: BLE001 - the conversation as it was
        logger.debug("Could not shorten a fix stage's old reads", exc_info=True)
        return messages, 0, 0


def note(repeated: int, masked: int) -> None:
    """Once per stage visit, record that reads were shortened; and when more reads were taken out at the trigger than
    before, forget what the read guard counted as given, so a read of them again is not called a repeat. Never raises."""
    try:
        from app.agents import stage_memory

        slot = stage_memory.store(_SLOT, {})
        if masked > int(slot.get("masked") or 0):
            from app.agents.workspace_backend import WHAT_THE_CONVERSATION_WAS_GIVEN

            stage_memory.forget(*WHAT_THE_CONVERSATION_WAS_GIVEN)
            slot["masked"] = masked
        if (repeated or masked) and not slot.get("recorded"):
            slot["recorded"] = True
            from app.observability.transcript import _run_id_from_config, record

            run = _run_id_from_config()
            if run:
                record(run, _stage(), RECORD_KIND, message=f"{SAID}: {repeated} read again later, {masked} older "
                       "than the kept tail")
    except Exception:  # noqa: BLE001 - a record never fails a call
        logger.debug("Could not record shortened reads", exc_info=True)


__all__ = ["NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "TAKEN_OUT", "applies_here", "enabled", "explanation",
           "fix_stage_trigger", "note", "rows_of", "stubbed", "trigger_here"]
