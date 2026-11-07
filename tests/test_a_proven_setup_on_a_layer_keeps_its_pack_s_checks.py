"""A setup proven on a pack's runner layer keeps that pack's checks (SF.1).

A proven setup's pack was built from its declaration alone: no test-bug patterns, no known errors, no release files,
no entrypoint - the blind derived pack behind LF.534, 537 and 552's false acceptances. A setup proven on a pack's
runner layer (SF.2) runs that pack's own runners, so it keeps everything of the pack but its framework's files.
"""
from __future__ import annotations

import json

from app.stacks import pack_named
from app.stacks.custom_setup import PROVEN_SETUP, pack_from, write_runner_layer


def _record(setup):
    return {"pack": PROVEN_SETUP, "project": "notes-api", "setup": setup}


SETUP = {
    "kind": "http_api", "language": "python", "stack_line": "Python, Falcon, pytest",
    "stack": {"language": "Python", "framework": "Falcon"},
    "install": [["python3", "-m", "venv", ".venv"]],
    "unit_test": [".venv/bin/python", "-m", "pytest", "tests"],
    "acceptance_test": [".venv/bin/python", "-m", "pytest", "acceptance"],
    "unit_report": "test-results/unit.xml", "acceptance_report": "test-results/acceptance.xml",
    "unit_dir": "tests", "acceptance_dir": "acceptance", "unit_pattern": "test_*.py", "acceptance_pattern": "test_*.py",
    "kept": {"pytest.ini": "", "acceptance/conftest.py": "base_url", "start.sh": "x"},
}


def test_a_setup_on_a_layer_keeps_the_layer_pack_s_checks():
    layer = pack_named("python-http-api")
    pack = pack_from(_record({**SETUP, "layer": "python-http-api"}))
    assert pack.name == PROVEN_SETUP
    assert pack.test_bugs == layer.test_bugs and pack.known_errors == layer.known_errors
    assert pack.release_files and pack.entrypoint == layer.entrypoint
    assert pack.stack["framework"] == "Falcon" and pack.frameworks == ()
    assert set(pack.files) == {"pytest.ini", "acceptance/conftest.py", "start.sh"}


def test_a_setup_with_no_layer_is_built_as_before():
    pack = pack_from(_record(SETUP))
    assert pack.test_bugs == () and not pack.release_files


def test_the_layer_s_declaration_names_its_pack(tmp_path):
    project = tmp_path / "notes-api"
    project.mkdir()
    write_runner_layer(project, pack_named("python-http-api"), "notes-api", "Notes")
    assert json.loads((project / "stack-setup.json").read_text())["layer"] == "python-http-api"
