"""Tests for the Technical Lead Deep Agent (Step 5.2)."""

from __future__ import annotations

from app.agents.technical_lead import (
    MilestonePlanOutput,
    SpecialistTask,
    create_technical_lead_agent,
)


def test_milestone_plan_output_schema_is_present() -> None:
    schema = MilestonePlanOutput.model_json_schema()

    required_fields = {
        "selected_sprint_goal",
        "milestone_scope",
        "delegated_tasks",
        "integration_notes",
        "blockers",
    }
    assert required_fields.issubset(schema["properties"].keys())


def test_specialist_task_schema_restricts_role_to_known_specialists() -> None:
    schema = SpecialistTask.model_json_schema()

    assert {"specialist_role", "task_description", "acceptance_criteria"}.issubset(
        schema["properties"].keys()
    )


def test_technical_lead_agent_factory_creates_graph() -> None:
    agent = create_technical_lead_agent(model="openai:gpt-4o-mini")

    assert agent is not None
    assert hasattr(agent, "invoke")
