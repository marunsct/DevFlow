"""Tests that acceptance review includes pre-emptive checks for tests that need what they never made.

Pre-emptive linting must catch unpassable acceptance tests before locking the suite,
avoiding expensive dispute cycles during implementation.
"""

from __future__ import annotations

import inspect
from app.graph import acceptance_nodes


def test_acceptance_review_calls_tests_that_need_what_they_never_made() -> None:
    source = inspect.getsource(acceptance_nodes.acceptance_review)
    assert "tests_that_need_what_they_never_made" in source, (
        "acceptance_review must check for tests that need what they never made before locking"
    )

