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
    if not ((test_round == 0 and replans > 0) or _the_head_is_a_batch(root)):
        return ""
    return restore_if_worse(root)


def _the_head_is_a_batch(root: str | Path) -> bool:
    """Whether the last commit is a batch of work orders: this measurement is its first.

    A re-plan is not the only redraft. Measured on one run: a milestone review's revision (five findings) was a
    batch at round 4 of an attempt with no re-plan; it took a green product from 16 acceptance tests to 4, the best
    stayed on record unused, twelve per-defect fixes could not reach the cause, and only the next re-plan put the
    best back. The first measurement after any batch is judged the same way.
    """
    try:
        from app import ci

        done = ci._git(Path(root), "log", "-1", "--format=%s")
        return bool(done) and done.returncode == 0 and done.stdout.strip().startswith("Work orders:")
    except Exception:  # noqa: BLE001 - a record that cannot be read undoes nothing
        return False


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


def keep_on_a_replan_enabled() -> bool:
    return is_on("KEEP_THE_BEST_ON_A_REPLAN", False)


class _KeepOnAReplan:
    """`KEEP_THE_BEST_ON_A_REPLAN` as the switch registry reads one: off in code, the compose file turns it on."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A re-plan's redraft leaves alone the planned files the best product already has as they are, "
                   "instead of rewriting every file and wrecking a product that partly works (LF.295, LF.312).")

    @staticmethod
    def enabled() -> bool:
        return keep_on_a_replan_enabled()


keep_on_a_replan_switch = _KeepOnAReplan()


#: The re-plan from which a product under half the suite keeps its files too.
AFTER_A_FULL_REDRAFT = 2


def files_the_best_attempt_already_has(root: str | Path, paths: list[str], *, replans: int) -> set[str]:
    """The planned files a re-plan's redraft should leave as they are; empty when off or not a re-plan (behind `KEEP_THE_BEST_ON_A_REPLAN`).

    Measured over a day of small-model runs: a re-plan redrafted every planned file, and the best-attempt undo had
    to put the product back in about half the runs (16 tests to 15, 7 to 0, 3 to 0, 24 to 23), each time after a whole
    test round on the wreck. On a re-plan whose best product passes at least half of the suite, a planned file that
    is still exactly as it was in that best product is not drafted again; new files and changed files are. A product
    that passes less than half keeps the full redraft, which has sometimes paid (1 criterion to 12).
    """
    if not keep_on_a_replan_enabled() or replans < 1 or not paths:
        return set()
    try:
        from app import ci
        from app.acceptance import suite

        root = Path(root)
        best = _read(root)
        passed = int(best.get("passed") or 0)
        commit = str(best.get("commit") or "")
        last = suite.last_result(root) or {}
        total = int(last.get("passed") or 0) + int(last.get("failed") or 0)
        # Under half the suite the first re-plan redrafts whole, which has paid; from the second on one full redraft
        # has been tried. Measured on a small-model run: at 4 of 11 two re-plans in a row redrafted every file, each
        # fell to 0, and the run was stopped with the undo putting 3 files back each time.
        if passed <= 0 or not commit or total <= 0 or (passed * 2 < total and replans < AFTER_A_FULL_REDRAFT):
            return set()
        # The product as it stands, when it passes as many tests as the best: its files are the best files, whatever
        # the fixers changed since that commit. Measured: a re-plan at 8 of 9 tests kept one file - the fixers had
        # improved the others since the best commit - redrafted five, and the product fell to 2 of 10.
        as_good_now = int(last.get("passed") or 0) >= passed
        kept: set[str] = set()
        for path in paths:
            if not (root / path).is_file():
                continue
            if as_good_now:
                kept.add(path)
                continue
            same = ci._git(root, "diff", "--quiet", commit, "--", path)
            if same is not None and same.returncode == 0:
                kept.add(path)
        if kept:
            logger.info("A re-plan leaves %d file(s) as the best attempt had them (%d of %d tests passed)",
                        len(kept), passed, total)
        return kept
    except Exception:  # noqa: BLE001 - the redraft goes on as it always did
        logger.debug("Could not tell which files the best attempt has", exc_info=True)
        return set()

