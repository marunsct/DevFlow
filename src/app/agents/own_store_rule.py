"""A unit test that stores data starts from an empty store of its own, said to whoever writes or repairs unit tests (LF.1316).

Measured on a full-stack run: one store test file failed with "6 !== 1" and with six records where an empty list was
expected - every test's records stayed for the next, as one store file served the whole test file - and the fixer held
to test files rewrote it five times over two rounds, about six minutes each, without giving each test a store of its
own. It is one root of the recurring note that a product's own unit tests ship failing.

`FOR_TEST_WRITERS` goes to the testing role, to the draft of each test file and to each testing builder; `FOR_A_FIXER`
to a fixer held to test files (`app.tools.tests_only_writes`) and with the evidence of `app.analysis.shared_store_tests`.
How a test in one language gets its own store is that language's row (`app.stacks.languages`, `fresh_store`).
"""

from __future__ import annotations

FOR_TEST_WRITERS = (
    "A unit test that stores data starts from an empty store of its own - a fresh temporary data folder (the "
    "project's `DATA_DIR`-style setting) or a store cleared before each test - and never counts on what another test "
    "stored."
)

FOR_A_FIXER = (
    "Unit tests that count or list stored records fail together when they share one store: give every test of the "
    "file an empty store of its own - a fresh temporary data folder (the project's `DATA_DIR`-style setting) or the "
    "store cleared before each test - in one rewrite, rather than changing the counts and lists the tests expect."
)

__all__ = ["FOR_A_FIXER", "FOR_TEST_WRITERS"]
