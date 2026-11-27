"""A test run ended at its time limit answers with what it printed and with advice that fits it (LF.1641).

Measured on a service run: `npm test` ran Node's own unit runner and was ended at the 300-second limit five times.
Each answer was `"stdout": ""` - the command ran in a container of its own, and that path kept nothing of what the
run printed - and each was told about browser projects, `--project=` and a `webServer`, because the project also had
the browser runner installed for its acceptance suite. What held the run: a test helper that declared a request body
and never sent it, so twenty-five tests each failed at the runner's limit for one test, one after another; the spec
reporter had printed each of them, with how long it took, before the limit.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from app.tools import sandbox
from app.tools.sandbox import SandboxExecutor

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

PRINTED = (
    "✔ initDB creates a database and table (13.1ms)\n"
    "✖ POST /notes with missing title returns 400 (20003.9ms)\n"
    "✖ POST /notes with empty string title returns 400 (20006.4ms)\n"
)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    project = tmp_path / "notes-api"
    (project / "tests").mkdir(parents=True)
    (project / "package.json").write_text(json.dumps({
        "name": "notes-api",
        "scripts": {"test": "node --test --test-reporter=spec 'tests/**/*.test.js'", "test:acceptance": "playwright test"},
        "devDependencies": {"@playwright/test": "1.64.0"},
    }), encoding="utf-8")
    (project / "tests" / "routes.test.js").write_text(
        "test('POST /notes with missing title returns 400', async () => {});\n"
        "test('POST /notes with empty string title returns 400', async () => {});\n", encoding="utf-8")
    (project / "tests" / "db.test.js").write_text("test('initDB creates a database and table', () => {});\n",
                                                  encoding="utf-8")
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from app.tools import resources

    monkeypatch.setattr(resources, "enough_headroom", lambda *args, **kwargs: (True, ""))
    return tmp_path


def _ended_in_its_own_container(monkeypatch, printed: str = PRINTED) -> None:
    """Docker held past the limit: what `subprocess.run` raises then carries what was printed, as bytes."""
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setattr(sandbox, "_docker_binary", lambda: "/usr/bin/docker")

    def docker(argv, *args, **kwargs):
        if argv[1] == "run":
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout") or 1, output=printed.encode(), stderr=b"")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sandbox.subprocess, "run", docker)


def test_a_run_ended_in_its_own_container_answers_with_what_it_printed(workspace, monkeypatch):
    _ended_in_its_own_container(monkeypatch)

    outcome = SandboxExecutor.execute(["npm", "test"], str(workspace), "testing_specialist", working_directory="notes-api")

    assert "timed out" in outcome["error"]
    assert "POST /notes with missing title returns 400 (20003.9ms)" in outcome["stdout"]


def test_a_unit_run_is_not_told_about_browsers(workspace, monkeypatch):
    _ended_in_its_own_container(monkeypatch)

    said = SandboxExecutor.execute(["npm", "test"], str(workspace), "testing_specialist",
                                   working_directory="notes-api")["error"]

    assert "--project=" not in said and "webServer" not in said
    assert "drives no browser" in said and "never closes" in said


def test_the_refusal_to_run_it_again_says_the_same(workspace, monkeypatch):
    _ended_in_its_own_container(monkeypatch)
    SandboxExecutor.execute(["npm", "test"], str(workspace), "testing_specialist", working_directory="notes-api")

    refused = SandboxExecutor.execute(["npm", "test"], str(workspace), "testing_specialist",
                                      working_directory="notes-api")["error"]

    assert "Not running this again" in refused
    assert "drives no browser" in refused and "--project=" not in refused


def test_it_names_the_tests_that_ran_to_a_limit_and_the_file_that_declares_them(workspace, monkeypatch):
    _ended_in_its_own_container(monkeypatch)

    said = SandboxExecutor.execute(["npm", "test"], str(workspace), "testing_specialist",
                                   working_directory="notes-api")["error"]

    assert "`POST /notes with missing title returns 400`" in said
    assert "`POST /notes with empty string title returns 400`" in said
    assert "`notes-api/tests/routes.test.js`" in said
    assert "initDB creates a database" not in said and "db.test.js" not in said


def test_a_run_of_the_browser_suite_is_still_told_about_browsers(workspace, monkeypatch):
    _ended_in_its_own_container(monkeypatch, printed="Running 18 tests using 1 worker\n")

    said = SandboxExecutor.execute(["npm", "run", "test:acceptance"], str(workspace), "testing_specialist",
                                   working_directory="notes-api")["error"]

    assert "--project=" in said and "drives no browser" not in said


def test_the_advice_for_a_test_run_uses_no_banned_word():
    assert not BANNED.search(sandbox._TIMEOUT_ADVICE_FOR_A_TEST_RUN)
    assert not BANNED.search(sandbox._tests_that_ran_to_a_limit("✖ a b (9000ms)\n", "/nowhere", None))
