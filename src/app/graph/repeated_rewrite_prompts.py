"""A rewrite whose prompt is byte-identical to three that already failed is not sent a fourth time (behind `REPEATED_REWRITE_PROMPT_STOP`).

By the code's own flow: after a failed fix the harness asks the model for three candidate rewrites
of the defect's files, all with the same prompt, and when none passes the defect's tests the single rewrite that
follows (`rewritten_fixes.fix_by_rewriting`) is asked with that same prompt again - a fourth sample of a request
three samples had just answered wrongly. The same holds across a defect's attempts whenever nothing in the prompt
has changed.

With the switch on, each prompt sent for a rewrite is fingerprinted with the workspace it was sent for. A candidate
that fails its defect's tests counts as one failure of its prompt, and a single rewrite counts as one when it is
sent (a rewrite that holds closes its defect, so the prompt is not asked again). At `MOST_IDENTICAL` failures the
prompt is not sent again: the rewrite returns nothing and the defect goes to the agent loop, whose request is
different. The count lives in the process: a restarted worker asks once more, then counts again.
"""

from __future__ import annotations

import hashlib
import threading

from app.switches import is_on

#: `REPEATED_REWRITE_PROMPT_STOP` set to on or off overrides this.
ON_BY_DEFAULT = False

#: The same prompt this many times failed is not sent again.
MOST_IDENTICAL = 3

_failures: dict[tuple[str, str], int] = {}
_lock = threading.Lock()


def enabled() -> bool:
    return is_on("REPEATED_REWRITE_PROMPT_STOP", ON_BY_DEFAULT)


def _key(root: object, prompt: str) -> tuple[str, str]:
    return str(root), hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()


def exhausted(root: object, prompt: str) -> bool:
    """Whether `prompt` has already failed `MOST_IDENTICAL` times in this workspace; False when off."""
    if not enabled():
        return False
    with _lock:
        return _failures.get(_key(root, prompt), 0) >= MOST_IDENTICAL


def failed(root: object, prompt: str) -> None:
    """Count one failure of `prompt` in this workspace; nothing when off."""
    if not enabled():
        return
    with _lock:
        key = _key(root, prompt)
        _failures[key] = _failures.get(key, 0) + 1


def forget() -> None:
    """Drop every count (a test's hook)."""
    with _lock:
        _failures.clear()


__all__ = ["MOST_IDENTICAL", "ON_BY_DEFAULT", "enabled", "exhausted", "failed", "forget"]
