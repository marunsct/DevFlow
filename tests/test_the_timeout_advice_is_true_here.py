"""What a timed-out command is told depends on what this workspace has.

Measured on one run. `npx playwright test` timed out and was answered
with "there is no browser to open a page with ... To check a page, read the
file and assert on its contents from a test". Seven minutes later
`npx playwright test --project=Desktop` ran 34 tests in the same sandbox, with
real passes and real failures.

The advice was not merely wrong about the environment. "Read the file and
assert on its contents from a test" describes the hand-built DOM that
`a_dom_built_by_hand` refuses - one part of the harness telling a stage to do
what another part stops it doing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.sandbox import (
    _TIMEOUT_ADVICE,
    _TIMEOUT_ADVICE_WITH_A_BROWSER,
    _a_browser_runner_is_installed,
    _timeout_advice,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    return tmp_path


def _manifest(where: Path, packages: dict) -> None:
    import json

    (where / "package.json").write_text(
        json.dumps({"name": "p", "devDependencies": packages}), encoding="utf-8"
    )


def test_a_workspace_with_playwright_is_told_browsers_work(workspace: Path) -> None:
    _manifest(workspace / "app", {"@playwright/test": "^1.40.0"})

    assert _a_browser_runner_is_installed(str(workspace), "app")
    assert _timeout_advice(str(workspace), "app") == _TIMEOUT_ADVICE_WITH_A_BROWSER


def test_it_names_what_to_try_instead(workspace: Path) -> None:
    _manifest(workspace / "app", {"playwright": "^1.40.0"})

    advice = _timeout_advice(str(workspace), "app")

    assert "--project=" in advice
    assert "webServer" in advice


def test_it_does_not_ask_for_the_thing_the_harness_refuses(workspace: Path) -> None:
    _manifest(workspace / "app", {"@playwright/test": "^1.40.0"})

    advice = _timeout_advice(str(workspace), "app")

    assert "global.document" in advice
    assert "refused elsewhere" in advice
    assert "read the file and assert on its contents" not in advice


def test_a_workspace_without_one_reads_as_before(workspace: Path) -> None:
    _manifest(workspace / "app", {"eslint": "^9.0.0"})

    assert not _a_browser_runner_is_installed(str(workspace), "app")
    assert _timeout_advice(str(workspace), "app") == _TIMEOUT_ADVICE


def test_no_manifest_at_all_reads_as_before(workspace: Path) -> None:
    assert _timeout_advice(str(workspace), "app") == _TIMEOUT_ADVICE


def test_the_manifest_may_be_above_the_working_directory(workspace: Path) -> None:
    """`npm test` from a subdirectory of a project that installed it."""
    _manifest(workspace, {"@playwright/test": "^1.40.0"})

    assert _a_browser_runner_is_installed(str(workspace), "app")


def test_a_runtime_dependency_counts_too(workspace: Path) -> None:
    import json

    (workspace / "app" / "package.json").write_text(
        json.dumps({"name": "p", "dependencies": {"playwright": "^1.40.0"}}),
        encoding="utf-8",
    )

    assert _a_browser_runner_is_installed(str(workspace), "app")


def test_an_unreadable_manifest_is_not_a_browser(workspace: Path) -> None:
    (workspace / "app" / "package.json").write_text("{not json", encoding="utf-8")

    assert not _a_browser_runner_is_installed(str(workspace), "app")


@pytest.fixture(autouse=True)
def _the_host_s_free_memory_is_not_this_test_s(monkeypatch):
    """The sandbox refuses to start a command when the host is short of memory (`resources.enough_headroom`); measured
    on a host whose model servers held most of its memory, that refusal came before the timeout these tests pin."""
    from app.tools import resources

    monkeypatch.setattr(resources, "enough_headroom", lambda *args, **kwargs: (True, ""))


def _timed_out_in_its_own_container(monkeypatch) -> None:
    import subprocess

    from app.tools import sandbox

    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setattr(sandbox, "_docker_binary", lambda: "/usr/bin/docker")

    def docker(argv, *args, **kwargs):
        if argv[1] == "run":
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout") or 1)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sandbox.subprocess, "run", docker)


def _timed_out_in_this_container(monkeypatch) -> None:
    import subprocess

    from app.tools import sandbox

    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    monkeypatch.setattr(sandbox.SandboxExecutor, "_resolve_executable",
                        staticmethod(lambda name, *args, **kwargs: "/usr/bin/" + name))

    def runs_out(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout") or 1, output="", stderr="")

    monkeypatch.setattr(sandbox, "_run_and_watch_the_tree", runs_out)


@pytest.mark.parametrize("where", [_timed_out_in_its_own_container, _timed_out_in_this_container])
def test_a_timeout_and_the_refusal_to_repeat_it_both_say_browsers_work_here(workspace: Path, monkeypatch, where) -> None:
    """The timeout itself and the refusal to repeat it say the same thing, wherever the command ran."""
    from app.tools.sandbox import SandboxExecutor

    _manifest(workspace / "app", {"@playwright/test": "^1.40.0"})
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    where(monkeypatch)
    suite = ["npx", "playwright", "test"]

    timed_out = SandboxExecutor.execute(suite, str(workspace), "testing_specialist", working_directory="app")
    refused = SandboxExecutor.execute(suite, str(workspace), "testing_specialist", working_directory="app")

    assert "timed out" in timed_out["error"] and "--project=" in timed_out["error"]
    assert "Not running this again" in refused["error"] and "--project=" in refused["error"]


def test_the_plain_advice_claims_nothing_false_about_this_environment() -> None:
    """A browser runner can be installed here at any time; a workspace without
    one yet is not a machine without browsers."""
    assert "no browser" not in _TIMEOUT_ADVICE
    assert "read the file and assert on its contents" not in _TIMEOUT_ADVICE


def test_the_plain_advice_names_a_runner_left_watching() -> None:
    """One run's `npm test` was `vitest` - watch mode - and ran the full 300
    seconds. The cause is named without naming a runner."""
    assert "watches for changes by default" in _TIMEOUT_ADVICE
    assert "run-once mode" in _TIMEOUT_ADVICE
    assert "vitest" not in _TIMEOUT_ADVICE.lower()


def test_a_command_that_is_not_a_test_run_gets_the_general_advice(workspace: Path) -> None:
    """One run's testing specialist started `node server.js`, which never exits,
    and was told "the likely causes are different" from the server it was."""
    _manifest(workspace / "app", {"@playwright/test": "^1"})

    assert _timeout_advice(str(workspace), "app", ["node", "server.js"]) == _TIMEOUT_ADVICE
    assert _timeout_advice(str(workspace), "app", ["npx", "playwright", "test"]) == _TIMEOUT_ADVICE_WITH_A_BROWSER
