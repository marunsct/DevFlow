"""A brief's rule on dependencies concerns the product, not the test tool, and the tool has to land where it can run.

Measured on one run on a brief with no dependencies and no pack: `pip install pytest`, a virtualenv's pip and
`python3 -m ensurepip` were refused about seven times, and QA wrote its own wrapper to locate a runner.
"""
from __future__ import annotations

import re

import pytest

from app.tools.repository import PROJECT_MARKER
from app.tools.sandbox import _refuse_an_install_the_brief_rules_out as refuse, _the_project_virtualenv


@pytest.fixture
def forbidding(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text("# Constraints\n\n- No external dependencies\n")
    return tmp_path


def _a_virtualenv(root):
    (root / PROJECT_MARKER).write_text("product", encoding="utf-8")
    bin_directory = root / "product" / ".venv" / "bin"
    bin_directory.mkdir(parents=True)
    (bin_directory / "python").write_text("", encoding="utf-8")
    return bin_directory


@pytest.mark.parametrize("command", [
    [".venv/bin/pip", "install", "pytest"],
    ["product/.venv/bin/pip3", "install", "pytest-cov", "coverage"],
    [".venv/bin/python", "-m", "pip", "install", "pytest==8.3.4"],
    [".venv/bin/pip", "install", "hypothesis", "pytest[testing]"],
])
def test_a_test_tool_into_the_workspace_s_virtualenv_is_allowed(forbidding, command):
    assert refuse(command, str(forbidding)) == ""


@pytest.mark.parametrize("command", [["pip", "install", "pytest"], ["python3", "-m", "pip", "install", "pytest"]])
def test_a_pip_nothing_finds_the_install_of_says_how_instead_of_blaming_the_brief(forbidding, command):
    answer = refuse(command, str(forbidding))
    assert "the brief rules" not in answer
    assert "`python3 -m venv .venv`" in answer and "`.venv/bin/pip install pytest`" in answer
    assert "`.venv/bin/pytest`" in answer


def test_with_a_virtualenv_there_the_bare_pip_is_its_own_and_runs(forbidding):
    _a_virtualenv(forbidding)
    assert refuse(["pip", "install", "pytest"], str(forbidding)) == ""


@pytest.mark.parametrize("command", [
    [".venv/bin/pip", "install", "flask"],
    [".venv/bin/pip", "install", "pytest", "flask"],
    ["pip", "install", "pytest-but-really-a-library", "requests"],
    [".venv/bin/pip", "install", "coverage-shipped"],
])
def test_anything_the_product_could_import_is_still_refused(forbidding, command):
    assert "the brief rules" in refuse(command, str(forbidding))


def test_a_project_with_no_contract_finds_its_virtualenv_from_the_pinned_directory(tmp_path):
    bin_directory = _a_virtualenv(tmp_path)
    assert _the_project_virtualenv(str(tmp_path)) == str(bin_directory)


def test_no_project_and_no_virtualenv_claim_nothing(tmp_path):
    assert _the_project_virtualenv(str(tmp_path)) is None


def test_the_answer_presupposes_no_kind_of_product(forbidding):
    words = re.findall(r"[a-z-]+", refuse(["pip", "install", "pytest"], str(forbidding)).lower())
    assert not {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"} & set(words)
