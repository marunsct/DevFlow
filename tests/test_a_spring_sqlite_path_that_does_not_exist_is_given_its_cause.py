"""A Spring service on SQLite that answers 500 with `path to '...' does not exist` is given its cause.

Measured on two Java runs (7 and 9): every request answered 500 with that message; SQLite's driver creates the file and
not its folder, and the suite hands the service a fresh data folder that is not there yet.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_a_missing_data_folder_is_given_its_cause(tmp_path):
    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes")
    said = ("java.sql.SQLException: path to 'test-results/acceptance-data-39067/notes.db': "
            "'/workspace/notes-api/test-results/acceptance-data-39067' does not exist")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The server fails on a request it should answer or refuse.", severity="major",
        reproduction_steps="GET /notes", expected_behavior="200", actual_behavior=said, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "createDirectories" in defect.actual_behavior
