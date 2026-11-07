"""Fixes undone because the product stopped starting after them, told to every fixer after them.

Measured over 37 stored runs: 128 fixes were reverted as "the product no longer builds or starts after it", and 11
runs had three or more in a row - one ten long. Each fixer was given its own criterion's failure and none was told
that the fixers before it had made a change that stopped the product, nor what the product raised; each made the
same change again. The streak is recorded in the workspace and cleared by the first fix that is kept.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FILE = ".harness/start_breaks.json"
#: The causes kept, newest last.
MOST_KEPT = 3
HEADING = "--- Fixes undone because the product stopped starting (measured by the harness) ---"


def _path(root: str | Path) -> Path:
    return Path(root) / FILE


def _read(root: str | Path | None) -> dict[str, Any]:
    if not root:
        return {}
    try:
        data = json.loads(_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record(root: str | Path, stage: str, cause: str) -> None:
    """One more fix undone because the product stopped starting. Never raises."""
    try:
        data = _read(root)
        causes = [*list(data.get("causes") or []), {"stage": stage, "cause": " ".join(str(cause).split())[:600]}]
        path = _path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"count": int(data.get("count") or 0) + 1, "causes": causes[-MOST_KEPT:]}),
                        encoding="utf-8")
    except Exception:  # noqa: BLE001 - a fix is measured the same without the record
        logger.debug("Could not record a start break", exc_info=True)


def clear(root: str | Path) -> None:
    """A fix was kept: the streak ends. Never raises."""
    try:
        _path(root).unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not clear the start breaks", exc_info=True)


def the_section(root: str | Path | None) -> str:
    """The block a fixer's request ends with while the streak lasts; "" otherwise. Never raises."""
    data = _read(root)
    causes = [c for c in data.get("causes") or [] if isinstance(c, dict) and c.get("cause")]
    if not causes:
        return ""
    count = int(data.get("count") or len(causes))
    last = causes[-1]
    return (
        f"\n\n{HEADING}\n- {count} fix{'es' if count != 1 else ''} in a row, the last in {last.get('stage')}, "
        "changed the product so that it no longer started, and each was undone. What it printed the last time: "
        f"{last.get('cause')}\n- Read that error before changing how the product is set up or started. A change that "
        "repeats it is undone again; make the product start with your change, then make your criterion pass.\n"
    )


__all__ = ["FILE", "HEADING", "clear", "record", "the_section"]
