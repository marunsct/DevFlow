"""A product that fails at start is not given, as its cause, a unit test that its start never compiles (LF.1611).

Measured on one Java run: the service failed at start (a duplicate bean, then a missing one), and a unit test's
import the compiler rejected was folded into the one start defect, with its test file as that defect's file. Five of
six rounds of fixes rewrote the test - which the start's build skips - and three were reverted for it, while the
causes were in product files no fix was given.
"""
from __future__ import annotations

from app.agents.specialists import ReportedDefect
from app.graph import start_first
from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

TEST_FILE = "notes-api/src/test/java/app/notes_api/NoteControllerTest.java"

#: The start's output as the run's fix requests carried it (the duplicate bean).
STARTED = (
    "The product did not start for the acceptance suite: no test could reach it. Its output:\n"
    "ERROR 29 --- [main] o.s.boot.SpringApplication : Application run failed\n"
    "org.springframework.beans.factory.BeanDefinitionStoreException: Failed to parse configuration class "
    "[app.notes_api.Application]\n"
    "\tat app.notes_api.Application.main(Application.java:9) ~[!/:0.1.0]\n"
    "Caused by: org.springframework.context.annotation.ConflictingBeanDefinitionException: Annotation-specified bean "
    "name 'healthController' for bean class [app.notes_api.controller.HealthController] conflicts with existing, "
    "non-compatible bean definition of same name and class [app.notes_api.HealthController]"
)


def _reported(description, *, kind="", source="", files=(), actual="it fails"):
    return ReportedDefect(description=description, severity="major", reproduction_steps="sh start.sh",
                          expected_behavior="it starts", actual_behavior=actual, affected_files=list(files),
                          owner="backend", kind=kind, source=source)


def _the_test_s_import():
    return _reported(
        f"{TEST_FILE} line 26: package org.springframework.test.context.bean.override.mockito does not exist - this "
        "fails when the code runs.", kind="compile_error", source="language service", files=[TEST_FILE])


def test_a_unit_test_the_start_s_output_never_names_stays_its_own_finding():
    start = _reported(THE_PRODUCT_DOES_NOT_START, kind="start_failure", actual=STARTED)

    after = start_first.folded([start, _the_test_s_import()])

    assert len(after) == 2
    assert TEST_FILE not in after[0].affected_files
    assert "bean.override.mockito" not in after[0].actual_behavior
    assert after[1].affected_files == [TEST_FILE]


def test_a_unit_test_the_build_fails_on_is_still_folded_into_the_start():
    """A build that compiles its tests names the test file it fails on: that finding is why it does not start."""
    built = ("The product did not start. Its output:\n"
             "src/app.test.ts(3,5): error TS2304: Cannot find name 'describe'.")
    start = _reported(THE_PRODUCT_DOES_NOT_START, kind="start_failure", actual=built)
    finding = _reported("src/app.test.ts line 3: Cannot find name 'describe'.", kind="compile_error",
                        source="language service", files=["src/app.test.ts"])

    (merged,) = start_first.folded([start, finding])

    assert merged.affected_files == ["src/app.test.ts"]


def test_a_product_file_s_finding_is_folded_whatever_the_start_printed():
    start = _reported(THE_PRODUCT_DOES_NOT_START, kind="start_failure", actual=STARTED)
    finding = _reported("notes-api/src/main/java/app/notes_api/controller/NoteController.java line 41: cannot find "
                        "symbol (symbol: method setId(java.lang.Long))", kind="compile_error",
                        source="language service",
                        files=["notes-api/src/main/java/app/notes_api/controller/NoteController.java"])

    (merged,) = start_first.folded([start, finding])

    assert "setId" in merged.actual_behavior
