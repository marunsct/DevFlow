"""A fix keeps the best version it reached, not its last or its start.

Deep review 2026-11-18 (A3): a fixer fixed its error, broke the build with its last edit, and had its tools withheld
before it could answer; the broken build was kept, or the whole stage was reverted to where it started and the fix
it had made was lost. Now each write whose immediate check (`verify_after_write`) finds the defect's own tests
passing records a checkpoint - a commit of the workspace as it is, made beside the branch, so neither HEAD nor the
index moves. When the stage ends worse than that checkpoint - reverted for what it broke, or its own tests failing
again - the checkpoint is put back and measured in its place, and kept only if that measurement holds.

Only a fix made alone: fixers of a batch share one workspace, and a checkpoint would hold the others' half-done work.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_lock = threading.Lock()
#: (run, stage) -> the latest checkpoint whose check passed.
_best: dict[tuple[str, str], str] = {}


def snapshot(root: str | Path, message: str) -> str:
    """A commit of the workspace as it is now, parented on HEAD, that moves neither HEAD nor the index; "" if none."""
    from app.tools.version_control import _git

    base = Path(root)
    with tempfile.TemporaryDirectory() as scratch:
        index = Path(scratch) / "index"
        steps = (("read-tree", "HEAD"), ("add", "-A"))
        for step in steps:
            done = _git(base, *step, index=index)
            if done is None or done.returncode != 0:
                return ""
        tree = _git(base, "write-tree", index=index)
        if tree is None or tree.returncode != 0 or not tree.stdout.strip():
            return ""
        made = _git(base, "-c", "user.name=harness", "-c", "user.email=harness@localhost",
                    "commit-tree", tree.stdout.strip(), "-p", "HEAD", "-m", message)
        return made.stdout.strip() if made is not None and made.returncode == 0 else ""


def record(root: str | Path, run_id: str | None, stage: str) -> None:
    """Keep the workspace as it is now as `stage`'s best so far. Never raises."""
    try:
        made = snapshot(root, f"{stage}: its own tests pass here")
        if made:
            with _lock:
                _best[(str(run_id or ""), stage)] = made
    except Exception:  # noqa: BLE001 - the fix goes on without a checkpoint
        logger.debug("Could not record a checkpoint for %s", stage, exc_info=True)


def take(run_id: str | None, stage: str) -> str:
    """`stage`'s best checkpoint, forgotten as it is handed over; "" when it has none."""
    with _lock:
        return _best.pop((str(run_id or ""), stage), "")


def instead_of(
    root: str | Path, run_id: str | None, stage: str, fix_base: str, broke: list[str],
    its_tests_pass_now: Callable[[], bool | None], measure: Callable[[str], list[str]],
) -> list[str] | None:
    """The stage's best checkpoint measured in place of how it ended, when it ended worse; None when not tried.

    `broke` is what `engineering.after_a_fix` returned for the stage's end. Reverted (it broke something), the
    checkpoint is measured against the stage's start (`measure(fix_base)`): what it breaks, [] when it holds and is
    kept.
    Kept with its own tests failing again, the checkpoint is measured against the kept end, which a checkpoint that
    breaks something goes back to; [] either way.
    """
    from app import ci

    checkpoint = take(run_id, stage)
    if not checkpoint:
        return None
    try:
        if broke:
            if not ci.revert_to(root, checkpoint):
                ci.revert_to(root, fix_base)
                return None
            logger.warning("%s ended broken; measuring its best checkpoint, where its own tests passed", stage)
            return measure(fix_base)
        if its_tests_pass_now() is not False:
            return None
        end = ci.head(root)
        if not end or not ci.revert_to(root, checkpoint):
            return None
        logger.warning("%s ended with its own tests failing again; measuring its best checkpoint", stage)
        measure(end)
        return []
    except Exception:  # noqa: BLE001 - the stage's end stands as measured
        logger.warning("Could not measure %s's best checkpoint", stage, exc_info=True)
        return None
