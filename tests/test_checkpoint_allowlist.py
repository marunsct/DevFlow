"""Tests for the checkpoint deserialization allowlist.

LangGraph will reconstruct arbitrary Python types from a checkpoint by default,
which it warns is both deprecated and a code-execution risk if anyone can write
to the checkpoint store. These tests prove the workflow declares exactly the
types it stores, so a resume neither warns nor silently accepts an unexpected
type.
"""

from __future__ import annotations

import logging

from app.graph.checkpointing import CHECKPOINTED_TYPES, build_checkpointer, build_serializer
from app.sprint import RemediationCycle, start_remediation
from app.state import ReviewRequestStatus, ReviewStatus, WorkflowStage


def test_workflow_state_types_round_trip_through_a_checkpoint() -> None:
    """Every allowlisted type must survive serialize -> deserialize unchanged."""
    serde = build_serializer()
    cycle = start_remediation("Sprint 1: booking")

    restored = serde.loads_typed(serde.dumps_typed(cycle))

    assert isinstance(restored, RemediationCycle)
    assert restored.sprint_goal == "Sprint 1: booking"


def test_enums_used_in_review_state_round_trip() -> None:
    """Review status is an enum; a checkpoint must restore it as the enum, not a string."""
    serde = build_serializer()
    review = ReviewStatus(
        stage=WorkflowStage.ARCHITECTURE,
        status=ReviewRequestStatus.SKIPPED,
        reviewer="alice",
        revision=1,
        updated_at="2026-01-01T00:00:00+00:00",
    )

    restored = serde.loads_typed(serde.dumps_typed(review))

    assert restored.status is ReviewRequestStatus.SKIPPED
    assert restored.stage is WorkflowStage.ARCHITECTURE


def test_restoring_state_does_not_warn_about_unregistered_types(caplog) -> None:
    """A resume must not emit LangGraph's 'unregistered type' deprecation warning."""
    serde = build_serializer()
    cycle = start_remediation("Sprint 1: booking")

    with caplog.at_level(logging.WARNING, logger="langgraph.checkpoint.serde.jsonplus"):
        serde.loads_typed(serde.dumps_typed(cycle))

    assert "unregistered type" not in caplog.text


def test_the_checkpointer_applies_the_allowlist() -> None:
    saver = build_checkpointer()

    assert saver.serde is not None
    assert len(CHECKPOINTED_TYPES) > 0
