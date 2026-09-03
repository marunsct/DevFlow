"""Tests for the Scrum Master Deep Agent (Step 5.1)."""

from __future__ import annotations

from app.agents.scrum_master import SprintDefinition, SprintPlanOutput, create_scrum_master_agent


def test_sprint_plan_output_schema_is_present() -> None:
    schema = SprintPlanOutput.model_json_schema()

    assert {"sprints", "open_questions"}.issubset(schema["properties"].keys())


def test_sprint_definition_schema_is_present() -> None:
    schema = SprintDefinition.model_json_schema()

    required_fields = {
        "goal",
        "user_value",
        "in_scope",
        "out_of_scope",
        "dependencies",
        "acceptance_criteria",
        "test_strategy",
        "security_checks",
        "documentation_work",
        "risks",
        "rollback_notes",
    }
    assert required_fields.issubset(schema["properties"].keys())


def test_scrum_master_agent_factory_creates_graph() -> None:
    agent = create_scrum_master_agent(model="openai:gpt-4o-mini")

    assert agent is not None
    assert hasattr(agent, "invoke")
