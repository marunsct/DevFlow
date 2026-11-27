"""A change refused in another work order's file is the harness's hand-off to that file's owner (LF.1548).

Measured on a medium run in parallel mode: the database work order tried eleven times to edit a routes file the plan
gave to the backend work order, running beside it. Each `edit_artifact` was refused, the refusal asked the model to
put what it needed in `blockers`, from the fifth it added how often it had been refused, and the model reworded its
edit every time: 97 calls, 31% of them failing. The refusal did not take the change anywhere, so sending it again was
the only way the model had to get it made.

So the harness does what the refusal asked of the model, at the first refusal, in parallel and linear modes alike:

1. `record` keeps the refused change - the file, its owner, and what was attempted (the `find`/`replace` or the start
   of the content, cut short) - in `.harness/foreign-file-handoffs.json`, and counts the refusals of that file to that
   stage. The second refusal is one short line, and from then on the stage's writes to that path are withheld for
   the rest of the stage (`repository._another_work_order_s_file`, `settled_answer.withhold_writes_to`).
2. `with_them` adds the stage's recorded changes to its `blockers` when it hands over, where the milestone review and
   the work-order ledger read a blocker the model reported.
3. The owner gets it as soon as possible: `build_middleware` hands it to the owner's next model call when the owner is
   running (parallel mode) or starts later (linear mode); `to_their_owners`, when every builder has finished and
   before CI, sends the ones no running owner received to the owner's next visit (once an attempt, by the same
   `unfinished_orders` note LF.1299 and LF.1310 use).

The recording and both deliveries are in the defect ledger (`loop.sh effects`). The record is cleared with every new
milestone plan, whose stage names repeat. Nothing here names a language, a framework or a kind of product.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: Where the recorded changes are kept, by the stage refused, then the file.
RECORD_FILE = ".harness/foreign-file-handoffs.json"
#: How much of the attempted change is kept, and how much the short refusal repeats.
MOST_CHANGE_CHARS = 300
MOST_SHOWN_CHARS = 160

#: The ledger events (`loop.sh effects`).
RECORDED_EVENT = "foreign file change recorded for its owner"
DELIVERED_EVENT = "foreign file change delivered to its running owner"
SENT_EVENT = "foreign file change sent to its owner's next visit"

#: How a recorded entry was delivered.
RUNNING = "running"
NEXT_VISIT = "next visit"

#: The `builders_sent_back` entry: the undelivered changes have gone to their owners this attempt.
SENT_TO_OWNERS = "foreign file changes"

#: What each refusal says, so the effects report can count them.
REFUSED_MARK = "belongs to another work order in this milestone"
SHORT_MARK = "Do not send it again; finish your own files."
WITHHELD_MARK = "are withheld for the rest of this stage and were not run"

#: How a refused change that is the whole file begins: a later one replaces what was recorded (`record`).
WHOLE_FILE = "the file written as "

_LOCK = threading.Lock()


def cut_short(text: str, most: int = MOST_CHANGE_CHARS) -> str:
    """`text` on one line, at most `most` characters."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= most else flat[: most - 3].rstrip() + "..."


def _read(root: str | Path) -> dict[str, dict[str, dict[str, Any]]]:
    try:
        table = json.loads((Path(root) / RECORD_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return table if isinstance(table, dict) else {}


def _write(root: str | Path, table: dict) -> None:
    file = Path(root) / RECORD_FILE
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")


def record(root: str | Path, stage: str, path: str, owner: str, change: str) -> int:
    """Keep one refused change for `owner` as `stage`'s blocker; how many times `stage` has now been refused `path`.

    A repeat counts the refusal and keeps what was first recorded, unless it is the whole file written again: that
    replaces whatever was recorded, and goes to the owner again if the earlier change already had (LF.1610). Measured
    on one builder: its first write was a file cut off mid-line by the reply's cap, its second the whole file, and the
    owner was handed the first while the second was answered "do not send it again". Never raises: a record that
    cannot be written reads as a first refusal, so the stage is told in full.
    """
    if not stage or not path or not owner:
        return 1
    try:
        with _LOCK:
            table = _read(root)
            entries = table.setdefault(stage, {})
            entry = entries.get(path)
            if entry is None:
                entries[path] = {"owner": owner, "change": cut_short(change), "refusals": 1, "delivered": ""}
                refusals = 1
            else:
                refusals = entry["refusals"] = int(entry.get("refusals") or 1) + 1
                if change.startswith(WHOLE_FILE) and cut_short(change) != entry.get("change"):
                    entry["change"], entry["delivered"] = cut_short(change), ""
            _write(root, table)
    except Exception:  # noqa: BLE001 - the refusal stands without its record
        logger.warning("Could not record a change refused in another work order's file", exc_info=True)
        return 1
    if refusals == 1:
        from app.observability import defect_ledger

        defect_ledger.note(RECORDED_EVENT, stage, detail=f"`{path}` for {owner}: {cut_short(change, 200)}")
    return refusals


def recorded(root: str | Path, stage: str) -> dict[str, dict[str, Any]]:
    """The changes recorded for `stage`, by file."""
    entries = _read(root).get(stage) if stage else None
    return dict(entries) if isinstance(entries, dict) else {}


def forget(root: str | Path) -> None:
    """Clear every record: a new milestone plan's stages start with none. Never raises."""
    try:
        with _LOCK:
            (Path(root) / RECORD_FILE).unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not clear the recorded foreign file changes", exc_info=True)


# -- what the refused stage is told ---------------------------------------------------------------------------------


def first_refusal(path: str, owner: str) -> str:
    """The refusal of a stage's first write to `path`, which `owner`'s work order lists."""
    return (
        f"'{path}' belongs to another work order in this milestone: the plan gave it to {owner}, which writes it. "
        f"The change you sent is recorded as this stage's blocker and goes to {owner} - at once while it runs, "
        "otherwise on its next visit before the tests run; the milestone review reads it too. Do not send it again "
        "in any wording. Change only the files your own work order lists, write your side against the interface "
        "the plan gives, and finish them. Nothing was written."
    )


def short_refusal(path: str, owner: str, change: str) -> str:
    """The one line a stage is given from its second refused write to `path`, quoting the change first recorded."""
    return (f"Recorded for {owner}: {cut_short(change, MOST_SHOWN_CHARS) or f'a change to {path}'}. {SHORT_MARK} "
            f"Further writes to '{path}' are withheld for the rest of this stage. Nothing was written.")


def withheld(path: str, owner: str) -> str:
    """What a write to a withheld path is answered with (`settled_answer`)."""
    return (f"Refusing: writes to '{path}' {WITHHELD_MARK}. What you need there is recorded for {owner}. "
            "Finish your own files and return your structured response.")


def as_blocker(path: str, owner: str, change: str) -> str:
    """One recorded change as a blocker line of the stage refused."""
    said = f": this work order needed {change}" if change else ""
    return f"`{path}` belongs to {owner}'s work order, recorded for it{said}"


def with_them(output: Any, root: str | Path, stage: str) -> Any:
    """`output` with `stage`'s recorded changes among its blockers; `output` as it was when there are none."""
    entries = recorded(root, stage)
    if not entries:
        return output
    try:
        have = list(getattr(output, "blockers", None) or [])
        added = [as_blocker(path, str(entry.get("owner") or ""), str(entry.get("change") or ""))
                 for path, entry in sorted(entries.items()) if isinstance(entry, dict)]
        added = [line for line in added if line not in have]
        if not added:
            return output
        return output.model_copy(update={"blockers": [*have, *added]})
    except Exception:  # noqa: BLE001 - its own output stands
        logger.debug("Could not add the recorded foreign file changes to %s's blockers", stage, exc_info=True)
        return output


# -- what the owner is told -----------------------------------------------------------------------------------------


HEADING = "What another work order needs from your files"
OPENING = ("Another work order of this milestone needed these changes in files your work order lists, and may not "
           "make them itself. Each is yours to judge against your work order:")
CLOSING = ("Make each change your work order's interfaces call for, in your own files, and check it as your work "
           "order says. Where a change is not what your work order promises, or is already made under another name, "
           "say so in your report and leave the code as it is.")


def the_note(lines: Iterable[str]) -> str:
    """The note an owner is given, one line per change."""
    return f"\n\n--- {HEADING} ---\n{OPENING}\n" + "\n".join(f"- {line}" for line in lines) + f"\n{CLOSING}"


def _line(path: str, refused_to: str, change: str) -> str:
    return f"`{path}`, for {refused_to}" + (f": {change}" if change else "")


def _taken_for(root: str | Path, owner: str, how: str) -> list[tuple[str, str, str]]:
    """The undelivered changes for `owner` as (stage refused, path, change), now marked delivered `how`."""
    taken: list[tuple[str, str, str]] = []
    with _LOCK:
        table = _read(root)
        for refused_to, entries in sorted(table.items()):
            if not isinstance(entries, dict):
                continue
            for path, entry in sorted(entries.items()):
                if isinstance(entry, dict) and entry.get("owner") == owner and not entry.get("delivered"):
                    entry["delivered"] = how
                    taken.append((refused_to, path, str(entry.get("change") or "")))
        if taken:
            _write(root, table)
    return taken


def to_the_running_owner(root: str | Path, owner: str) -> str:
    """The note for `owner`'s next model call with every change recorded for it and not yet delivered; "" if none.

    Never raises: what cannot be delivered now goes on the owner's next visit.
    """
    if not owner or not str(owner).startswith("specialist_") or not (Path(root) / RECORD_FILE).is_file():
        return ""
    try:
        taken = _taken_for(root, owner, RUNNING)
    except Exception:  # noqa: BLE001 - delivered on the next visit instead
        logger.debug("Could not hand %s its recorded changes", owner, exc_info=True)
        return ""
    if not taken:
        return ""
    from app.observability import defect_ledger

    for refused_to, path, _change in taken:
        defect_ledger.note(DELIVERED_EVENT, refused_to, detail=f"`{path}` to {owner}")
    logger.warning("Handed %s %d change(s) other work orders were refused in its files", owner, len(taken))
    return the_note(_line(path, refused_to, change) for refused_to, path, change in taken).lstrip("\n")


def build_middleware(repo_root: str | Path) -> Any:
    """The middleware that hands a running owner the changes other work orders were refused in its files.

    Before the model call, so the note is a message of the owner's own conversation from then on, read once.
    """
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.messages import HumanMessage

    from app.observability.transcript import _stage_from_config

    class ForeignFileHandoffMiddleware(AgentMiddleware):
        name = "ForeignFileHandoffMiddleware"

        def before_model(self, state: Any, runtime: Any = None) -> dict[str, Any] | None:
            try:
                note = to_the_running_owner(repo_root, _stage_from_config(""))
            except Exception:  # noqa: BLE001 - never fail the stage it serves
                return None
            return {"messages": [HumanMessage(content=note)]} if note else None

    return ForeignFileHandoffMiddleware()


def to_their_owners(state: Any) -> dict[str, Any] | None:
    """The fields that send every change no running owner received to its owner's next visit, once an attempt.

    None when there is none. Never raises: a change that cannot be sent stays the refused stage's blocker.
    """
    try:
        if SENT_TO_OWNERS in (state.get("builders_sent_back") or []):
            return None
        root = str(getattr(state.get("repository"), "root_path", "") or "")
        tasks = list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or [])
        if not root or not tasks or not (Path(root) / RECORD_FILE).is_file():
            return None
        from app.graph.workflow import _specialist_stage_name

        stages = {_specialist_stage_name(task, index) for index, task in enumerate(tasks)}
        owners = sorted({str(entry.get("owner") or "") for entries in _read(root).values() if isinstance(entries, dict)
                         for entry in entries.values() if isinstance(entry, dict) and not entry.get("delivered")})
        notes: dict[str, str] = {}
        from app.observability import defect_ledger

        for owner in owners:
            if owner not in stages:
                continue
            taken = _taken_for(root, owner, NEXT_VISIT)
            for refused_to, path, _change in taken:
                defect_ledger.note(SENT_EVENT, refused_to, sprint=state.get("current_sprint_index", 0),
                                   detail=f"`{path}` to {owner}")
            if taken:
                notes[owner] = the_note(_line(path, refused_to, change) for refused_to, path, change in taken)
        if not notes:
            return None
        logger.warning("Changes refused in other work orders' files go to %s", ", ".join(sorted(notes)))
        return {"unfinished_orders": notes,
                "builders_sent_back": [*(state.get("builders_sent_back") or []), SENT_TO_OWNERS]}
    except Exception:  # noqa: BLE001 - the build goes on as before
        logger.warning("Could not send the recorded foreign file changes to their owners", exc_info=True)
        return None


# -- `loop.sh effects` ----------------------------------------------------------------------------------------------


def effects_lines(records: list[dict]) -> list[str]:
    """LF.1548: foreign-file writes refused, changes recorded for their owners, and how they were delivered."""
    events: dict[str, int] = {}
    for r in records:
        if isinstance(r, dict) and r.get("event") in (RECORDED_EVENT, DELIVERED_EVENT, SENT_EVENT):
            events[r["event"]] = events.get(r["event"], 0) + 1
    refused = sum(
        1 for r in records
        if isinstance(r, dict) and r.get("kind") == "tool_result"
        and any(mark in f"{r.get('content') or ''} {r.get('raised') or ''}"
                for mark in (REFUSED_MARK, SHORT_MARK, WITHHELD_MARK))
    )
    if not (events or refused):
        return ["     -  LF.1548 a change refused in another work order's file handed to its owner: not reached"]
    return [f"  {refused:>4}  LF.1548 writes refused in another work order's file",
            f"  {events.get(RECORDED_EVENT, 0):>4}  LF.1548 hand-offs recorded for the file's owner",
            f"  {events.get(DELIVERED_EVENT, 0):>4}  LF.1548 hand-offs delivered to a running owner",
            f"  {events.get(SENT_EVENT, 0):>4}  LF.1548 hand-offs sent to the owner's next visit"]


__all__ = [
    "DELIVERED_EVENT", "HEADING", "MOST_CHANGE_CHARS", "NEXT_VISIT", "RECORDED_EVENT", "RECORD_FILE", "REFUSED_MARK",
    "RUNNING", "SENT_EVENT", "SENT_TO_OWNERS", "SHORT_MARK", "WHOLE_FILE", "WITHHELD_MARK", "as_blocker",
    "build_middleware",
    "cut_short", "effects_lines", "first_refusal", "forget", "record", "recorded", "short_refusal", "the_note",
    "to_the_running_owner", "to_their_owners", "with_them", "withheld",
]
