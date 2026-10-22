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


def test_a_revision_is_told_to_change_nothing_else() -> None:
    """The instruction guarded removal and said nothing about addition.

    On one run four consecutive architecture reviews returned
    changes_required with 5, then 4, then 6, then 8 findings, escalating from
    minor to blocking, each round raising subjects the round before had not
    mentioned - an export prompt, a persistent banner, a quota warning.

    Whether the architect added those while revising or the reviewer noticed
    them late cannot be separated from the record, since the specification is
    overwritten each revision. The instruction is asymmetric either way: it
    forbade dropping unflagged content and permitted adding unreviewed content.
    """
    from app.agents.principal_architect import build_architecture_revision_request

    class _Doc:
        source_path = "/uploads/brief.md"
        source_type = "markdown"
        text = "build a to-do list"
        truncated = False
        truncation_note = None

    class _Repo:
        branch = "master"
        commit = "abc1234"
        root_path = "/app/data/workspaces/t29"
        files: list = []

    brief = build_architecture_revision_request(
        "previous spec", ["fix the testing framework contradiction"],
        "intake", "tools", "stack", _Repo(), _Doc(),
    )["messages"][0]["content"]

    assert "do not add scope that was not asked for" in brief
    assert "changes nothing else" in brief
    # The existing half must survive.
    assert "Do not silently drop specification content" in brief
