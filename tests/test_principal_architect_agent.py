"""Tests for the Principal Architect Deep Agent (Step 4.2)."""

from __future__ import annotations

from app.agents.principal_architect import (
    ArchitectureDecisionRecord,
    TechnicalSpecificationOutput,
    create_principal_architect_agent,
)


def test_technical_specification_schema_is_present() -> None:
    schema = TechnicalSpecificationOutput.model_json_schema()

    required_fields = {
        "product_scope",
        "component_boundaries",
        "domain_model",
        "api_and_event_contracts",
        "data_flows",
        "security_and_privacy",
        "reliability_and_observability",
        "testing",
        "deployment",
        "open_questions",
        "acceptance_criteria",
        "decisions",
    }

    assert required_fields.issubset(schema["properties"].keys())


def test_architecture_decision_record_schema_is_present() -> None:
    schema = ArchitectureDecisionRecord.model_json_schema()

    required_fields = {
        "title",
        "context",
        "alternatives",
        "decision",
        "rationale",
        "trade_offs",
        "consequences",
        "validation_evidence",
    }

    assert required_fields.issubset(schema["properties"].keys())


def test_principal_architect_agent_factory_creates_graph() -> None:
    agent = create_principal_architect_agent(model="openai:gpt-4o-mini")

    assert agent is not None
    assert hasattr(agent, "invoke")
