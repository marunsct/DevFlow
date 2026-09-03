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
    for role in get_args(SpecialistRole):
        agent = create_specialist_agent(role, model="openai:gpt-4o-mini")
        assert agent is not None
        assert hasattr(agent, "invoke")


def test_validation_tool_runs_an_allowlisted_command(tmp_path: Path) -> None:
    run_validation = build_validation_tool(str(tmp_path))

    result = run_validation.invoke({"command": ["python", "--version"]})

    assert result["returncode"] == 0


def test_validation_tool_rejects_a_disallowed_command(tmp_path: Path) -> None:
    run_validation = build_validation_tool(str(tmp_path))

    result = run_validation.invoke({"command": ["rm", "-rf", "/"]})

    assert "error" in result

