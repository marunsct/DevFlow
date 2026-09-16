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


def test_a_named_runner_survives_a_forbidden_word() -> None:
    """Matching on words alone rejected answers that named a real runner.

    The same shape as finding 83, where `grep` exiting 1 because it matched
    nothing was reported as a failed command: the check asked about the wording
    rather than about the thing itself.
    """
    from app.agents.tools_models import TechnologyStack

    for value in (
        "node --test (no manual steps required)",
        "pytest, not manual verification",
        "jest with jsdom instead of manual browser testing",
    ):
        stack = TechnologyStack(
            language="JavaScript", framework="vanilla",
            database="localStorage", testing_framework=value,
        )
        assert stack.testing_framework == value


def test_a_value_that_names_no_runner_is_still_refused() -> None:
    """The check still has to do its job: these name nothing that can run."""
    import pytest
    from pydantic import ValidationError

    from app.agents.tools_models import TechnologyStack

    for value in ("Manual browser testing", "visual inspection", "by hand", "none"):
        with pytest.raises(ValidationError):
            TechnologyStack(
                language="JavaScript", framework="vanilla",
                database="localStorage", testing_framework=value,
            )
