"""A setup whose unit tests sit beside the code can declare so, as a pack can.

Measured on one run: the setup stage's write of the declaration was refused seven times, `unit_dir` as the project's own
name and then as `.`, each time because it "must be a path inside the project"; packs declare `.` and the harness reads
it. It wrote the file by a command in the end, the proof refused the same field, and the setup was left to the agents.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.stacks.custom_setup import problems_with, read_declaration

DECLARED = {
    "kind": "http_api",
    "install": [["pip", "install", "-e", "."]],
    "unit_test": ["python3", "-m", "pytest", "test_unit.py", "--junitxml=report-unit.xml"],
    "unit_report": "report-unit.xml",
    "unit_dir": ".",
    "unit_pattern": "test_unit*.py",
    "acceptance_test": ["python3", "-m", "pytest", "tests/acceptance", "--junitxml=report-acceptance.xml"],
    "acceptance_report": "report-acceptance.xml",
    "acceptance_dir": "tests/acceptance",
    "acceptance_pattern": "test_acceptance*.py",
    "kept_files": [],
    "smoke_files": ["test_unit.py", "tests/acceptance/test_acceptance.py"],
    "guide": "g",
    "acceptance_guide": "a",
}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    where = tmp_path / "the-product"
    (where / "tests" / "acceptance").mkdir(parents=True)
    (where / "test_unit.py").write_text("")
    (where / "tests" / "acceptance" / "test_acceptance.py").write_text("")
    return where


def _written(project: Path, **changed) -> str:
    return json.dumps({**DECLARED, **changed})


@pytest.mark.parametrize("spelling", [".", "./", "the-product", "the-product/"])
def test_the_project_itself_is_a_unit_directory_however_it_is_spelt(project, spelling):
    text = _written(project, unit_dir=spelling)
    assert problems_with(text, project) == ""
    (project / "stack-setup.json").write_text(text)
    declared, problem = read_declaration(project)
    assert problem == ""
    assert declared.unit_dir == "."


def test_a_unit_smoke_test_beside_the_code_is_where_its_runner_collects_it(project):
    # The harness's own check of a written setup read `.` as a folder no file is in.
    (project / "stack-setup.json").write_text(_written(project))
    assert read_declaration(project)[1] == ""


def test_one_that_does_not_match_the_unit_pattern_is_still_refused(project):
    (project / "other.py").write_text("")
    (project / "stack-setup.json").write_text(_written(project, smoke_files=["other.py", DECLARED["smoke_files"][1]]))
    assert "must sit in" in read_declaration(project)[1]


def test_an_acceptance_test_outside_its_folder_is_still_found_with_unit_tests_beside_the_code(project):
    (project / "test_acceptance_lost.py").write_text("")
    (project / "stack-setup.json").write_text(_written(project))
    assert "`test_acceptance_lost.py`" in read_declaration(project)[1]


def test_such_a_setup_is_proven_and_recorded_as_a_pack_with_tests_beside_the_code(project, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.stacks import contract
    from app.stacks.custom_setup import prove

    monkeypatch.setenv("PROVEN_SETUP_LIBRARY", str(tmp_path / "library"))
    passed = '<testsuite tests="1" failures="0" errors="0"><testcase name="t" classname="c"/></testsuite>'

    def run(argv, category, working_directory):
        if category == "test":
            (tmp_path / working_directory / argv[-1].removeprefix("--junitxml=")).write_text(passed)
        return {"returncode": "0"}

    (project / "stack-setup.json").write_text(_written(project, unit_dir="the-product/"))
    stack = SimpleNamespace(language="python", framework="", frontend_framework="", testing_framework="pytest")
    result = prove(tmp_path, project.name, stack, run=run)
    assert result.ok, result.problem
    assert contract.the_pack(tmp_path)[0].unit_dir == "."


def test_a_named_unit_directory_is_kept_as_it_was(project):
    (project / "tests" / "unit").mkdir()
    (project / "tests" / "unit" / "test_unit.py").write_text("")
    (project / "test_unit.py").unlink()
    (project / "stack-setup.json").write_text(
        _written(project, unit_dir="tests/unit", smoke_files=["tests/unit/test_unit.py", DECLARED["smoke_files"][1]])
    )
    declared, problem = read_declaration(project)
    assert problem == "" and declared.unit_dir == "tests/unit"


@pytest.mark.parametrize("spelling", [".", "the-product/"])
def test_acceptance_tests_still_need_a_folder_and_the_refusal_says_what_it_read(project, spelling):
    problem = problems_with(_written(project, acceptance_dir=spelling), project)
    assert "`acceptance_dir` names the project itself" in problem
    assert "a folder of their own" in problem
    assert "inside the project" not in problem


@pytest.mark.parametrize("field", ["unit_report", "acceptance_report"])
def test_a_report_still_has_to_be_a_file(project, field):
    assert f"`{field}`" in problems_with(_written(project, **{field: "."}), project)


@pytest.mark.parametrize("outside", ["../elsewhere", "/etc"])
def test_a_directory_outside_the_project_is_still_refused(project, outside):
    assert "`unit_dir` must be a path inside the project" in problems_with(_written(project, unit_dir=outside), project)
