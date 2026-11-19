"""The harness's own command is run with its arguments as written; only a model's are read as workspace paths.

Measured: the start probe in a command's own container was given the readiness path `/health`; nothing was at that
path and the workspace was its parent, so the rewrite for a model's workspace path sent it as `../health`. The
request line was malformed, every probe got no answer, and the product's real error was never shown.
"""
from __future__ import annotations

import pytest

from app.tools.sandbox import SandboxExecutor


@pytest.fixture(autouse=True)
def _here(monkeypatch):
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")


def _echoed(tmp_path, for_the_harness: bool) -> str:
    (tmp_path / "notes-api").mkdir()
    outcome = SandboxExecutor.execute(["echo", "/health"], repo_root=str(tmp_path), role_name="testing_specialist",
                                      category="start", working_directory="notes-api",
                                      for_the_harness=for_the_harness) or {}
    return str(outcome.get("stdout") or outcome).strip()


def test_the_harness_s_url_path_goes_out_as_written(tmp_path):
    assert _echoed(tmp_path, True) == "/health"
