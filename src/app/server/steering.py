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


def notes(repo_root: str | Path) -> list[dict[str, Any]]:
    """The run's notes, oldest first, or [] when there are none."""
    try:
        data = json.loads((Path(repo_root) / STEERING_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in data if isinstance(item, dict) and str(item.get("text") or "").strip()] if isinstance(data, list) else []


def add(repo_root: str | Path, text: str, by: str) -> dict[str, Any]:
    """Keep one note for the run's next model calls."""
    cleaned = str(text or "").strip()
    if not cleaned:
        raise ValueError("A note needs some text.")
    note = {
        "text": cleaned[:MOST_NOTE_CHARS],
        "by": str(by or "owner"),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = Path(repo_root) / STEERING_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = notes(repo_root) + [note]
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    temporary.replace(path)
    return note


def as_instructions(repo_root: str | Path) -> str:
    """The run's newest notes as a block of the system prompt, or ""."""
    kept = notes(repo_root)[-MOST_NOTES_PER_CALL:]
    if not kept:
        return ""
    return (
        "\n\n=== THE OWNER'S DIRECTION FOR THIS RUN ===\n"
        "The owner sent these while the run was going; they come before any other preference:\n"
        + "\n".join(f"- {note['text']}" for note in kept)
    )
