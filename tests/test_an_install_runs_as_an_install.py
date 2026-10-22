"""A package-manager install runs in the install category whatever was sent.

The `install` category is the one with the registry and the time to use it.
One run's `npm i -D jest` arrived with no category, ran under the 120-second
default instead, and timed out - answered with advice about servers, watchers
and browser test suites, none of which it was.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import SandboxExecutor, _fetches_dependencies


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "i", "-D", "jest"],
        ["npm", "install"],
        ["npm", "ci"],
        ["pnpm", "add", "vitest"],
        ["yarn", "install"],
        ["pip", "install", "-r", "requirements.txt"],
        ["poetry", "install"],
        ["cargo", "add", "serde"],
        ["cargo", "fetch"],
        ["go", "get", "example.com/x"],
        ["go", "mod", "download"],
        ["dotnet", "restore"],
        ["bundle", "install"],
        ["composer", "install"],
    ],
)
def test_an_install_in_any_ecosystem_is_recognised(command) -> None:
    assert _fetches_dependencies(command)


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "test"],
        ["npm", "run", "build"],
        ["npx", "playwright", "test"],
        ["go", "test", "./..."],
        ["cargo", "build"],
        ["pip", "--version"],
        ["dotnet", "build"],
        [],
    ],
)
def test_nothing_else_is(command) -> None:
    assert not _fetches_dependencies(command)


def test_execute_runs_the_install_in_the_install_category(tmp_path, monkeypatch) -> None:
    seen = {}

    def fake_run(cls, command, repo_root, role_name="general", category="default", *a, **k):
        seen["category"] = category
        return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(fake_run))

    SandboxExecutor.execute(["npm", "i", "-D", "jest"], str(tmp_path), "testing_specialist")

    assert seen["category"] == "install"


def test_a_category_the_caller_chose_is_kept(tmp_path, monkeypatch) -> None:
    seen = {}

    def fake_run(cls, command, repo_root, role_name="general", category="default", *a, **k):
        seen["category"] = category
        return {"returncode": "0", "stdout": "", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(fake_run))

    SandboxExecutor.execute(["npm", "test"], str(tmp_path), "testing_specialist", category="test")

    assert seen["category"] == "test"


def test_an_install_that_times_out_is_told_it_was_an_install(tmp_path) -> None:
    from app.tools.sandbox import _timeout_advice

    advice = _timeout_advice(str(tmp_path), None, ["npm", "i", "-D", "jest"])

    assert "package install" in advice
    assert "browser" not in advice and "watch" not in advice


def test_anything_else_keeps_its_advice(tmp_path) -> None:
    from app.tools.sandbox import _TIMEOUT_ADVICE, _timeout_advice

    assert _timeout_advice(str(tmp_path), None, ["npm", "test"]) == _TIMEOUT_ADVICE
