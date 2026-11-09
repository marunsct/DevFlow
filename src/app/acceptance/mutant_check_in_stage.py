"""A fixer asked for a test that notices a deliberate change is told, at each write, whether it does (behind `MUTANT_CHECK_IN_THE_FIX_STAGE`).

A mutation finding is settled by the harness after the fix stage ends: it makes the
change, runs the unit tests and puts the line back (`mutation_guided.settled`). The
fixer meanwhile wrote its test blind - for a finding, `_the_defect_s_tests_pass` has no
tests of the defect's own to run, so the checks after a write (`verify_after_write`)
answered nothing - and learned the outcome only when its stage was over. A test that
did not notice the change cost a whole second stage, and the sprint often had no round
left for one: the finding became a completion gap.

With the switch on, each write in a finding's fix stage runs that one check - only that
change, against the unit tests as they now are - and appends its outcome to the write's
reply: the change is noticed and the finding is settled, or the unit tests still pass
with it. At most `MOST_CHECKS` times a stage, since each is two runs of the unit tests.
Linear fixes only: a fix stage running beside others must not have the product changed
under them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.acceptance import mutation_guided
from app.switches import is_on

#: `MUTANT_CHECK_IN_THE_FIX_STAGE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Checks a stage gets: each makes the change and runs the unit tests with it and without it.
MOST_CHECKS = 3
#: What a write is answered with when the change is now noticed, and when it is not.
SAYS = (
    "The harness made the deliberate change described above and ran the unit tests: at least one now fails with it "
    "and passes without it. Your finding is settled: give your answer now.",
    "The harness made the deliberate change described above and ran the unit tests: every one that passes without it "
    "still passes with it, so no test notices it yet. The test must fail where that line decides the outcome - give "
    "it an input on which the changed and the original line give different results, and assert the original's.",
)


def enabled() -> bool:
    return is_on("MUTANT_CHECK_IN_THE_FIX_STAGE", ON_BY_DEFAULT)


def check_for(root: str | Path, defect: Any, default: Callable[[], bool | None]) -> Callable[[], bool | None]:
    """The check to run after a write in the stage fixing `defect`: its change's, or `default` for any other defect."""
    if not enabled() or not mutation_guided.is_a_finding(defect):
        return default
    return lambda: mutation_guided.settled(root, defect)


def how_for(defect: Any) -> dict[str, Any]:
    """The arguments of `verify_after_write.watching` that go with `check_for`'s check; {} for any other defect."""
    if not enabled() or not mutation_guided.is_a_finding(defect):
        return {}
    return {"says": SAYS, "most": MOST_CHECKS}


__all__: list[Any] = ["MOST_CHECKS", "ON_BY_DEFAULT", "SAYS", "check_for", "enabled", "how_for"]
