"""A toolchain that fetches while it builds and tests is given the network for those commands too.

Measured on one Java run with each command in a container of its own: a fixer changed the Spring Boot version, the
reinstall stopped at a compile error before Maven reached its test plugin, and every later offline build and test -
the product's own start among them - failed on "Unknown host repo.maven.apache.org": no acceptance test reached the
product, and each defect said "the product does not start" for a cause no fixer could change.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

from app.stacks import contract, pack_named
from app.tools import sandbox
from app.tools.sandbox import SandboxExecutor


def _the_network(monkeypatch, root, argv, category):
    captured = {}

    class _Result:
        stdout, stderr, returncode = "", "", 0

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", lambda cmd, **_k: (captured.update(cmd=cmd), _Result())[1])
    with mock.patch.dict(os.environ, {"ALLOW_COMMAND_EXECUTION": "true", "SANDBOX_EXECUTION_MODE": "container"}):
        SandboxExecutor.execute(argv, repo_root=str(root), role_name="testing_specialist", category=category)
    return captured["cmd"][captured["cmd"].index("--network") + 1]


@pytest.mark.parametrize("category", ["test", "build", "default"])
def test_a_maven_project_s_builds_and_tests_reach_the_registry(monkeypatch, tmp_path, category):
    contract.write(tmp_path, pack_named("java-spring-api"), "notes-api", "Notes")
    (tmp_path / "notes-api").mkdir(exist_ok=True)
    sandbox.pin_project_stack(tmp_path, "java")
    assert _the_network(monkeypatch, tmp_path, ["mvn", "-q", "-B", "test"], category) == "bridge"


def test_a_project_whose_install_fetches_everything_tests_offline(monkeypatch, tmp_path):
    contract.write(tmp_path, pack_named("python-http-api"), "notes-api", "Notes")
    (tmp_path / "notes-api").mkdir(exist_ok=True)
    assert _the_network(monkeypatch, tmp_path, ["pytest"], "test") == "none"
    assert _the_network(monkeypatch, tmp_path, ["pip", "install", "-r", "requirements.txt"], "install") == "bridge"


def test_without_a_pack_a_test_stays_offline(tmp_path):
    assert sandbox._a_network_for("test", tmp_path) == "none"
    assert sandbox._a_network_for("install", tmp_path) == "bridge"
