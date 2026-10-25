"""A service pack writes its own `start.sh` and keeps it, so a stage cannot start the service with a module that never listens.

Measured on a small-model run: the team wrote `start.sh` running the module that defines the application (it exports
`createApp` and listens on nothing). The suite runs the project's `start.sh` when there is one, so the web server timed
out and no test ran, for five QA rounds.
"""
from __future__ import annotations

import pytest

from app.stacks import contract, pack_named


@pytest.mark.parametrize("name,command", [
    ("node-hono-api", "exec node dist/main.js"),
    ("node-hono-native-api", "exec node src/main.ts"),
    ("go-http-api", "exec ./bin/server"),
])
def test_the_pack_writes_a_start_script_from_its_own_start_command(name, command):
    pack = pack_named(name)
    assert "start.sh" in pack.kept_files
    script = pack.files["start.sh"]
    assert script.startswith("#!/bin/sh\n") and command in script


def test_a_start_script_that_runs_the_wrong_module_is_put_back(tmp_path):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    project.mkdir()
    (project / "start.sh").write_text("#!/usr/bin/env bash\nnode src/app.ts\n")

    repairs = contract.enforce(tmp_path)

    assert "exec node src/main.ts" in (project / "start.sh").read_text()
    assert any("start.sh" in line for line in repairs)
