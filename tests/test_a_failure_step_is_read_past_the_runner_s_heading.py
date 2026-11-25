"""Where a failed page test stopped is read from what it threw, not the runner's heading over it.

Measured over the real failed-test messages of many runs: most Playwright messages open with the runner's heading
(`file:line:col › title ────`), so the foundation rule keyed every such failure on its own title and never saw two
tests that stopped at the same thrown error.
"""
from __future__ import annotations

from app.graph.foundation import failure_step

# Shape copied from a real Playwright failure (a captured acceptance result); the test's title differs per test.
_HEADED = (
    "  1) acceptance/auth.spec.js:23:1 › [AC-1] registration creates a new user "
    "──────────\n\n"
    "    Error: Login rate limited\n\n      at helpers.js:41:11\n"
)


def test_two_headed_failures_that_threw_the_same_share_a_step():
    other = _HEADED.replace("23:1", "57:1").replace("registration creates a new user", "login returns a token")

    assert failure_step(_HEADED) == failure_step(other) == "Error: Login rate limited"


def test_a_plain_message_still_reads_its_first_line():
    assert failure_step("Login failed with status 401\nmore") == "Login failed with status 401"
