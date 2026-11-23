"""Slim's uncaught not-found fatal error and Go's `undefined:` are given the rule that explains them.

Measured on two PHP runs: the readiness route died with `Uncaught Slim\\Exception\\HttpNotFoundException: Not found` 64 and
81 times and the fixers rewrote the tests and the container set-up. Measured on one Go run: `undefined: json`,
`undefined: strings` and `undefined: strconv` 174 times, in files that used a standard package they did not import.
"""
from __future__ import annotations

import re

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def _defect(tmp_path, pack: str, said: str):
    contract.write(tmp_path, pack_named(pack), "notes-api", "Notes")
    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it answers", actual_behavior=said, affected_files=[],
        owner="backend")])
    return defect.actual_behavior


def test_a_slim_route_not_found_is_given_the_error_middleware_rule(tmp_path):
    said = ("[WebServer] PHP Fatal error:  Uncaught Slim\\Exception\\HttpNotFoundException: Not found. in "
            "/workspace/notes-api/vendor/slim/slim/Slim/Middleware/RoutingMiddleware.php:76")

    behaviour = _defect(tmp_path, "php-slim-api", said)

    assert KNOWN_CAUSE in behaviour and "addErrorMiddleware" in behaviour and "is registered" in behaviour


def test_a_go_undefined_name_is_given_the_import_rule(tmp_path):
    said = "notes-api/server.go line 41: undefined: json"

    behaviour = _defect(tmp_path, "go-http-api", said)

    assert KNOWN_CAUSE in behaviour and "import block" in behaviour and "encoding/json" in behaviour


def test_a_slim_error_page_from_an_unvalidated_body_is_given_the_validation_rule(tmp_path):
    """Measured on one PHP run: a blank or numeric title answered 500 with Slim's HTML error page for two attempts."""
    behaviour = _defect(tmp_path, "php-slim-api", "Requests at the edges of the interface contract are not handled: "
                     "`POST /notes` with `title` only spaces answered 500 (it said: an HTML page, \"Slim Application "
                     "Error\")")

    assert KNOWN_CAUSE in behaviour
    assert "not blank after `trim()`" in behaviour and "`InvalidArgumentException`" in behaviour
    assert not re.search(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", behaviour, re.I)
