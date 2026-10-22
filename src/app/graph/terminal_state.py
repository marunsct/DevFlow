"""The workspace must tell the truth after the run ends (Initiative J.6).

A failed run's workspace looked exactly like a released one: the product was
there, the suite was there, and nothing said "this did not ship". The database
knew and the artifacts did not - monitoring-handover §8.3 measured it, and a
`completed_with_gaps` status that lives only in the database is half an
honesty mechanism (J.4). Every terminal state but a clean release writes a
machine-readable marker into the workspace root, where any archive or
handover of the workspace carries it; a clean release clears it; the run's
status API reports what it says.

The marker is deliberately at the root and deliberately loud: it is for a
person or a script meeting the workspace cold, not for the graph. Nothing in
a later stage reads it to decide anything - the run is over when it is
written - so a stale marker can only mislead a human, and `clear` on a clean
release is what keeps it from doing even that.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The marker file, in the workspace root.
MARKER = "NON-DELIVERABLE.json"


def mark(
    root: Any, *, status: str, reason: str = "", stage: str = "", gaps: list[str] | None = None
) -> None:
    """Write the non-deliverable marker. Never raises.

    A marker that cannot be written must not fail the terminal write it rides
    - that would lose the run's real error, which matters more than the sign
    on the door.
    """
    try:
        path = Path(str(root)) / MARKER
        path.write_text(
            json.dumps(
                {
                    "deliverable": False,
                    "status": str(status),
                    "reason": str(reason or ""),
                    "stage": str(stage or ""),
                    "completion_gaps": [str(gap) for gap in gaps or []],
                    "at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 - the sign must never cost the run its error
        logger.warning("Could not write the non-deliverable marker", exc_info=True)


def clear(root: Any) -> None:
    """Remove the marker: a clean release leaves nothing to say. Never raises."""
    try:
        path = Path(str(root)) / MARKER
        if path.is_file():
            path.unlink()
    except Exception:  # noqa: BLE001
        logger.warning("Could not clear the non-deliverable marker", exc_info=True)


def read(root: Any) -> dict[str, Any] | None:
    """The marker as written, or None.

    Absent, unreadable or malformed all answer None: the marker tells the
    truth about a run, and a broken marker telling something invented would
    be worse than silence.
    """
    try:
        path = Path(str(root or "")) / MARKER
        found = json.loads(path.read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else None
    except Exception:  # noqa: BLE001
        return None


__all__ = ["MARKER", "clear", "mark", "read"]
