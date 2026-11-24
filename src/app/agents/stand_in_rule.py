"""What a unit test that stands a component in can check, said to whoever writes or repairs unit tests (LF.1312).

Measured over 60 scored runs: 12 shipped their own unit tests failing or set aside while every hidden test passed. On
one, a controller slice test replaced the service with a stand-in and asserted the service's validation rule (an empty
title refused with 400); the controller answered 201, the test could never pass, and the fixes in tests-only mode left
it so. The product kept the rule all along.

`FOR_TEST_WRITERS` goes to the testing role, to the draft of each test file and to each testing builder; `FOR_A_FIXER`
to a fixer held to test files (`app.tools.tests_only_writes`) and with the evidence of `app.analysis.stand_in_tests`.
"""

from __future__ import annotations

FOR_TEST_WRITERS = (
    "A test that replaces a component with a stand-in (a mock, stub, fake or patched name) checks only what the code "
    "under test does itself; a rule that another component enforces is tested where it lives - in that component's "
    "own test, or in a test that uses the real component."
)

FOR_A_FIXER = (
    "A failing test that expects a rule enforced by a component it replaces with a stand-in can never pass as "
    "written: move that check into the component's own test, or into a test without the stand-in, rather than "
    "changing the product or deleting the check."
)

__all__ = ["FOR_A_FIXER", "FOR_TEST_WRITERS"]
