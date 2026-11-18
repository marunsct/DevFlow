"""A rewind finds the stage's own workspace snapshot by its checkpoint, and refuses a point whose snapshot was never taken.

Deep review 2026-11-18, item D2a: a rewind matched a checkpoint to a workspace
snapshot by the clock (the first snapshot of the stage taken from the
checkpoint's time on), and a snapshot that failed was logged at debug and
ignored. A stage whose snapshot failed was rewound all the same: the run's
state went back while its files stayed as a later stage left them, or were put
back from another entry of the same stage.
"""

from __future__ import annotations

import pytest

from app.tools import version_control
from app.tools.version_control import (
    SnapshotNotTaken,
    StageSnapshot,
    initialise_repository,
    snapshot_for_checkpoint,
    stage_snapshots,
)
from test_a_run_can_be_rewound_to_a_stage import _script
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_architecture,
    agents,
)


def _a_finished_run(agents, tmp_path, thread_id: str):
    from app.graph.workflow import rewind_points, start_workflow

    initialise_repository(tmp_path)
    _script_through_architecture(agents, _approved_review())
    _script(agents)
    graph = _graph()
    state = start_workflow(graph, _document(), _repository(tmp_path), thread_id)
    assert state["stage"] == "complete", state.get("error")
    return graph, rewind_points(graph, thread_id)


def test_each_stage_snapshot_names_the_checkpoint_its_stage_started_from(agents, tmp_path):
    graph, points = _a_finished_run(agents, tmp_path, "run-named")

    named = {s.checkpoint_id: s.stage for s in stage_snapshots(tmp_path)}

    scrum = next(point for point in points if point["stage"] == "scrum_master")
    assert named[scrum["checkpoint_id"]] == "scrum_master"


def test_a_rewind_to_a_stage_whose_snapshot_failed_refuses_and_leaves_the_run_where_it_was(agents, tmp_path, monkeypatch):
    from app.graph.workflow import RewindError, rewind_to

    taking = version_control.snapshot_workspace

    def git_fails_for_the_scrum_master(root, label, *args, **kwargs):
        return None if label == "scrum_master" else taking(root, label, *args, **kwargs)

    monkeypatch.setattr(version_control, "snapshot_workspace", git_fails_for_the_scrum_master)
    graph, points = _a_finished_run(agents, tmp_path, "run-unsnapshotted")
    target = next(point for point in points if point["stage"] == "scrum_master")
    (tmp_path / "made_after.txt").write_text("a later stage's file")

    with pytest.raises(RewindError, match="not snapshotted"):
        rewind_to(graph, "run-unsnapshotted", target["checkpoint_id"], str(tmp_path))

    assert graph.get_state({"configurable": {"thread_id": "run-unsnapshotted"}}).values["stage"] == "complete"
    assert (tmp_path / "made_after.txt").exists()


def _snap(millis: int, stage: str, commit: str, checkpoint_id: str | None = None) -> StageSnapshot:
    return StageSnapshot(millis, stage, commit, checkpoint_id)


def test_the_snapshot_named_by_the_checkpoint_is_taken_whatever_the_clock_says():
    snapshots = [_snap(1_000, "builder", "early"), _snap(5_000, "builder", "mine", "cp-2"),
                 _snap(5_100, "builder", "retried", "cp-2")]

    assert snapshot_for_checkpoint(snapshots, "builder", "cp-2", since_millis=9_000) == "mine"


def test_a_checkpoint_from_before_snapshots_named_their_checkpoint_is_matched_by_time():
    snapshots = [_snap(1_000, "builder", "older"), _snap(3_000, "builder", "its own"),
                 _snap(8_000, "builder", "named later", "cp-9")]

    assert snapshot_for_checkpoint(snapshots, "builder", "cp-1", since_millis=2_500) == "its own"


def test_a_checkpoint_written_after_snapshots_named_their_checkpoint_with_none_naming_it_was_never_snapshotted():
    snapshots = [_snap(1_000, "builder", "first", "cp-1"), _snap(9_000, "builder", "a later entry", "cp-3")]

    with pytest.raises(SnapshotNotTaken):
        snapshot_for_checkpoint(snapshots, "builder", "cp-2", since_millis=5_000)
