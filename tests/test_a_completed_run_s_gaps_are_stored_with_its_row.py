"""A completed run's gaps are stored with its row and captured at completion.

Two runs released at a hidden-test 1/10 read "completed" everywhere: the
graph knew what they had not proven, but the record did not carry it, so no
screen, export or audit could tell a proven completion from a hollow one.
The release writes `completion_gaps`; the runner captures them onto the run
record when the graph completes; the store keeps them in the runs row
(Initiative J.4).
"""

from __future__ import annotations

import inspect

from app.server import runner
from app.server.runner import RunRecord


def test_a_record_carries_no_gaps_until_completion_names_them():
    record = RunRecord(run_id="run-x", thread_id="t-x", document_names=[], document_paths=[])

    assert record.completion_gaps == []


def test_gaps_round_trip_through_the_runs_row(run_store):
    record = RunRecord(
        run_id="run-gaps", thread_id="t-gaps", document_names=[], document_paths=[],
        status="completed",
        completion_gaps=[
            "AC-2 ships deferred, unproven by the suite: no automated check can prove it",
            "The project setup was never proven: its smoke tests did not pass",
        ],
    )

    run_store.save(record)
    fetched = run_store.load("run-gaps")

    assert fetched is not None
    assert fetched.completion_gaps == record.completion_gaps
    assert fetched.status == "completed"


def test_a_row_saved_before_the_column_existed_reads_as_no_gaps(run_store):
    """The migration adds the column with an empty default; reading an old
    row must not invent gaps or fail."""
    record = RunRecord(run_id="run-old", thread_id="t-old", document_names=[], document_paths=[],
                       status="completed")
    run_store.save(record)
    with run_store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE runs SET completion_gaps = '[]' WHERE run_id = 'run-old'")
        conn.commit()

    assert run_store.load("run-old").completion_gaps == []


def test_the_runner_captures_the_gaps_when_the_graph_completes():
    source = inspect.getsource(runner.WorkflowRunner)
    assert 'record.completion_gaps = [str(gap) for gap in state.get("completion_gaps") or []]' in source
    # ...on the same path that records the completion itself, before the row
    # is persisted.
    completion = source.index('record.status = "completed" if stage == "complete"')
    assert source.index("record.completion_gaps =", completion) < source.index("self._persist(record)", completion)
