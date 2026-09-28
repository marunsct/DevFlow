"""A malformed tool call is a bad attempt, not a reason to end a run.

Measured on one run, at 2,333 events into Sprint 2:

    OpenAIAPIError: Error code: 500 - llama-server error:
      "Failed to parse tool call arguments as JSON:
       [json.exception.parse_error.101] parse error at line 1, column 26:
       syntax error while parsing value - invalid string: missing closing
       quote"

The model truncated a tool call mid-string and the server refused it. The whole
run stopped over one malformed message, on work that was otherwise sound.

This is the "benign condition raises where every sibling returns" pattern in a
new place: a context overflow is handled, a missing structured response is
retried, and a generation fault - the most ordinary failure a local model has -
was fatal.
"""

from __future__ import annotations

import pytest

from app.graph.workflow import _is_transient_model_error, _transient_retry_update

MALFORMED = (
    "OpenAIAPIError: Error code: 500 - llama-server error: Failed to parse tool "
    "call arguments as JSON: parse error at line 1, column 26: invalid string: "
    "missing closing quote"
)


@pytest.mark.parametrize(
    "message",
    [
        MALFORMED,
        "Error code: 500 - internal server error",
        "Connection reset by peer",
        "Read timed out.",
        "503 Service Unavailable",
    ],
)
def test_a_generation_fault_is_transient(message):
    assert _is_transient_model_error(RuntimeError(message))


@pytest.mark.parametrize(
    "message",
    [
        "This model's maximum context length is 131072 tokens",
        "Incorrect API key provided",
        "model not found",
    ],
)
def test_a_refusal_is_not_transient(message):
    """Re-sending an oversized or unauthorised request changes nothing."""
    assert not _is_transient_model_error(RuntimeError(message))


def test_context_overflow_is_never_classified_as_transient():
    """They need different responses: overflow compacts, transient retries."""
    assert not _is_transient_model_error(
        RuntimeError("prompt is too long: 200000 tokens > 131072 maximum")
    )


def test_a_transient_error_routes_back_to_the_stage():
    update = _transient_retry_update({}, "product_manager", RuntimeError(MALFORMED))

    assert update is not None
    assert update["stage"] == "product_manager"
    assert update["structured_retries"]["product_manager:transient"] == 1
    # The paused conversation must be dropped, or the retry replays the failure.
    assert update["pending_inner_thread_id"] is None
    assert update["pending_decision"] is None


def test_an_iterated_stage_routes_to_its_owning_node():
    """`specialist_ui_ux_0` is a stage name, not a graph node."""
    update = _transient_retry_update({}, "specialist_ui_ux_0", RuntimeError(MALFORMED))

    assert update["stage"] == "specialist_dispatch"


def test_the_budget_is_bounded():
    """A persistent fault must end the run with the provider's own message."""
    from app.graph.workflow import _max_structured_retries

    spent = {"structured_retries": {"product_manager:transient": _max_structured_retries()}}

    assert _transient_retry_update(spent, "product_manager", RuntimeError(MALFORMED)) is None


def test_a_non_transient_error_is_not_retried():
    assert _transient_retry_update({}, "product_manager", RuntimeError("bad api key")) is None


def test_both_model_call_sites_are_guarded():
    """The fault can arrive on the first call or on a resume; one site is half
    a fix."""
    from pathlib import Path

    workflow = (Path(__file__).resolve().parent.parent / "src/app/graph/workflow.py").read_text()

    assert workflow.count("_transient_retry_update(state, stage_name, exc)") == 2
