"""A Spring service that exits at start with "Unable to determine Dialect without JDBC metadata" is given its cause.

Measured on two Java runs: the start output carried that line, the fixers rewrote `pom.xml` and the controller three
rounds running, and the data folder and the SQLite dialect (the two causes) were never named.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_the_missing_dialect_is_given_its_causes(tmp_path):
    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes")
    said = ("[WebServer] Caused by: org.hibernate.HibernateException: Unable to determine Dialect without JDBC "
            "metadata (please set 'jakarta.persistence.jdbc.url' for common cases or 'hibernate.dialect' when a "
            "custom Dialect implementation must be provided)")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it answers", actual_behavior=said, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior
    assert "SQLiteDialect" in defect.actual_behavior and "DATA_DIR" in defect.actual_behavior
