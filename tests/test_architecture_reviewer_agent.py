"""Tests for the Senior Architect Reviewer Deep Agent (Step 4.3)."""

from __future__ import annotations

from app.agents.architecture_reviewer import (
    ArchitectureReviewFinding,
    ArchitectureReviewOutput,
    create_architecture_reviewer_agent,
)


def test_architecture_review_output_schema_is_present() -> None:
    schema = ArchitectureReviewOutput.model_json_schema()

    required_fields = {"status", "findings", "approval_conditions", "accepted_risks"}
    assert required_fields.issubset(schema["properties"].keys())
    assert schema["properties"]["status"]["enum"] == ["approved", "changes_required"]


def test_architecture_review_finding_schema_is_present() -> None:
    schema = ArchitectureReviewFinding.model_json_schema()

    required_fields = {"severity", "description", "evidence", "required_remediation"}
    assert required_fields.issubset(schema["properties"].keys())


def test_architecture_reviewer_agent_factory_creates_graph() -> None:
    agent = create_architecture_reviewer_agent(model="openai:gpt-4o-mini")

    assert agent is not None
    assert hasattr(agent, "invoke")


def test_architecture_reviewer_prompt_has_no_write_artifact_or_banned_words() -> None:
    import re

    from app.agents.architecture_reviewer import _SYSTEM_PROMPT

    # The architecture reviewer has can_write=False and no artifact tool;
    # it must never instruct the model to call write_artifact or edit files.
    assert "write_artifact" not in _SYSTEM_PROMPT
    assert "approved artifact tool" not in _SYSTEM_PROMPT

    # The new constraint added to the prompt must contain no banned words
    rule_start = _SYSTEM_PROMPT.index("Do not modify application source code, documents, or the specification itself")
    rule_end = _SYSTEM_PROMPT.index("Never approve based only on the Principal Architect's own confidence")
    rule_text = _SYSTEM_PROMPT[rule_start:rule_end].lower()

    banned = [r"\btask\b", r"\btasks\b", r"\bto-do\b", r"\btodo\b", r"\bbutton\b", r"\bclick\b", r"\bcheckbox\b"]
    for pattern in banned:
        assert not re.search(pattern, rule_text), f"Banned word matched in rule: {pattern}"
