"""A package declared only in a manifest the project's install never reads is undeclared.

Measured on a gate run: `bcrypt` was in `pyproject.toml`, the pack's install
read only `requirements.txt` and `requirements-dev.txt`, the check counted it
declared, and every clean install lacked it: the product did not start and the
unit tests could not import it.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.analysis import dependency_drift
from app.stacks import contract

PYPROJECT = '[project]\nname = "items-api"\ndependencies = ["flask>=3.1", "bcrypt"]\n'
REQUIREMENTS_INSTALL = [["python3", "-m", "venv", ".venv"],
                        [".venv/bin/python", "-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt"]]


def _project(tmp_path: Path, install) -> Path:
    project = tmp_path / "items-api"
    (project / "items_api").mkdir(parents=True)
    (project / "items_api" / "__init__.py").write_text("")
    (project / "items_api" / "auth.py").write_text("import bcrypt\nimport flask\n")
    (project / "requirements.txt").write_text("flask>=3.1\n")
    (project / "requirements-dev.txt").write_text("pytest\n")
    (project / "pyproject.toml").write_text(PYPROJECT)
    if install is not None:
        (tmp_path / contract.CONTRACT_FILE).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / contract.CONTRACT_FILE).write_text(json.dumps({"pack": "python-flask-api", "project": "items-api", "install": install}))
    return project


def _names(project: Path) -> list[str]:
    return [name for name, _, _ in dependency_drift.undeclared(project)]


def test_a_pyproject_the_install_never_reads_declares_nothing(tmp_path):
    assert _names(_project(tmp_path, REQUIREMENTS_INSTALL)) == ["bcrypt"]


def test_an_install_of_the_project_itself_reads_its_pyproject(tmp_path):
    install = [*REQUIREMENTS_INSTALL[:1], [".venv/bin/python", "-m", "pip", "install", "-e", ".", "-r", "requirements-dev.txt"]]
    assert _names(_project(tmp_path, install)) == []


def test_with_no_recorded_install_every_manifest_counts_as_before(tmp_path):
    assert _names(_project(tmp_path, None)) == []
