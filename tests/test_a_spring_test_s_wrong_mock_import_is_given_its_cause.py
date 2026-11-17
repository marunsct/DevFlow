"""A Spring Boot test importing `MockBean` from a package that does not exist is given where it lives.

Measured on one run: a controller test imported `org.springframework.boot.test.mock.bean.MockBean`, the compiler said
the package does not exist, and the first fix left it so.
"""
from __future__ import annotations

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
