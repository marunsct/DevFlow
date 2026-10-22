"""Whether the workers can run commands, as the workers themselves found it.

Commands run in the worker, so only a worker can say whether they will: the
API process shares the settings but not the runtime socket a worker may have
mounted. Each worker records what it found when it starts, and a run is
refused before its first model call when the record says commands cannot run.
No record at all - an older worker, or a deployment without the shared store -
refuses nothing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: Where a worker leaves what it found.
READINESS_KEY = "harness:execution-readiness"


def readiness_record(ready: bool, detail: str) -> str:
    """The record a worker leaves, as stored."""
    return json.dumps(
        {"ready": bool(ready), "detail": detail, "checked_at": datetime.now(timezone.utc).isoformat()}
    )


def record_this_workers_readiness(client: Any) -> None:
    """Probe this process and leave the result where the API can read it. Never raises."""
    try:
        from app.tools.sandbox import execution_readiness

        ready, detail = execution_readiness()
        client.set(READINESS_KEY, readiness_record(ready, detail))
        (logger.info if ready else logger.warning)("Command execution: %s", detail)
    except Exception:  # noqa: BLE001 - a worker that cannot probe still takes tasks
        logger.warning("Could not record whether commands can run", exc_info=True)


def why_commands_cannot_run(stored: str | bytes | None) -> str | None:
    """The reason a stored record gives for refusing a run, or None to let it start."""
    if not stored:
        return None
    try:
        record = json.loads(stored)
    except (TypeError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("ready") is not False:
        return None
    return str(record.get("detail") or "The workers cannot run commands.")
