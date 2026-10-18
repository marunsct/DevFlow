"""The owner's direction to a run while it runs (UI plan: steering).

Built on the owner's dynamic instruction injection, not beside it: a note is
kept in the run's workspace and the instruction middleware that already adds
the stack's instructions to every model call (`app.plugins.middleware`) adds
the run's notes too, from the next call on. Nothing is interrupted: the stage
in progress reads the note on its next call.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Where a run's notes are kept, inside its workspace's harness folder.
STEERING_FILE = ".harness/steering.json"
#: One note's length at most, and the notes a call carries at most (the newest).
MOST_NOTE_CHARS = 2_000
MOST_NOTES_PER_CALL = 5


#: How long a note applies: for the rest of the run, or for the one stage that is working when it is first applied.
SCOPES = ("run", "next_stage")


def _all(repo_root: str | Path) -> list[dict[str, Any]]:
    try:
        data = json.loads((Path(repo_root) / STEERING_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in data if isinstance(item, dict) and str(item.get("text") or "").strip()] if isinstance(data, list) else []


def _save(repo_root: str | Path, kept: list[dict[str, Any]]) -> None:
    path = Path(repo_root) / STEERING_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    temporary.replace(path)


def notes(repo_root: str | Path) -> list[dict[str, Any]]:
    """The run's notes, oldest first, with when each reached a call; [] when there are none."""
    return _all(repo_root)


def add(repo_root: str | Path, text: str, by: str, scope: str = "run") -> dict[str, Any]:
    """Keep one note for the run's next model calls."""
    cleaned = str(text or "").strip()
    if not cleaned:
        raise ValueError("A note needs some text.")
    if scope not in SCOPES:
        raise ValueError(f"A note's scope is one of {', '.join(SCOPES)}.")
    kept = _all(repo_root)
    note = {
        "id": f"N-{1 + max((int(str(n.get('id', 'N-0')).split('-')[-1]) for n in kept), default=0)}",
        "text": cleaned[:MOST_NOTE_CHARS],
        "by": str(by or "owner"),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": scope,
    }
    _save(repo_root, kept + [note])
    return note


def _applied(repo_root: str | Path, stage: str, run_id: str | None) -> list[dict[str, Any]]:
    """The notes that apply to a call in `stage`, marking each the first time it reaches one.

    A `next_stage` note applies to the stage it first reached and to no other.
    The first time a note reaches a call, a `steering_applied` record goes in
    the run's transcript - the owner's proof it was read (Initiative AS).
    """
    kept = _all(repo_root)
    live: list[dict[str, Any]] = []
    changed = False
    for note in kept:
        first = note.get("applied_stage")
        if first and note.get("scope") == "next_stage" and first != stage:
            continue
        if not first:
            note["applied_stage"], note["applied_at"] = stage, datetime.now(timezone.utc).isoformat(timespec="seconds")
            changed = True
            try:
                from app.observability.transcript import record

                record(run_id or "", stage, "steering_applied", note_id=note.get("id"), scope=note.get("scope"))
            except Exception:  # noqa: BLE001 - a record that cannot be kept never stops a call
                pass
        live.append(note)
    if changed:
        _save(repo_root, kept)
    return live


def as_instructions(repo_root: str | Path, stage: str = "", run_id: str | None = None) -> str:
    """The notes that apply to this call, the newest few, as a block of the system prompt, or ""."""
    live = _applied(repo_root, stage, run_id)[-MOST_NOTES_PER_CALL:]
    if not live:
        return ""
    return (
        "\n\n=== THE OWNER'S DIRECTION FOR THIS RUN ===\n"
        "The owner sent these while the run was going; they come before any other preference:\n"
        + "\n".join(f"- {note['text']}" for note in live)
    )
