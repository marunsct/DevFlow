"""A testing work order's refused product change is kept as its blocker (LF.1310).

Measured over nine recent runs: the refusal "'X' is product code, and this is the testing work order ..." was returned
54 times, up to 15 in one run and 8 in another. A testing builder writing tests against the other work orders' code
finds a real fault in it, tries to fix it, is refused, and tries again: the refusal told it to name the fault in
`blockers`, a local model kept trying the change instead, and every refusal cost a model call.

So the harness does what the refusal asked of the model, at the first refusal:

1. `record` keeps the attempted change - the product file, what the test needed (the edit's text or the start of the
   write, cut short) and the stage - in `.harness/testing-blockers.json`, and says whether it is new; the refusal then
   tells the stage it was recorded and will reach the builder that owns the file, and a second refusal of the same file
   in the same stage is one short line (`repository._a_tester_changing_the_product`).
2. `with_them` adds the stage's recorded changes to its `blockers` when it hands over, where the milestone review and
   the work-order ledger read a blocker the model reported.
3. `to_their_builders`, when every builder has finished and before CI (once an attempt, beside LF.1299's
   `unfinished_build.after_the_build`), sends each recorded change to the builder whose work order lists the file -
   or, when none does, the stage of this plan that created it - by the same `unfinished_orders` note LF.1299 uses: the
   builder runs again with what the tests need from its files. A change no builder of this plan owns stays a blocker.

Both the recording and the sending are in the defect ledger (`loop.sh effects`). The record is cleared with every new
milestone plan, whose stage names repeat. Nothing here names a language, a framework or a kind of product.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: Where the recorded changes are kept, by stage then file: the tool that refuses and the node that hands over share it.
RECORD_FILE = ".harness/testing-blockers.json"
#: How much of what the test needed is kept.
MOST_NEEDED_CHARS = 300

#: The ledger events and what their detail opens with (`loop.sh effects`).
RECORDED_EVENT = "testing blocker recorded"
RECORDED_SAID = "A product change refused to a testing work order, recorded as its blocker"
ROUTED_EVENT = "testing blocker sent to its builder"
ROUTED_SAID = "A testing work order's blocker sent to the builder of the file"

#: The `builders_sent_back` entry: the recorded changes have gone to their builders this attempt.
SENT_TO_BUILDERS = "testing blockers"

#: What a refusal says, so the effects report can count them per stage.
REFUSED_MARK = "is product code, and this is the testing work order"
REPEATED_MARK = "already recorded as this stage's blocker"

_LOCK = threading.Lock()


def cut_short(text: str, most: int = MOST_NEEDED_CHARS) -> str:
    """`text` on one line, at most `most` characters."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= most else flat[: most - 3].rstrip() + "..."


def _read(root: str | Path) -> dict[str, dict[str, dict[str, Any]]]:
    try:
        table = json.loads((Path(root) / RECORD_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return table if isinstance(table, dict) else {}


def record(root: str | Path, stage: str, path: str, needed: str) -> bool:
    """Keep one refused change as `stage`'s blocker; True the first time this stage is refused this file.

    A repeat counts the refusal and keeps what was first recorded. Never raises: a record that cannot be written reads
    as a first refusal, so the stage is told in full.
    """
    if not stage or not path:
        return True
    try:
        with _LOCK:
            table = _read(root)
            entries = table.setdefault(stage, {})
            entry = entries.get(path)
            first = entry is None
            if first:
                entries[path] = {"needed": cut_short(needed), "refusals": 1}
            else:
                entry["refusals"] = int(entry.get("refusals") or 1) + 1
            file = Path(root) / RECORD_FILE
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:  # noqa: BLE001 - the refusal stands without its record
        logger.warning("Could not record a testing stage's refused change", exc_info=True)
        return True
    if first:
        from app.observability import defect_ledger

        defect_ledger.note(RECORDED_EVENT, stage, detail=f"{RECORDED_SAID}: `{path}`: {cut_short(needed, 200)}")
    return first


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
        logger.debug("Could not clear the testing stages' recorded changes", exc_info=True)


def as_blocker(path: str, needed: str) -> str:
    """One recorded change as a blocker line."""
    said = f": the test needed {needed}" if needed else ""
    return f"`{path}` is product code this testing work order may not change{said}"


def with_them(output: Any, root: str | Path, stage: str) -> Any:
    """`output` with `stage`'s recorded changes among its blockers; `output` as it was when there are none."""
    entries = recorded(root, stage)
    if not entries:
        return output
    try:
        have = list(getattr(output, "blockers", None) or [])
        added = [as_blocker(path, str(entry.get("needed") or "")) for path, entry in sorted(entries.items())]
        added = [line for line in added if line not in have]
        if not added:
            return output
        return output.model_copy(update={"blockers": [*have, *added]})
    except Exception:  # noqa: BLE001 - its own output stands
        logger.debug("Could not add the recorded changes to %s's blockers", stage, exc_info=True)
        return output


# -- to the builder that owns the file ------------------------------------------------------------------------------


def _planned(path: str) -> str:
    cleaned = str(path or "").strip().replace("\\", "/")
    while cleaned.startswith(("./", "/")):
        cleaned = cleaned[2:] if cleaned.startswith("./") else cleaned[1:]
    return cleaned.rstrip("/")


def _lists(task: Any, path: str) -> bool:
    for planned in (_planned(p) for p in getattr(task, "files", None) or []):
        if planned and (path == planned or path.endswith("/" + planned) or path.startswith(planned + "/")):
            return True
    return False


def owner_of(path: str, stages: dict[str, Any], *, refused_to: str, root: str | Path) -> str | None:
    """The builder stage of this plan whose work order lists `path`, or else the one that created it; None if neither.

    `stages` maps each stage name of the plan to its work order. The stage refused never owns its own refusal.
    """
    listing = [stage for stage, task in stages.items() if stage != refused_to and _lists(task, path)]
    if len(listing) == 1:
        return listing[0]
    if listing:
        return None
    try:
        from app.analysis import project_memory

        created = project_memory.who_created(root, path)
    except Exception:  # noqa: BLE001 - unknown is no owner
        return None
    return created if created in stages and created != refused_to else None


HEADING = "What the testing work order needs from your files"
OPENING = ("While writing tests against your work order's interfaces, the testing work order needed these changes in "
           "your files and may not make them itself. Each is yours to judge against your work order:")
CLOSING = ("Make each change the interfaces you promised call for, in your own files, and check it as your work order "
           "says. Where a change is not what your work order promises, or is already made under another name, say so "
           "in your report and leave the code as it is.")


def _the_note(lines: Iterable[str]) -> str:
    return f"\n\n--- {HEADING} ---\n{OPENING}\n" + "\n".join(f"- {line}" for line in lines) + f"\n{CLOSING}"


def to_their_builders(state: Any) -> dict[str, Any] | None:
    """The fields that send every recorded change to the builder that owns its file, once an attempt; None if none.

    Never raises: a change that cannot be routed stays the testing stage's blocker.
    """
    try:
        if SENT_TO_BUILDERS in (state.get("builders_sent_back") or []):
            return None
        root = str(getattr(state.get("repository"), "root_path", "") or "")
        tasks = list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or [])
        if not root or not tasks:
            return None
        table = _read(root)
        if not table:
            return None
        from app.graph.workflow import _specialist_stage_name

        stages = {_specialist_stage_name(task, index): task for index, task in enumerate(tasks)}
        lines: dict[str, list[str]] = {}
        for refused_to, entries in sorted(table.items()):
            if refused_to not in stages or not isinstance(entries, dict):
                continue
            for path, entry in sorted(entries.items()):
                owner = owner_of(path, stages, refused_to=refused_to, root=root)
                if owner is None:
                    continue
                needed = str((entry or {}).get("needed") or "") if isinstance(entry, dict) else ""
                lines.setdefault(owner, []).append(f"`{path}`" + (f": the test needed {needed}" if needed else ""))
                from app.observability import defect_ledger

                defect_ledger.note(ROUTED_EVENT, refused_to, sprint=state.get("current_sprint_index", 0),
                                   detail=f"{ROUTED_SAID}: `{path}` to {owner}")
        if not lines:
            return None
        for owner, said in lines.items():
            logger.warning("A testing work order's recorded change(s) go to %s: %s", owner, "; ".join(said))
        return {"unfinished_orders": {owner: _the_note(said) for owner, said in lines.items()},
                "builders_sent_back": [*(state.get("builders_sent_back") or []), SENT_TO_BUILDERS]}
    except Exception:  # noqa: BLE001 - the build goes on as before
        logger.warning("Could not send the testing stages' recorded changes to their builders", exc_info=True)
        return None


def joined(first: dict[str, Any] | None, second: dict[str, Any] | None) -> dict[str, Any] | None:
    """Two send-backs of one hand-over as one update: each builder's notes joined, both marks kept."""
    if not first or not second:
        return first or second
    notes = dict(first.get("unfinished_orders") or {})
    for stage, note in (second.get("unfinished_orders") or {}).items():
        notes[stage] = (notes.get(stage) or "") + note
    marks = list(dict.fromkeys([*(first.get("builders_sent_back") or []), *(second.get("builders_sent_back") or [])]))
    return {**first, **second, "unfinished_orders": notes, "builders_sent_back": marks}


# -- `loop.sh effects` ----------------------------------------------------------------------------------------------


def effects_lines(records: list[dict]) -> list[str]:
    """LF.1310: changes recorded as blockers, those sent to a builder, and the refusals each testing stage was given."""
    recorded_n = sum(1 for r in records if isinstance(r, dict) and r.get("event") == RECORDED_EVENT)
    routed_n = sum(1 for r in records if isinstance(r, dict) and r.get("event") == ROUTED_EVENT)
    refusals: dict[str, int] = {}
    for r in records:
        if not isinstance(r, dict) or r.get("kind") != "tool_result":
            continue
        said = f"{r.get('content') or ''} {r.get('raised') or ''}"
        if REFUSED_MARK in said or REPEATED_MARK in said:
            stage = str(r.get("stage") or "")
            refusals[stage] = refusals.get(stage, 0) + 1
    if not (recorded_n or routed_n or refusals):
        return ["     -  LF.1310 a testing stage's refused product change kept as its blocker: not reached"]
    lines = [f"  {recorded_n:>4}  LF.1310 a testing stage's refused product change recorded as its blocker",
             f"  {routed_n:>4}  LF.1310 a recorded change sent to the builder that owns the file"]
    if refusals:
        lines.append("        product-code refusals per testing stage: "
                     + ", ".join(f"{stage} {n}" for stage, n in sorted(refusals.items())))
    return lines


__all__ = [
    "MOST_NEEDED_CHARS", "RECORDED_EVENT", "RECORDED_SAID", "RECORD_FILE", "REFUSED_MARK", "REPEATED_MARK",
    "ROUTED_EVENT", "ROUTED_SAID", "SENT_TO_BUILDERS", "as_blocker", "cut_short", "effects_lines", "forget", "joined",
    "owner_of", "record", "recorded", "to_their_builders", "with_them",
]
