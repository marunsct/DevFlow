"""A pack's `start.sh` is the harness's, runs by its name, and a stage cannot replace it with a command that only works in a test run.

Measured: a locked criterion asked that the project have a `start.sh` that starts the service. The pack's script had no
execute bit, a fixer rewrote it (`python3 -m uvicorn ...` for `.venv/bin/python -m uvicorn ...`, and no `cd`), the
locked suite passed because it runs inside the project's virtual environment, and the hidden tests, which start the
script from outside it, failed all nine: hidden 0 of 9 on a product that had scored 9 of 9.
"""
from __future__ import annotations

import os

import pytest

from app.stacks import contract, pack_named
from app.stacks.scaffold import make_a_script_executable


@pytest.mark.parametrize("name", ["python-http-api", "python-flask-api"])
def test_the_pack_keeps_its_start_script(name):
    pack = pack_named(name)
    assert "start.sh" in pack.kept_files
    assert pack.files["start.sh"].startswith("#!") and ".venv/bin/python" in pack.files["start.sh"]


def test_a_start_script_a_stage_replaced_is_put_back(tmp_path):
    pack = pack_named("python-http-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    project.mkdir()
    rendered = pack.render("notes", "Notes", None)
    for relative in pack.kept_files:
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered[relative], encoding="utf-8")
    (project / "start.sh").write_text("#!/usr/bin/env sh\nexec python3 -m uvicorn notes_api.main:app\n")

    repairs = contract.enforce(tmp_path)

    assert (project / "start.sh").read_text() == rendered["start.sh"]
    assert any("start.sh" in line for line in repairs)


def test_a_script_the_pack_writes_can_be_run_by_its_name(tmp_path):
    script = tmp_path / "start.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(0o644)

    make_a_script_executable(script, "#!/bin/sh\necho hi\n")

    assert os.access(script, os.X_OK)


def test_a_file_that_is_not_a_script_is_left_alone(tmp_path):
    data = tmp_path / "pytest.ini"
    data.write_text("[pytest]\n")
    data.chmod(0o644)

    make_a_script_executable(data, "[pytest]\n")

    assert not os.access(data, os.X_OK)
