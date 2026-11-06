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


import contextlib
import fcntl
import threading

#: One writer at a time, across the API's and the worker's processes and threads: the API adds notes while stages mark
#: them read, and an unlocked read-change-write could drop a note.
_IN_THIS_PROCESS = threading.Lock()


@contextlib.contextmanager
def _locked(repo_root: str | Path):
    path = Path(repo_root) / (STEERING_FILE + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with _IN_THIS_PROCESS, open(path, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


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
    with _locked(repo_root):
        return _add_locked(repo_root, cleaned, by, scope)


def _add_locked(repo_root: str | Path, cleaned: str, by: str, scope: str) -> dict[str, Any]:
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
    if not _all(repo_root):
        return []
    with _locked(repo_root):
        return _applied_locked(repo_root, stage, run_id)


def _applied_locked(repo_root: str | Path, stage: str, run_id: str | None) -> list[dict[str, Any]]:
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
        f"\n\n{DIRECTION_HEADER}\n"
        "The owner sent these while the run was going; they come before any other preference:\n"
        + "\n".join(f"- {note['text']}" for note in live)
    )


#: How the direction block begins, so a call that already carries it is not given it twice.
DIRECTION_HEADER = "=== THE OWNER'S DIRECTION FOR THIS RUN ==="
#: Each run's workspace, read once per process.
_WORKSPACES: dict[str, str] = {}


def _this_call_s_run_and_stage() -> tuple[str | None, str | None]:
    from app.observability.log_context import _TASK_RUN, _from_the_graph

    run, stage = _from_the_graph()
    return run or _TASK_RUN.get(), stage


def _the_workspace_of(run_id: str) -> str | None:
    if run_id not in _WORKSPACES:
        from app.server.run_store import RunStore

        record = RunStore.shared().load(run_id)
        root = str(getattr(record, "repo_root", "") or "")
        if not root:
            return None
        _WORKSPACES[run_id] = root
    return _WORKSPACES[run_id]


def with_the_direction(messages: list[Any]) -> list[Any]:
    """`messages` with the run's direction in their system message, for a call no agent middleware gave it to. Never raises.

    Measured on 2026-11-06: notes reached only the calls agents make, through their instruction middleware; drafting,
    rewritten fixes, the specification's parts and eleven other direct calls never carried one, so a direction never
    reached the code the product is written in. Called by the shared chat model for every call; a call that already
    carries the block is left as it is.
    """
    try:
        if any(DIRECTION_HEADER in str(getattr(m, "content", "") or "") for m in messages or ()):
            return messages
        run_id, stage = _this_call_s_run_and_stage()
        if not run_id:
            return messages
        root = _the_workspace_of(str(run_id))
        if not root or not _all(root):
            return messages
        direction = as_instructions(root, str(stage or ""), str(run_id)).strip()
        if not direction:
            return messages
        from langchain_core.messages import SystemMessage

        first = messages[0] if messages else None
        if isinstance(first, SystemMessage) and isinstance(first.content, str):
            return [SystemMessage(content=f"{first.content}\n\n{direction}"), *messages[1:]]
        return [SystemMessage(content=direction), *messages]
    except Exception:  # noqa: BLE001 - a direction that cannot be read never costs the call
        return messages
