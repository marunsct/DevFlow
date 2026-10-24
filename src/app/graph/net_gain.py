"""A fix that makes many tests pass and breaks one of the workers' unit tests is kept (behind `KEEP_NET_GAINS`).

Measured on a small-model run: a fix made 12 tests pass and broke 1 unit test (a test the same model had written for
sign-up), and was reverted whole; four more fixes that each repaired one criterion and broke that same test were
reverted too, so the sprint went round again with nothing gained. The gate protects what passed before it; it did
not weigh what the fix gained.

The fix stays when it gained at least `MIN_GAINED` tests and `RATIO` times as many as it broke, broke only unit tests
(never an acceptance test, which is the locked spec), and left the product able to build and start. The broken test is
not hidden: the snapshot kept is the one after the fix, so the next test round finds that unit test failing and raises
it as a defect like any other. Off, a fix that broke anything that passed is reverted, as before.
"""
from __future__ import annotations

from collections.abc import Collection

from app.switches import is_on

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False

#: The least a fix must gain to be weighed against what it broke, and how many times what it broke.
MIN_GAINED = 3
RATIO = 3


def enabled() -> bool:
    return is_on("KEEP_NET_GAINS", ON_BY_DEFAULT)


def keeps(lost: Collection[str], gained: Collection[str], *, product_runs: bool) -> bool:
    """Whether a fix that broke the tests in `lost` and made those in `gained` pass stays."""
    if not enabled() or not product_runs or not lost:
        return False
    if any(not str(name).startswith("unit: ") for name in lost):
        return False
    return len(gained) >= MIN_GAINED and len(gained) >= RATIO * len(lost)
