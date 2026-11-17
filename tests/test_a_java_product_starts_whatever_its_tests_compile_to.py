"""A Java product is built and started without compiling its tests.

Measured on one Java run: a unit test named a class that did not exist; `start.sh` ran `mvn -DskipTests package`,
which still compiles the tests, so the product never started - every acceptance and hidden test failed (hidden 0 of
9) on a product whose own code compiled. The unit command still compiles and runs the tests, so a broken test is
still a failing unit run.
"""

from __future__ import annotations

from app.stacks import pack_named

SKIPS_COMPILING = "-Dmaven.test.skip=true"


def test_the_start_the_install_and_the_release_image_build_without_the_tests():
    pack = pack_named("java-spring-api")
    commands = pack.commands("notes-api")
    assert all(SKIPS_COMPILING in argv for argv in commands["install"] if argv[0] == "mvn")
    start = pack.render("notes-api", "Notes")["start.sh"]
    assert SKIPS_COMPILING in start and "-DskipTests" not in start
    assert f"mvn -q -B {SKIPS_COMPILING} package" in pack.release_files["Dockerfile"]


def test_the_unit_command_still_compiles_and_runs_the_tests():
    commands = pack_named("java-spring-api").commands("notes-api")
    assert commands["unit_test"] == ["mvn", "-q", "-B", "test"]
