"""An install fetches only packages its registry has, and none first published days ago (deep review 2026-11-18, E2).

Found in the deep review: an install ran with a network and `install_egress` checked only the hosts it named; nothing
checked that a package an open model named exists, or that it was not registered days ago under a name models invent.
Now each package an install would fetch - named on its command line or declared in its manager's manifest - is looked
up in its registry first; a missing or days-old one is refused before anything runs, and a registry that cannot be
reached lets the install through with the verdict recorded. Optionally (`INSTALL_SCRIPTS_SKIPPED`, off) an install runs
with its dependencies' install scripts switched off, by each manager's own flag.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.tools import dependency_gate, sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
LONG_AGO = "2015-03-01T10:00:00.000Z"


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


class _Registry:
    """The registries, stood in for: `npm` and `pypi` packages by name, with the date each first appeared."""

    def __init__(self, npm: dict[str, str] | None = None, pypi: dict[str, str] | None = None, down: bool = False):
        self.npm, self.pypi, self.down = npm or {}, pypi or {}, down

    def fetch(self, url: str, most_bytes: int = 0) -> tuple[int, bytes]:
        if self.down:
            raise OSError("no route to the registry")
        found = re.match(r"^https://registry\.npmjs\.org/(.+?)(/latest)?$", url)
        if found and found.group(1) in self.npm:
            if found.group(2):
                return 200, json.dumps({"version": "1.0.0"}).encode()
            return 200, json.dumps({"time": {"created": self.npm[found.group(1)]}}).encode()
        found = re.match(r"^https://pypi\.org/pypi/(.+)/json$", url)
        if found and found.group(1) in self.pypi:
            return 200, json.dumps({"info": {"version": "1.0"}, "releases": {
                "1.0": [{"upload_time_iso_8601": self.pypi[found.group(1)]}]}}).encode()
        return 404, b"{}"


class _Done:
    stdout, stderr, returncode = "added 1 package", "", 0


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Container mode with the gate on: returns (install, containers) - run a command, and every `docker run` made."""
    containers: list[list[str]] = []

    def run(argv, *args, **kwargs):
        if Path(str(argv[0])).name == "docker" and argv[1:2] == ["run"]:
            containers.append([str(part) for part in argv])
        return _Done()

    monkeypatch.setenv("DEPENDENCY_GATE", "on")
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.delenv("INSTALL_SCRIPTS_SKIPPED", raising=False)
    monkeypatch.setattr("shutil.which", lambda name, *a, **k: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr("subprocess.run", run)
    dependency_gate._VERDICTS.clear()
    dependency_gate._UNREACHABLE.clear()

    def install(registry: _Registry, *command: str) -> dict:
        from app.tools import package_registry

        package_registry._CACHE.clear()
        monkeypatch.setattr(package_registry, "_fetch", registry.fetch)
        return sandbox.SandboxExecutor.execute(list(command), repo_root=str(tmp_path), role_name="backend_specialist")

    return install, containers


def test_a_package_its_registry_does_not_have_is_not_installed(world, tmp_path):
    install, containers = world

    outcome = install(_Registry(npm={"express": LONG_AGO}), "npm", "install", "express", "express-session-helperz")

    assert containers == []
    assert "`express-session-helperz`" in outcome["error"] and "has no package" in outcome["error"]
    assert "`express`" not in outcome["error"]
    assert not BANNED.search(outcome["error"])


def test_a_package_first_published_days_ago_is_not_installed(world):
    install, containers = world

    outcome = install(_Registry(pypi={"fastapi-auth-easy": _days_ago(3)}), "pip", "install", "fastapi-auth-easy==0.1")

    assert containers == []
    assert "`fastapi-auth-easy`" in outcome["error"] and "3 days ago" in outcome["error"]


def test_a_dependency_a_manifest_declares_is_looked_up_before_its_install(world, tmp_path):
    install, containers = world
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"express": "^4.19.0", "local-thing": "file:../local-thing"},
        "devDependencies": {"jest-mock-fetchify": "^1.0.0"},
    }))

    outcome = install(_Registry(npm={"express": LONG_AGO}), "npm", "install")

    assert containers == []
    assert "`jest-mock-fetchify` (package.json)" in outcome["error"]
    assert "local-thing" not in outcome["error"]


def test_packages_long_established_are_installed_and_the_verdicts_kept(world, tmp_path):
    install, containers = world
    (tmp_path / "requirements.txt").write_text("fastapi>=0.110\nuvicorn[standard]==0.30.0  # the server\n-e .\n")

    outcome = install(_Registry(pypi={"fastapi": LONG_AGO, "uvicorn": LONG_AGO}), "pip", "install", "-r", "requirements.txt")

    assert "error" not in outcome and len(containers) == 1
    kept = json.loads((tmp_path / dependency_gate.RECORD).read_text())
    assert {kept["pypi:fastapi"]["verdict"], kept["pypi:uvicorn"]["verdict"]} == {"allowed"}


def test_a_registry_that_cannot_be_reached_lets_the_install_through_and_says_so_in_the_record(world, tmp_path):
    install, containers = world

    outcome = install(_Registry(down=True), "npm", "install", "left-pad")

    assert "error" not in outcome and len(containers) == 1
    assert json.loads((tmp_path / dependency_gate.RECORD).read_text())["npm:left-pad"]["verdict"] == "unverified"


def test_a_value_given_to_an_option_is_not_taken_for_a_package(world):
    install, containers = world

    install(_Registry(npm={"typescript": LONG_AGO}), "npm", "install", "--save-prefix", "~", "typescript@5")

    assert len(containers) == 1


@pytest.mark.parametrize("switch, expected", [("on", True), ("off", False)])
def test_dependencies_install_scripts_are_switched_off_only_when_asked(world, monkeypatch, switch, expected):
    install, containers = world
    monkeypatch.setenv("INSTALL_SCRIPTS_SKIPPED", switch)

    install(_Registry(npm={"express": LONG_AGO}), "npm", "install", "express")

    assert ("--ignore-scripts" in containers[0]) is expected


def test_a_manager_with_no_flag_for_it_runs_its_install_as_it_was(world, monkeypatch):
    install, containers = world
    monkeypatch.setenv("INSTALL_SCRIPTS_SKIPPED", "on")

    install(_Registry(pypi={"fastapi": LONG_AGO}), "pip", "install", "fastapi")

    assert containers[0][-3:] == ["pip", "install", "fastapi"]
