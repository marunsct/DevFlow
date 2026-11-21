"""A Slim app that dies with "Could not detect any PSR-17 ResponseFactory" is given the autoloader rule as its cause.

Measured on one PHP run (39 repeats): the error killed every request and the product never started, though `slim/psr7`
was in `composer.json` and in `vendor/`; the fixers rewrote tests and routes, not the autoload set-up.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_a_missing_psr17_factory_is_given_its_cause(tmp_path):
    contract.write(tmp_path, pack_named("php-slim-api"), "notes-api", "Notes")
    said = ("PHP Fatal error:  Uncaught RuntimeException: Could not detect any PSR-17 ResponseFactory implementations. "
            "Please install a supported implementation in order to use `AppFactory::create()`.")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it answers", actual_behavior=said, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "dump-autoload" in defect.actual_behavior
