"""A command that runs a test suite gets the test time limit, whatever the caller sent.

One run's `specialist_testing_4` ran `npm test` with no category. It ran under
the 120-second default and timed out; its end-to-end half alone took 144
seconds when the stage ran it again as `npm run test:e2e` with
`category: "test"`.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import SandboxExecutor, _runs_tests


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "test"],
        ["npm", "run", "test:e2e"],
        ["npm", "run", "test-unit"],
        ["npx", "playwright", "test"],
        ["node", "--test"],
        ["go", "test", "./..."],
        ["cargo", "test"],
        ["dotnet", "test"],
        ["pytest", "-q"],
        ["python3", "-m", "pytest"],
        ["python", "-m", "unittest"],
        ["./vendor/bin/phpunit"],
    ],
)
def test_a_test_run_in_any_ecosystem_is_recognised(command) -> None:
    assert _runs_tests(command)


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "run", "build"],
        ["node", "server.mjs"],
        ["npm", "install"],
        ["cargo", "build"],
        ["ls", "tests"],
        ["cat", "app.test.js"],
        [],
    ],
)
def test_nothing_else_is(command) -> None:
    assert not _runs_tests(command)


def _category_seen(tmp_path, monkeypatch, command, **kwargs) -> str:
    seen = {}

    def fake_run(cls, command, repo_root, role_name="general", category="default", *a, **k):
        seen["category"] = category
        return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(fake_run))
    SandboxExecutor.execute(command, str(tmp_path), "testing_specialist", **kwargs)
    return seen["category"]


def test_execute_runs_a_test_command_in_the_test_category(tmp_path, monkeypatch) -> None:
    assert _category_seen(tmp_path, monkeypatch, ["npm", "test"]) == "test"


def test_a_category_the_caller_chose_is_kept(tmp_path, monkeypatch) -> None:
    assert _category_seen(tmp_path, monkeypatch, ["npm", "test"], category="build") == "build"
