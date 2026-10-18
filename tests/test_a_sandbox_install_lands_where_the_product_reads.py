"""A sandbox install lands where the product's own commands read.

The environment contract tells every stage that installs must land in the
interpreter environment the product's commands use - and then the sandbox
contradicted it: a Python pack runs everything through `.venv/bin/python`,
while a bare `pip install` in a sandbox command landed in the system
environment the served app never reads. Instructing and then punishing
(monitoring-handover §6.2). The project's virtualenv now goes in front of
every sandbox command's PATH, so `pip`, `python` and `pytest` are the
virtualenv's and an install is visible to the acceptance server the moment
it lands (Initiative K.5).
"""

from __future__ import annotations

import os
from pathlib import Path

from app.stacks import contract, pack_named
from app.tools.sandbox import _child_environment, _the_project_virtualenv


def _a_python_workspace(tmp_path: Path) -> Path:
    pack = pack_named("python-http-api")
    assert pack is not None
    contract.write(tmp_path, pack, "notes-app", "Notes", "notes_app")
    venv_bin = tmp_path / "notes-app" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (venv_bin / "python").chmod(0o755)
    return tmp_path


def test_the_project_virtualenv_is_found(tmp_path: Path) -> None:
    workspace = _a_python_workspace(tmp_path)

    found = _the_project_virtualenv(str(workspace))

    assert found == str(workspace / "notes-app" / ".venv" / "bin")


def test_without_a_virtualenv_or_a_contract_nothing_is_claimed(tmp_path: Path) -> None:
    workspace = _a_python_workspace(tmp_path)
    (workspace / "notes-app" / ".venv" / "bin" / "python").unlink()
    assert _the_project_virtualenv(str(workspace)) is None

    bare = tmp_path / "bare"
    bare.mkdir()
    assert _the_project_virtualenv(str(bare)) is None


def test_every_sandbox_command_puts_the_virtualenv_first(tmp_path: Path) -> None:
    workspace = _a_python_workspace(tmp_path)

    environment = _child_environment(str(workspace), None)

    first = environment["PATH"].split(os.pathsep)[0]
    assert first == str(workspace / "notes-app" / ".venv" / "bin")


def test_a_workspace_without_a_virtualenv_keeps_its_path(tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()

    environment = _child_environment(str(bare), None)

    # Nothing of this workspace is prepended: no virtualenv, no claim.
    # (The inherited PATH may mention other virtualenvs - the host's own.)
    assert str(bare) not in environment["PATH"]


def test_a_tool_in_the_project_virtualenv_is_found_by_its_bare_name(tmp_path: Path, monkeypatch) -> None:
    """`pytest` in `.venv/bin` was answered "not installed in this environment" five
    times while the command, with the virtualenv on its PATH, would have found it."""
    from app.tools.sandbox import SandboxExecutor

    root = _a_python_workspace(tmp_path)
    tool = root / "notes-app" / ".venv" / "bin" / "pytest"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    found = SandboxExecutor._resolve_executable("pytest", str(root))

    assert found == str(tool)
