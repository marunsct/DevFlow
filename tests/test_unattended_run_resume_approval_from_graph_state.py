from __future__ import annotations

from unittest.mock import MagicMock
from app.server.events import EventBus
from app.server.runner import RunRecord, WorkflowRunner


def test_unattended_run_answers_own_gate_when_graph_state_is_parked_on_approval():
    runner = WorkflowRunner(EventBus())
    record = RunRecord(
        run_id="run-gate",
        thread_id="thread-gate",
        document_names=[],
        document_paths=[],
        current_stage="acceptance_author_2",
        auto_approve=True,
    )

    mock_graph = MagicMock()
    mock_snap = MagicMock()
    mock_snap.values = {"stage": "awaiting_approval:acceptance_author_2"}
    mock_graph.get_state.return_value = mock_snap

    # On old code, graph is not checked and this returns False
    assert runner._resume_means_answering_own_gate(record, graph=mock_graph) is True
