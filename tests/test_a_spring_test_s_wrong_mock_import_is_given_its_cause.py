"""A Spring Boot test importing `MockBean` from a package that does not exist is given where it lives.

Measured on one run: a controller test imported `org.springframework.boot.test.mock.bean.MockBean`, the compiler said
the package does not exist, and the first fix left it so.
"""
from __future__ import annotations

import re

from app.agents.specialists import ReportedDefect
from app.stacks import contract, pack_named
from app.stacks.known_errors import KNOWN_CAUSE, with_known_causes


def test_the_wrong_package_is_given_the_real_one(tmp_path):
    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes")
    text = ("notes-api/src/test/java/app/notes_api/NotesControllerTest.java line 12: package "
            "org.springframework.boot.test.mock.bean does not exist")

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description=text, severity="major", reproduction_steps="mvn test-compile", expected_behavior="it compiles",
        actual_behavior=text, affected_files=[], owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "org.springframework.boot.test.mock.mockito" in defect.actual_behavior


def test_a_missing_validation_starter_is_named(tmp_path):
    """Measured on one run: the code used `jakarta.validation` and the pom had no validation starter."""
    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes")
    text = "notes-api/src/main/java/app/notes_api/NoteController.java line 3: package jakarta.validation does not exist"

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description=text, severity="major", reproduction_steps="mvn test-compile", expected_behavior="it compiles",
        actual_behavior=text, affected_files=[], owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "spring-boot-starter-validation" in defect.actual_behavior


def test_a_sqlite_setting_in_an_h2_url_is_named(tmp_path):
    """Measured on one run: "SQLite via H2's SQLite mode" was chosen (H2 has none), SQLite's busy timeout went into
    H2's URL, and the service exited at start for two attempts."""
    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes")
    text = ('The service exited with code 1 before answering. It printed: ERROR o.h.engine.jdbc.spi.SqlExceptionHelper'
            '   : Unsupported connection setting "BUSY_TIMEOUT" [90113-232]')

    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it starts", actual_behavior=text, affected_files=[],
        owner="backend")])

    assert KNOWN_CAUSE in defect.actual_behavior and "sqlite-jdbc" in defect.actual_behavior


BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The start's own words on the measured Java run (LF.1613): a hand-built Hibernate `SessionFactory` bean.
NO_ENTITY_MANAGER_FACTORY = (
    "The service exited with code 1 before answering. It printed:\n"
    "APPLICATION FAILED TO START\n\nDescription:\n\n"
    "Parameter 0 of constructor in app.notes_api.service.NoteService required a bean named 'entityManagerFactory' "
    "that could not be found.\n\nAction:\n\nConsider defining a bean named 'entityManagerFactory' in your "
    "configuration.")


def _the_start_defect(tmp_path, actual):
    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes")
    (defect,) = with_known_causes(tmp_path, [ReportedDefect(
        description="The product does not start for the acceptance suite.", severity="major",
        reproduction_steps="sh start.sh", expected_behavior="it starts", actual_behavior=actual, affected_files=[],
        owner="backend")])
    return defect


def test_a_missing_entity_manager_factory_is_traced_to_a_hand_built_session_factory(tmp_path):
    """Measured on one run: the specification asked for a configuration class building a `SessionFactory` bean, Boot
    then built no `entityManagerFactory`, and the service exited at start for the sprint's last round."""
    defect = _the_start_defect(tmp_path, NO_ENTITY_MANAGER_FACTORY)

    cause = defect.actual_behavior.partition(KNOWN_CAUSE)[2]
    assert "SessionFactory" in cause and "@Bean" in cause
    assert "journal_mode=WAL" in cause, "where SQLite's settings go instead"
    assert not BANNED.search(cause)


def test_mockito_bean_under_a_spring_boot_before_3_4_is_given_the_annotation_that_exists(tmp_path):
    """Measured on one run: the parent was Spring Boot 3.2.5, a test used `@MockitoBean` (from 3.4 on), and each fix
    swapped it for a package that does not exist either."""
    text = ("notes-api/src/test/java/app/notes_api/NoteControllerTest.java line 26: package "
            "org.springframework.test.context.bean.override.mockito does not exist")
    defect = _the_start_defect(tmp_path, text)

    cause = defect.actual_behavior.partition(KNOWN_CAUSE)[2]
    assert "org.springframework.boot.test.mock.mockito" in cause and "3.4" in cause
    assert not BANNED.search(cause)
