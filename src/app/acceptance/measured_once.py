"""A product measured by the suite is not measured again until it changes (behind `MEASURE_ONCE`).

Measured on the fast-delivery path: the suite ran after every fix (`ci.take`), again as the round opened
(`acceptance_for_round`) and the unit tests a third time, with nothing changed between - on a service suite that
is minutes a round. `suite.last_result` already records a fingerprint of the product (`unstable.fingerprint`:
HEAD, the working-tree diff and the untracked files, less the harness's own folders). When the fingerprint is the
one the last run saved, the suite command is the same and its report is still on disk, the saved run stands and
is judged again against the criteria as they are now. A test that flips on the same tree is what the harness
already calls unstable, not a change in the product.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("MEASURE_ONCE", ON_BY_DEFAULT)


def saved_run_if_unchanged(repo_root: str | Path, command: str, report_file: Path) -> Any | None:
    """The last run as an `AcceptanceResult` when the product has not changed since; None when it must run again."""
    if not enabled():
        return None
    try:
        from app.acceptance import junit, suite
        from app.acceptance.unstable import unchanged_since_the_suite_measured

        saved = suite.last_result(repo_root) or {}
        if not saved.get("ran") or str(saved.get("command") or "") != command or not report_file.is_file():
            return None
        if not unchanged_since_the_suite_measured(repo_root):
            return None
        report = junit.read(report_file)
        if not report.found:
            return None
        # The report on disk is the run that was saved, not one written since by part of the suite: measured on one
        # run, a single file's re-measure left its ten tests where the suite's thirteen had been.
        counts = (saved.get("passed"), saved.get("failed"), saved.get("skipped"))
        if None not in counts and tuple(int(n or 0) for n in counts) != (report.passed, report.failed, report.skipped):
            return None
        logger.info("The product is as the suite last measured it; that measurement stands")
        return suite.AcceptanceResult(
            ran=True,
            exit_code=int(saved.get("exit_code") or 0),
            command=command,
            report=report,
            output=str(saved.get("output") or ""),
            server_log=str(saved.get("server_log") or ""),
            repairs=[],
            problem=str(saved.get("problem") or ""),
            runtime_problems=list(saved.get("runtime_problems") or []),
            shows=str(saved.get("shows") or ""),
        )
    except Exception:  # noqa: BLE001 - when in doubt, measure
        logger.debug("Could not reuse the last measurement", exc_info=True)
        return None


__all__ = ["ON_BY_DEFAULT", "enabled", "saved_run_if_unchanged"]
