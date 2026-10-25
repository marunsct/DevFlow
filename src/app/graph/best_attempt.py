"""A sprint that is planned again starts from the best product it has had, not the worst (behind `KEEP_THE_BEST_ATTEMPT`).

Measured on a small-model run: a sprint's first attempt ended at 14 of 18 acceptance criteria passing, remediation was
exhausted, the sprint was planned again, and the new drafting rewrote working files. The next rounds measured 0 of 18
with no test reaching the product, and every attempt after it started from that. Nothing in the run kept the 14.

Each round that passes more acceptance tests than any before it is committed and remembered. When a sprint is about
to be planned again (or escalated) and the product now passes at least `MARGIN` fewer tests than that best, the
product's files are put back as they were at the best commit - except the locked suite and the harness's own files -
so the next attempt, or the person the run escalates to, finds the best product, not the last. Off, nothing changes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: How many acceptance tests fewer than the best counts as worse: one test is noise.
MARGIN = 2

_FILE = ".harness/best-attempt.json"


def enabled() -> bool:
    return is_on("KEEP_THE_BEST_ATTEMPT", ON_BY_DEFAULT)


def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / _FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _passed_now(root: Path) -> int | None:
    """The acceptance tests passing in the suite's last run, or None when it has not run."""
    from app.acceptance import suite

    result = suite.last_result(root) or {}
    if not result.get("ran"):
        return None
    return int(result.get("passed") or 0)


def note(root: str | Path) -> None:
    """Remember the product as it stands when it passes more acceptance tests than any before. Never raises."""
    if not enabled():
        return
    try:
        from app import ci

        root = Path(root)
        passed = _passed_now(root)
        best = _read(root)
        if passed is None or passed <= int(best.get("passed") or 0):
            return
        commit = ci.commit(root, f"Best attempt so far: {passed} acceptance tests pass")
        if not commit:
            return
        (root / _FILE).parent.mkdir(parents=True, exist_ok=True)
        (root / _FILE).write_text(json.dumps({"passed": passed, "commit": commit}) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001 - a record of the best is never worth a failed round
        logger.debug("Could not note the best attempt", exc_info=True)


def after_a_redraft(root: str | Path, *, test_round: int, replans: int) -> str:
    """At the first measurement of a re-planned sprint: put the best product back if the redraft left it clearly worse.

    Measured on three runs in one night: a re-plan's redraft took a product from 14 of 18 criteria to 0, from 17 to 12,
    and from 4 tests to 0. Putting the best back only at the next re-plan cost a whole round of fixers on the wreck.
    A redraft is a gamble that sometimes pays (one took a product from 1 to 12 criteria); a bad one is undone at its
    first measurement and the sprint is planned again. Returns what was done, or "" (not a re-plan's first round, no
    clear drop, or off), in which case the round goes on as it does.
    """
    if test_round != 0 or replans <= 0:
        return ""
    return restore_if_worse(root)


def _kept(path: str, locked: set[str]) -> bool:
    """Whether a path stays as it is: the locked suite, the harness's own files, what git ignores anyway."""
    parts = Path(path).parts
    return path in locked or ".harness" in parts or ".git" in parts or "node_modules" in parts


def restore_if_worse(root: str | Path, *, margin: int = MARGIN) -> str:
    """Put the product back to its best commit when it passes `margin` fewer acceptance tests now; what was done, or "". Never raises."""
    if not enabled():
        return ""
    try:
        from app import ci
        from app.acceptance import suite

        root = Path(root)
        best = _read(root)
        now = _passed_now(root)
        if not best or now is None or int(best.get("passed") or 0) - now < margin:
            return ""
        best_commit = str(best.get("commit") or "")
        current = ci.commit(root, "Before the best attempt is put back")
        changed = ci._git(root, "diff", "--name-only", best_commit, current, "--", ".", ":(exclude)docs")
        if changed is None or changed.returncode != 0:
            return ""
        locked = {str(path.relative_to(root)) for path in suite.suite_files(root) if path.is_relative_to(root)}
        paths = [line.strip() for line in changed.stdout.splitlines() if line.strip() and not _kept(line.strip(), locked)]
        if not paths or not ci.restore_paths(root, best_commit, paths):
            return ""
        ci.commit(root, f"Put back the best attempt ({best['passed']} acceptance tests passed; {now} did)")
        # What the harness decides next (which criteria still fail, whether more than half the product is
        # undelivered) reads the suite's last saved result. That was the wrecked product's: a run was stopped for
        # 21 failing criteria with its best product, 12 of them passing, already back on disk.
        try:
            suite.run(root)
        except Exception:  # noqa: BLE001 - the restore stands; the next measurement corrects the record
            logger.debug("Could not measure the product that was put back", exc_info=True)
        said = (f"The product passes {now} acceptance tests now and passed {best['passed']} at its best; "
                f"{len(paths)} file(s) were put back as they were then.")
        logger.warning(said)
        return said
    except Exception:  # noqa: BLE001 - the sprint is planned again as it would have been
        logger.debug("Could not put back the best attempt", exc_info=True)
        return ""
