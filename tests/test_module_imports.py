"""Every module must import on its own, in any order.

`repository` imports the model-output sanitiser; `app.agents` imports the role
agent, which imports the agent toolkit, which imports `repository`. Adding that
import at module scope left `repository` half-built for whichever entrypoint
touched the sandbox first - and the test suite passed anyway, because pytest
happened to import the package in the order that hides it.

A cycle that only shows up under one import order is worth a test that tries
every order that matters: each module first, in a fresh interpreter.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

MODULES = [
    "app.main",
    "app.graph.workflow",
    "app.agents.role_agent",
    "app.tools.sandbox",
    "app.tools.repository",
    "app.tools.agent_toolkit",
    "app.analysis.integration_checks",
    "app.analysis.file_kinds",
    "app.agents.model_output",
    "app.agents.text_tool_calls",
    "app.models",
]


@pytest.mark.parametrize("module", MODULES)
def test_the_module_imports_first(module: str) -> None:
    source = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": source, "PATH": "/usr/bin:/bin"},
        timeout=120,
    )

    assert result.returncode == 0, f"{module} failed to import first:\n{result.stderr[-800:]}"
