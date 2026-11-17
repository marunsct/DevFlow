"""A toolchain that fetches what it needs at its first test run is warmed up with the network before tests run without it.

Measured on one run with each command in a container of its own: Maven's test runner fetches its JUnit provider the
first time a test runs, not at the install; tests run with no network there, so the scaffold's own smoke test failed
twice ("report missing") and the run ended at its scaffold. The pack names a warm-up, run with the network once the
tests exist - at the scaffold and after a changed manifest is installed again - whose failure is ignored.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.stacks import contract, pack_named
from app.stacks.scaffold import scaffold

PASSED = "<testsuites><testcase name='smoke'/></testsuites>"


def _runner(root: Path, pack, seen: list, warm_up_fails: bool = False):
    def run(argv, category, working_directory):
        commands = pack.commands(working_directory)
        smoke = all((root / working_directory / path).exists() for path in pack.rendered_smoke_files(working_directory, "T"))
        seen.append((list(argv), category, smoke))
        if list(argv) in commands.get("warm_up", []):
            return {"returncode": "1" if warm_up_fails else "0", "stdout": "", "stderr": ""}
        if category != "test":
            return {"returncode": "0", "stdout": "", "stderr": ""}
        unit = list(argv) == commands["unit_test"]
        target = root / working_directory / (pack.unit_report if unit else pack.acceptance_report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(PASSED)
        return {"returncode": "0", "stdout": "", "stderr": ""}

    return run


def test_the_maven_pack_runs_its_tests_once_with_the_network_failures_ignored():
    warm = pack_named("java-spring-api").commands("notes")["warm_up"]
    assert warm == [["mvn", "-q", "-B", "-Dmaven.test.failure.ignore=true", "test"]]
    # A pack whose install fetches everything names none, and its commands are as they were.
    assert "warm_up" not in pack_named("python-http-api").commands("notes")


@pytest.mark.parametrize("warm_up_fails", [False, True])
def test_with_tests_offline_the_scaffold_warms_up_after_the_smoke_tests_exist_and_before_they_run(
        tmp_path, monkeypatch, warm_up_fails):
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    pack = pack_named("java-spring-api")
    seen: list = []

    result = scaffold(tmp_path, pack, "notes", "Notes", run=_runner(tmp_path, pack, seen, warm_up_fails))

    assert result.ok, result.problem  # a failed warm-up is ignored: the tests say what they lack
    warm = pack.commands("notes")["warm_up"][0]
    index = [argv for argv, _, _ in seen].index(warm)
    assert seen[index][1:] == ("install", True)  # with the network, the smoke tests written
    assert [category for _, category, _ in seen[index + 1:]][:1] == ["test"]
    assert all(category == "install" for _, category, _ in seen[:index])


def test_where_tests_have_the_network_there_is_nothing_to_warm(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    pack = pack_named("java-spring-api")
    seen: list = []

    assert scaffold(tmp_path, pack, "notes", "Notes", run=_runner(tmp_path, pack, seen)).ok
    assert pack.commands("notes")["warm_up"][0] not in [argv for argv, _, _ in seen]


def test_a_changed_manifest_installed_again_is_warmed_up_again(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    pack = pack_named("java-spring-api")
    seen: list = []
    assert scaffold(tmp_path, pack, "notes", "Notes", run=_runner(tmp_path, pack, seen)).ok
    pom = tmp_path / "notes" / "pom.xml"
    pom.write_text(pom.read_text() + "\n<!-- a dependency added -->\n")
    seen.clear()

    said = contract.install_if_the_manifests_changed(tmp_path, runner=_runner(tmp_path, pack, seen))

    assert said and "installed again" in said[0]
    calls = [(argv, category) for argv, category, _ in seen]
    assert calls[-1] == (pack.commands("notes")["warm_up"][0], "install")
    assert json.loads(json.dumps(contract.read(tmp_path)["warm_up"])) == pack.commands("notes")["warm_up"]
