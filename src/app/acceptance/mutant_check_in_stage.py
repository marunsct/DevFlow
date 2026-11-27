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
#: What a write is answered with when the change is now noticed, when it is not, and when it could not be checked -
#: no unit test passes as the files are now (LF.1623). Measured on a C# run: a write that left the test file not
#: compiling was answered "every one that passes without it still passes with it", none passing either way, and the
#: fixer spent its last call on the same check; its fix was reverted for the build.
SAYS = (
    "The harness made the deliberate change described above and ran the unit tests: at least one now fails with it "
    "and passes without it. Your finding is settled: give your answer now.",
    "The harness made the deliberate change described above and ran the unit tests: every one that passes without it "
    "still passes with it, so no test notices it yet. The test must fail where that line decides the outcome - give "
    "it an input on which the changed and the original line give different results, and assert the original's.",
    "The harness could not check the deliberate change described above: with the files as they are now, no unit test "
    "passes - they do not compile, do not start, or every one fails - or the line is no longer where it was. Make the "
    "unit tests compile and pass on the product as it is first; a test that cannot run notices nothing.",
)


def enabled() -> bool:
    return is_on("MUTANT_CHECK_IN_THE_FIX_STAGE", ON_BY_DEFAULT)


def check_for(root: str | Path, defect: Any, default: Callable[[], bool | None]) -> Callable[[], bool | None]:
    """The check to run after a write in the stage fixing `defect`: its change's, or `default` for any other defect."""
    if not enabled() or not mutation_guided.is_a_finding(defect):
        return default
    return lambda: mutation_guided.settled(root, defect)


def how_for(defect: Any, root: str | Path | None = None) -> dict[str, Any]:
    """The arguments of `verify_after_write.watching` that go with `check_for`'s check; {} for any other defect.

    With `root`, a check that does not settle the finding is followed by what the unit run said when it failed - the
    compiler's errors in it, else its end (`ci.what_the_unit_run_said`).
    """
    if not enabled() or not mutation_guided.is_a_finding(defect):
        return {}
    how: dict[str, Any] = {"says": SAYS, "most": MOST_CHECKS}
    if root is not None:
        from app import ci

        how["then"] = lambda: ci.what_the_unit_run_said(root)
    return how


__all__: list[Any] = ["MOST_CHECKS", "ON_BY_DEFAULT", "SAYS", "check_for", "enabled", "how_for"]
