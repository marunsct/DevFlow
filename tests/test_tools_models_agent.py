"""Tests for the Tools and Models Architect Deep Agent (Step 4.1)."""

from __future__ import annotations

from app.agents.tools_models import ToolsAndModelsOutput, create_tools_models_agent


def test_tools_and_models_output_schema_is_present() -> None:
    schema = ToolsAndModelsOutput.model_json_schema()

    required_fields = {
        "frameworks",
        "model_providers",
        "storage_options",
        "queue_and_job_systems",
        "authentication",
        "observability",
        "testing_tools",
        "deployment_options",
        "open_questions",
    }

    assert required_fields.issubset(schema["properties"].keys())


def test_tools_models_agent_factory_creates_graph() -> None:
    agent = create_tools_models_agent(model="openai:gpt-4o-mini")

    assert agent is not None
    assert hasattr(agent, "invoke")
