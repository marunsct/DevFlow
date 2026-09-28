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
@__import__('pytest').mark.skipif(not __import__('os').getenv("OPENAI_API_KEY") or __import__('os').getenv("OPENAI_API_KEY") == "sk-test", reason="Requires real OPENAI_API_KEY")
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

def test_the_brief_never_quotes_the_host_workspace_path():
    """The agent's filesystem is rooted at "/"; the host path resolves nowhere.

    Quoting it and then instructing the agent not to use it does not work:
    agents retried `ls` against that exact string four times in a row on
    one run, every attempt failing with path_not_found.
    """
    from types import SimpleNamespace

    from app.agents.product_manager import build_intake_request

    repository = SimpleNamespace(
        root_path="/app/data/workspaces/low-run-abc123", branch="main",
        commit="deadbeef", status="clean",
    )
    document = SimpleNamespace(
        text="a brief", source_path="brief.md", source_type="markdown",
        truncated=False, truncation_note=None,
    )

    brief = build_intake_request(document, repository)["messages"][0]["content"]

    assert "/app/data/workspaces" not in brief
    # The information that is actually useful survives.
    assert "main" in brief and "deadbeef" in brief


def test_the_brief_names_no_file_the_agent_could_try_to_read() -> None:
    """A filename in a prompt is an affordance: it invites a read.

    The previous version showed the upload's basename instead of its host path,
    on the reasoning that the name was safe where the path was not. It is not:
    the stored name carries an upload suffix (`brief_low_aa06a786.md`) and names
    nothing in a workspace rooted at "/". Measured on runs 2b5def74, da6c5e19,
    5d83e946 and again on one run, where `product_manager` spent its first
    two calls on `read_file` and then `glob` for that exact string.
    """
    import re

    from app.agents.product_manager import build_intake_request
    from app.documents import DocumentContent

    document = DocumentContent(
        source_path="/app/data/uploads/brief_low_aa06a786.md",
        source_type="markdown",
        text="# Build a to-do app\nIt must store tasks.",
        truncated=False,
    )

    class _Repo:
        branch = "main"
        commit = "abc123"

    brief = build_intake_request(document, _Repo())["messages"][0]["content"]

    assert "brief_low_aa06a786" not in brief
    assert "/app/data/uploads" not in brief
    # Nothing that reads as a filename to open.
    assert not re.search(r"\b[\w-]+\.(md|markdown|txt|docx|pdf|csv)\b", brief)
    # The document itself must still be there.
    assert "Build a to-do app" in brief


def test_the_brief_names_no_file_the_agent_could_try_to_read() -> None:
    """A filename in a prompt is an affordance: it invites a read.

    The previous version showed the upload's basename instead of its host path,
    on the reasoning that the name was safe where the path was not. It is not:
    the stored name carries an upload suffix (`brief_low_aa06a786.md`) and names
    nothing in a workspace rooted at "/". Measured on runs 2b5def74, da6c5e19,
    5d83e946 and again on one run, where `product_manager` spent its first
    two calls on `read_file` and then `glob` for that exact string.
    """
    import re

    from app.agents.product_manager import build_intake_request
    from app.documents import DocumentContent

    document = DocumentContent(
        source_path="/app/data/uploads/brief_low_aa06a786.md",
        source_type="markdown",
        text="# Build a to-do app\nIt must store tasks.",
        truncated=False,
    )

    class _Repo:
        branch = "main"
        commit = "abc123"

    brief = build_intake_request(document, _Repo())["messages"][0]["content"]

    assert "brief_low_aa06a786" not in brief
    assert "/app/data/uploads" not in brief
    assert not re.search(r"\b[\w-]+\.(md|markdown|txt|docx|pdf|csv)\b", brief)
    assert "Build a to-do app" in brief


def test_the_document_text_carries_no_stored_filename(tmp_path) -> None:
    """The leak a previous fix missed, found by the run transcript.

    `build_intake_request` was changed to show no filename. The name was in the
    document *text*: `read_document` prefixed each file with
    `--- Document: brief_low_236ab395.md ---`, the stored upload name, which
    exists nowhere an agent can read.

    Measured across five runs:
    `product_manager` opens by trying to read that exact string and gets an
    error for its first call of the run. Only one run's transcript - the
    first record of what the model was actually sent - showed where it came
    from.
    """
    import re

    from app.documents import read_document

    (tmp_path / "brief_low_236ab395.md").write_text("# Brief\nBuild it.\n", encoding="utf-8")

    document = read_document([str(tmp_path / "brief_low_236ab395.md")])

    assert not re.search(r"brief_low_[0-9a-f]+", document.text)
    assert "Build it." in document.text


def test_several_documents_are_still_separated(tmp_path) -> None:
    """The separator has a job when more than one file is uploaded; it just
    does not need to name a file to do it."""
    from app.documents import read_document

    (tmp_path / "a_1111.md").write_text("# One\nfirst\n", encoding="utf-8")
    (tmp_path / "b_2222.md").write_text("# Two\nsecond\n", encoding="utf-8")

    document = read_document([str(tmp_path / "a_1111.md"), str(tmp_path / "b_2222.md")])

    assert "--- Document 1 ---" in document.text
    assert "--- Document 2 ---" in document.text
    assert "first" in document.text and "second" in document.text
    assert "a_1111" not in document.text and "b_2222" not in document.text
