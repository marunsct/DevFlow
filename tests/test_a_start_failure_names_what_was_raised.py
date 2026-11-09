"""A fix reverted because the product stopped starting names the error raised, not only the server's first frames.

Measured on a run whose fixes kept stopping the service: the revert kept the first 400 characters of the failure -
the server's frames down to the framework's `add_route` - so no fixer read the error the framework raised.
"""
from __future__ import annotations

from app.graph.engineering import the_start_and_end_of


def test_the_raised_error_at_the_end_is_kept():
    frames = " ".join(f'File "/x/site-packages/server/m{n}.py", line {n}, in run' for n in range(60))
    problem = ("The product did not start for the acceptance suite: no test could reach it. Its output: " + frames
               + " TypeError: responder must be a coroutine function")
    said = the_start_and_end_of(problem)
    assert said.startswith("The product did not start")
    assert said.endswith("TypeError: responder must be a coroutine function")
    assert len(said) <= 600


def test_a_short_failure_is_unchanged():
    assert the_start_and_end_of("The build failed:\n  missing  module") == "The build failed: missing module"
