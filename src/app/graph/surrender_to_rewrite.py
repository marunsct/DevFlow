"""A fix stage that gave up goes to the rewrite path once before its defect is left open (behind `SURRENDER_TO_REWRITE`).

Measured over ten runs: the five costliest agent-loop fix stages (36-40 calls, 1.1-1.9M input tokens each) ended in
a surrender - an answer with no changed file, "we can't fix all" in its blockers - and the defect was left open for
the next test round to raise again. The harness's own rewrite (`rewritten_fixes.fix_by_rewriting`: it gathers the
failure and the files it points at and asks for each file whole) was never tried on a defect the agent loop gave up
on, only on one it was tried on first (fast delivery) or after a failed fix (candidates).

With the switch on, an answer that changed no file is replaced by the rewrite's, when the rewrite writes one. It is
asked once per fix attempt, and its change is measured and reverted like any other fix. When it writes nothing the
agent loop's answer stands and the defect is left open as before.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `SURRENDER_TO_REWRITE` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("SURRENDER_TO_REWRITE", ON_BY_DEFAULT)


def surrendered(output: Any) -> bool:
    """Whether a fix stage's answer changed no file: it gave up, or found nothing to change."""
    return output is not None and not list(getattr(output, "changed_files", None) or [])


def after_a_surrender(output: Any, rewrite: Callable[[], Any | None]) -> Any:
    """`output`, or the rewrite's answer when `output` changed no file and the rewrite wrote one. Never raises."""
    if not enabled() or not surrendered(output):
        return output
    try:
        rewritten = rewrite()
    except Exception:  # noqa: BLE001 - the stage's own answer stands and the defect stays open
        logger.warning("The rewrite after a surrender failed to run", exc_info=True)
        return output
    if rewritten is None or surrendered(rewritten):
        return output
    logger.info("The agent loop changed nothing; the harness rewrote %s", ", ".join(rewritten.changed_files))
    return rewritten


__all__ = ["ON_BY_DEFAULT", "after_a_surrender", "enabled", "surrendered"]
