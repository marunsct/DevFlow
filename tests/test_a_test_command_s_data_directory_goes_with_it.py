"""The fresh data directory a test command is given is removed when the command ends.

Found in review: `_a_fresh_data_directory` made a new `unit-data-*`
directory under the project's `test-results/` for every test command of a
product that keeps data, and nothing removed one. A run's workspace gathered
a directory per test run, each holding whatever the product's tests wrote -
on the run that motivated the fresh directory, a data file of 205 MB.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.stacks import contract, pack_named
from app.tools import sandbox


@pytest.fixture
def product(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    return tmp_path


def _a_command_that_writes_data(monkeypatch, given: dict, then=None):
    def run(argv, **kwargs):
        data = Path(kwargs["env"]["DATA_DIR"])
        (data / "notes.json").write_text("x" * 1000)
        given["data"] = data
        if then is not None:
            raise then
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(sandbox, "_run_and_watch_the_tree", run)
    monkeypatch.setattr(sandbox.SandboxExecutor, "_resolve_executable", staticmethod(lambda name, *a, **k: "/usr/bin/" + name))


def test_the_directory_is_gone_once_the_command_has_run(product, monkeypatch):
    given: dict = {}
    _a_command_that_writes_data(monkeypatch, given)

    outcome = sandbox.SandboxExecutor._execute_here(["node", "--test"], str(product), "testing_specialist", "test", 30, None)

    assert outcome["returncode"] == "0"
    assert given["data"].name.startswith("unit-data-") and not given["data"].exists()


def test_the_directory_is_gone_when_the_command_timed_out(product, monkeypatch):
    given: dict = {}
    _a_command_that_writes_data(monkeypatch, given, then=subprocess.TimeoutExpired(["node"], 30, output="", stderr=""))

    outcome = sandbox.SandboxExecutor._execute_here(["node", "--test"], str(product), "testing_specialist", "test", 30, None)

    assert outcome["returncode"] == "124"
    assert not given["data"].exists()


def test_only_a_directory_made_for_a_command_is_removed(tmp_path):
    kept = tmp_path / "test-results" / "fixtures"
    kept.mkdir(parents=True)
    elsewhere = tmp_path / "unit-data-1-2"
    elsewhere.mkdir()

    sandbox._remove_the_fresh_data_directories({"DATA_DIR": str(kept)})
    sandbox._remove_the_fresh_data_directories({"DATA_DIR": str(elsewhere)})

    assert kept.is_dir() and elsewhere.is_dir()
