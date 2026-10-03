"""The harness's own commands are measurements, never withheld as repeats.

On one run the agents ran the acceptance suite three times with nothing written
between, so when the harness measured the state the sprint was accepted in, the
sandbox answered "Not running this again ... you already have the answer". The
accepted baseline recorded no acceptance results, so the next sprint's CI could
not see a criterion regress - and the same refusal at the release gate would
have held a finished product back as "the suite did not run".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools import sandbox
from app.tools.sandbox import SUCCESSES_BEFORE_WITHHOLDING, SandboxExecutor, read_execution_ledger


RAN: list[list[str]] = []


@pytest.fixture
def workspace(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "workspace-run-1"
    (root / "app").mkdir(parents=True)
    RAN.clear()
    ran = RAN

    def fake_run(cls, command, repo_root, role_name="general", category="default", *a, **k):
        ran.append(list(command))
        return {"returncode": "0", "stdout": "8 passed", "stderr": ""}

    monkeypatch.setattr(SandboxExecutor, "_run", classmethod(fake_run))
    return root


SUITE = ["npm", "run", "test:acceptance"]


def test_the_harness_runs_the_suite_however_often_the_agents_did(workspace) -> None:
    for _ in range(SUCCESSES_BEFORE_WITHHOLDING + 1):
        SandboxExecutor.execute(SUITE, str(workspace), "testing_specialist", "test", working_directory="app")
    agents_last = SandboxExecutor.execute(SUITE, str(workspace), "testing_specialist", "test", working_directory="app")
    assert "Not running this again" in str(agents_last.get("error")), "the agents' guard still stands"

    measured = SandboxExecutor.execute(
        SUITE, str(workspace), "testing_specialist", "test", working_directory="app", for_the_harness=True,
    )

    assert measured.get("returncode") == "0" and not measured.get("error")
    assert RAN[-1] == SUITE


def test_the_harness_s_runs_do_not_count_toward_an_agent_s_repeats(workspace) -> None:
    for _ in range(SUCCESSES_BEFORE_WITHHOLDING + 2):
        SandboxExecutor.execute(
            SUITE, str(workspace), "testing_specialist", "test", working_directory="app", for_the_harness=True,
        )

    first = SandboxExecutor.execute(SUITE, str(workspace), "testing_specialist", "test", working_directory="app")

    assert not first.get("error")
    entries = read_execution_ledger(str(workspace))
    assert [e["by"] for e in entries] == ["harness"] * (SUCCESSES_BEFORE_WITHHOLDING + 2) + ["agent"]
    assert len(read_execution_ledger(str(workspace), by_the_agents=True)) == 1
    assert sandbox.succeeded_this_way_before(str(workspace), SUITE, "app") == 1


def test_the_flag_is_only_set_while_the_harness_command_runs(workspace) -> None:
    seen = []
    original = SandboxExecutor._run.__func__

    def spy(cls, *a, **k):
        seen.append(sandbox.running_for_the_harness())
        return original(cls, *a, **k)

    SandboxExecutor._run = classmethod(spy)  # type: ignore[method-assign]
    try:
        SandboxExecutor.execute(SUITE, str(workspace), "testing_specialist", "test", for_the_harness=True)
        SandboxExecutor.execute(["npm", "test"], str(workspace), "testing_specialist", "test")
    finally:
        SandboxExecutor._run = classmethod(original)  # type: ignore[method-assign]
    assert seen == [True, False]
    assert sandbox.running_for_the_harness() is False


def test_every_harness_runner_asks_as_the_harness(monkeypatch, tmp_path) -> None:
    from app.stacks import scaffold as scaffolding

    seen = []
    monkeypatch.setattr(
        "app.tools.sandbox.SandboxExecutor.execute",
        lambda argv, **kwargs: seen.append(kwargs.get("for_the_harness")) or {"returncode": "0"},
    )
    scaffolding.sandbox_runner(tmp_path)(SUITE, "test", "app")
    assert seen == [True]
