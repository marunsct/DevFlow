"""Tests for the Product Manager Deep Agent contract.

The product manager is the first role worker in the workflow. This test keeps the
behavior narrow: the agent must exist and expose a structured intake schema that
matches the product briefing outputs described in the workflow plan.
"""

from __future__ import annotations

import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.agents.approval import extract_pending_approval
from app.agents.product_manager import (
    ProductManagerOutput,
    build_intake_request,
    create_product_manager_agent,
)
from app.config import load_settings
from app.documents import read_document
from app.state import RepositoryContext


def test_product_manager_output_schema_is_present() -> None:
    """The output schema should include every product-intake field required by the plan."""
    schema = ProductManagerOutput.model_json_schema()

    required_fields = {
        "product_name",
        "users_and_stakeholders",
        "problems_and_desired_outcomes",
        "core_workflows",
        "mvp_candidates",
        "deferred_scope",
        "constraints",
        "evidence_vs_assumptions",
        "success_measures",
        "open_questions",
    }

    assert required_fields.issubset(schema["properties"].keys())


def test_product_manager_agent_factory_creates_graph() -> None:
    """The agent factory should produce a compiled graph rather than a bare stub."""
    agent = create_product_manager_agent(model="openai:gpt-4o-mini")

    assert agent is not None
    assert hasattr(agent, "invoke")


def _local_model_server_available() -> bool:
    """Check whether the configured local model endpoint accepts connections.

    The real end-to-end test below needs a running LM Studio (or compatible)
    server. We probe the TCP port with a short timeout instead of assuming the
    server is up, so the test skips cleanly in environments without one.
    """
    settings = load_settings()
    parsed = urlparse(settings.openai_base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.skipif(
    not _local_model_server_available(),
    reason="Local model server is not reachable; skipping end-to-end invocation.",
)
def test_product_manager_agent_returns_structured_intake_for_sample_brief(tmp_path: Path) -> None:
    """Run the agent against a small brief and inspect its real output structure.

    This follows the workflow plan's Step 3.1 gate: we must look at the actual
    output shape from a representative brief before trusting extraction logic.
    """
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(
        "# Acme Scheduling Assistant\n\n"
        "Small clinics need an easy way for patients to book appointments online "
        "instead of calling the front desk.\n",
        encoding="utf-8",
    )
    document = read_document(brief_path)
    repository = RepositoryContext(
        root_path=str(tmp_path),
        branch="main",
        commit="0000000",
        status="clean",
    )

    agent = create_product_manager_agent()
    # Every role agent now carries a checkpointer (Step 3.2), and LangGraph
    # refuses to run a checkpointed graph without a thread id to store the
    # checkpoint under. Any id works here; the run is not resumed.
    result = agent.invoke(
        build_intake_request(document, repository),
        config={"configurable": {"thread_id": "test-product-manager-intake"}},
    )

    # Since Step 3.2 an artifact write pauses the agent, so a run has two
    # legitimate shapes: it finished with structured output, or it paused for a
    # human decision. Both prove the contract; only "finished with nothing"
    # does not, and that is what this asserts against.
    if result.get("__interrupt__"):
        approval = extract_pending_approval(
            result, tmp_path, requested_by="product_manager", stage="intake"
        )
        assert approval is not None
        assert approval.artifact_path
        return

    structured = result["structured_response"]
    assert isinstance(structured, ProductManagerOutput), (
        "The agent finished without structured output and without pausing for approval. "
        "This usually means the configured local model did not call the structured-output "
        f"tool; got {type(structured).__name__}."
    )
    assert structured.product_name