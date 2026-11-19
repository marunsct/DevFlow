"""A Slim 4 middleware written with Slim 3's callable handler is given its cause.

Measured on one PHP run: every request failed with "Argument #2 ($handler) must be of type callable,
Psr\\Http\\Server\\RequestHandlerInterface@anonymous given", the product never answered its readiness route, and the
first fix rewrote the entry file unchanged.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_the_slim_4_handler_shape_is_named(tmp_path):
    contract.write(tmp_path, pack_named("php-slim-api"), "notes-api", "Notes")
    said = ("[WebServer] PHP Fatal error:  Uncaught TypeError: {closure:bootstrap_app():35}(): Argument #2 ($handler) "
            "must be of type callable, Psr\\Http\\Server\\RequestHandlerInterface@anonymous given, called in "
            "/workspace/notes-api/vendor/slim/slim/Slim/MiddlewareDispatcher.php")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it answers", actual_behavior=said, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "$handler->handle($request)" in defect.actual_behavior
