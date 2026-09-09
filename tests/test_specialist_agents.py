"""Tests for the specialist Deep Agents (Step 5.3)."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

from app.agents.specialists import SpecialistOutput, create_specialist_agent
from app.agents.technical_lead import SpecialistRole
from app.tools.agent_toolkit import build_validation_tool


def test_specialist_output_schema_is_present() -> None:
    schema = SpecialistOutput.model_json_schema()

    required_fields = {"changed_files", "decisions", "tests", "documentation", "risks", "blockers"}
    assert required_fields.issubset(schema["properties"].keys())


def test_every_specialist_role_builds_a_graph() -> None:
    from langchain_core.language_models import FakeListChatModel
    for role in get_args(SpecialistRole):
        agent = create_specialist_agent(role, model=FakeListChatModel(responses=[]))
        assert agent is not None
        assert hasattr(agent, "invoke")


def test_validation_tool_refuses_a_disallowed_executable(tmp_path: Path, monkeypatch) -> None:
    """Validation goes through the sandbox, so the same allowlist applies."""
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    run_validation = build_validation_tool(str(tmp_path))

    result = run_validation.invoke({"command": ["rm", "-rf", "/"]})

    assert result["returncode"] != 0
    assert "not permitted" in result["stderr"]


def test_validation_tool_rejects_interpreter_escape_hatches(tmp_path: Path, monkeypatch) -> None:
    """`python -c` style arguments must not become a general shell."""
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    run_validation = build_validation_tool(str(tmp_path))

    result = run_validation.invoke({"command": ["python", "-c", "import os; os.system('id')"]})

    assert result["returncode"] != 0
    assert "arbitrary code" in result["stderr"]


def test_validation_tool_is_disabled_when_execution_is_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "false")
    run_validation = build_validation_tool(str(tmp_path))

    result = run_validation.invoke({"command": ["pytest", "-q"]})

    assert "disabled" in result["stderr"]
