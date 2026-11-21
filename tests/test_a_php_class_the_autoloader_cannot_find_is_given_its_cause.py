"""A PHP service that dies with `Class "..." not found` is given the autoloader's rule as its cause.

Measured on one PHP run: the service used a namespace `composer.json` did not map, every request died with that error,
and three rounds of fixes rewrote the entry file and the tests, not the namespace or the autoload map.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_a_class_the_autoloader_cannot_find_is_given_the_mapping_rule(tmp_path):
    contract.write(tmp_path, pack_named("php-slim-api"), "notes-api", "Notes")
    said = ('[WebServer] PHP Fatal error:  Uncaught Error: Class "NotesApi\\SqliteNoteRepository" not found in '
            "/workspace/notes-api/src/Service.php:45")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it answers", actual_behavior=said, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior
    assert "psr-4" in defect.actual_behavior and "dump-autoload" in defect.actual_behavior
