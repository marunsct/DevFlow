"""A run can be rewound to the start of any stage it started, with its files as they were, and run from there.

The owner's request: go back to a certain stage of a run and run it again
from there - after a stage made a poor decision, or after a fix to the
harness that only an earlier stage would benefit from. Every stage now
snapshots the workspace as it starts (outside every branch and tag); a rewind
makes the checkpoint before the chosen stage the run's latest and puts the
files back as that snapshot holds them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.tools.version_control import (
    commit_milestone,
    initialise_repository,
    restore_snapshot,
    snapshot_workspace,
    workspace_snapshots,
)
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _script_through_architecture,
    _security_review,
    _specialist,
    _sprint_plan,
    agents,
    responds_with,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def test_a_snapshot_puts_the_workspace_back_as_it_was(tmp_path):
    initialise_repository(tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("v1\n")
    (tmp_path / ".harness").mkdir(exist_ok=True)
    (tmp_path / ".harness" / "decisions.json").write_text("[1]")
    ref = snapshot_workspace(tmp_path, "scrum_master")
    assert ref and ref.startswith("refs/harness/stages/")
    head_then = _git(tmp_path, "rev-parse", "HEAD")

    (tmp_path / "app" / "main.py").write_text("v2\n")
    (tmp_path / "app" / "later.py").write_text("made later\n")
    (tmp_path / ".harness" / "decisions.json").write_text("[1, 2]")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("installed")
    commit_milestone(tmp_path, sprint=1, goal="first sprint")
    assert _git(tmp_path, "tag", "-l", "sprint-1") == "sprint-1"

    (_, stage, commit), = [s for s in workspace_snapshots(tmp_path) if s[1] == "scrum_master"]
    assert restore_snapshot(tmp_path, commit)

    assert (tmp_path / "app" / "main.py").read_text() == "v1\n"
    assert not (tmp_path / "app" / "later.py").exists()
    assert (tmp_path / ".harness" / "decisions.json").read_text() == "[1]", "the harness's own records go back too"
    assert (tmp_path / "node_modules" / "pkg.js").exists(), "installed packages are left alone"
    assert _git(tmp_path, "rev-parse", "HEAD") == head_then
    assert _git(tmp_path, "tag", "-l", "sprint-1") == "", "no sprint the rewound run has not done again"
    assert any(s[1] == "before-rewind" for s in workspace_snapshots(tmp_path)), "what it held is kept"


def test_a_workspace_that_is_not_a_repository_is_never_snapshotted(tmp_path):
    assert snapshot_workspace(tmp_path, "scrum_master") is None
    assert workspace_snapshots(tmp_path) == []


def _script(agents) -> None:
    agents.script("scrum_master", [responds_with(_sprint_plan())])
    agents.script("technical_lead", [responds_with(_milestone("backend"))])
    agents.script("specialist_backend", [responds_with(_specialist())])
    agents.script("specialist_testing", [responds_with(_specialist())])
    agents.script("milestone_reviewer", [responds_with(_milestone_review())])
    agents.script("security_reviewer", [responds_with(_security_review())])


def test_a_finished_run_is_rewound_to_a_stage_and_run_again_from_there(agents, tmp_path):
    from app.graph.workflow import rewind_points, rewind_to, start_workflow

    initialise_repository(tmp_path)
    _script_through_architecture(agents, _approved_review())
    _script(agents)
    graph = _graph()
    state = start_workflow(graph, _document(), _repository(tmp_path), "run-rewind")
    assert state["stage"] == "complete", state.get("error")

    points = rewind_points(graph, "run-rewind")
    stages = [point["stage"] for point in points]
    assert stages[0] == "product_manager" and "scrum_master" in stages
    assert not any(stage.endswith(("_worker", "_gather")) or stage == "complete" for stage in stages)
    assert len(stages) == len(set(stages)), "one point per stage entered"

    target = next(point for point in points if point["stage"] == "scrum_master")
    (tmp_path / "made_after.txt").write_text("a later stage's file")
    done = rewind_to(graph, "run-rewind", target["checkpoint_id"], str(tmp_path))

    assert {k: done[k] for k in ("stage", "files_restored")} == {"stage": "scrum_master", "files_restored": True}
    assert done["point_at"]  # where it went back to, for the KPIs (`run_kpis.live_branch`)
    assert not (tmp_path / "made_after.txt").exists()
    _script(agents)
    again = graph.invoke(None, config={"configurable": {"thread_id": "run-rewind"}, "recursion_limit": 500})
    assert again["stage"] == "complete"
    assert len(agents.requests["scrum_master"]) == 2, "the scrum master ran again"
    assert len(agents.requests["product_manager"]) == 1, "nothing before it did"


def test_only_the_start_of_a_stage_is_a_point(agents, tmp_path):
    from app.graph.workflow import RewindError, rewind_to

    with pytest.raises(RewindError):
        rewind_to(_graph(), "no-such-run", "no-such-checkpoint", str(tmp_path))


@pytest.fixture
def runner(run_store, redis_container, monkeypatch):
    from app.server.events import EventBus
    from app.server.redis_client import reset_clients
    from app.server.runner import WorkflowRunner

    reset_clients()
    monkeypatch.setenv("CHECKPOINTER_TYPE", "memory")
    return WorkflowRunner(EventBus(), run_store=run_store)


async def test_a_running_run_is_paused_before_it_is_rewound(runner):
    from app.server.runner import RunConflict

    record = runner.register_run(
        run_id="run-live", thread_id="thread-live", document_names=["brief.md"],
        document_paths=["/tmp/brief.md"], owner="alice", tenant_id="acme",
    )
    record.status = "running"
    runner.run_store.save(record)

    with pytest.raises(RunConflict, match="pause it first"):
        await runner.rewind_run("run-live", "any")


def test_a_stage_that_paused_for_approval_is_one_point(agents, tmp_path):
    """Each answered approval begins with a bookkeeping checkpoint; it is not a new entry.

    Measured on a live run: one acceptance stage answered eleven approvals and
    was listed as eleven points.
    """
    from test_graph_routing import approve_write_decision, pause_for_approval

    from app.graph.workflow import resume_pending_approval, rewind_points, start_workflow

    _script_through_architecture(agents, _approved_review())
    _script(agents)
    agents.script("scrum_master", [pause_for_approval(), pause_for_approval(), responds_with(_sprint_plan())])
    graph = _graph()
    state = start_workflow(graph, _document(), _repository(tmp_path), "run-paused")
    while str(state.get("stage", "")).startswith("awaiting_approval:"):
        state = resume_pending_approval(graph, "run-paused", approve_write_decision())

    assert state["stage"] == "complete", state.get("error")
    stages = [point["stage"] for point in rewind_points(graph, "run-paused")]
    assert stages.count("scrum_master") == 1, stages


def test_a_stage_whose_work_goes_out_side_by_side_is_one_point(agents, tmp_path, monkeypatch):
    """Measured on a live run: one sprint's dispatch, going round its paused
    workers again and again, was listed as forty-one points."""
    import dataclasses

    from test_defects_are_fixed_side_by_side import THREE
    from test_defects_are_fixed_side_by_side import _script as _script_defects
    from test_graph_routing import approve_write_decision, pause_for_approval

    from app import config
    from app.graph.workflow import resume_pending_approval, rewind_points, start_workflow

    monkeypatch.setattr("app.agents.specialists.what_the_files_already_prove", lambda *a, **k: [])
    real = config.load_settings()
    monkeypatch.setattr(config, "load_settings", lambda *a, **k: dataclasses.replace(real, execution_mode="parallel"))
    _script_defects(agents, THREE)
    agents.script("specialist_database", [pause_for_approval(), pause_for_approval(), responds_with(_specialist(tests=["t-db"]))])
    graph = _graph()
    state = start_workflow(graph, _document(), _repository(tmp_path), "run-side-by-side")
    while str(state.get("stage", "")).startswith("awaiting_approval:"):
        state = resume_pending_approval(graph, "run-side-by-side", approve_write_decision())
    assert state["stage"] == "complete", state.get("error")

    stages = [point["stage"] for point in rewind_points(graph, "run-side-by-side")]
    assert stages.count("defect_remediation") == 1, stages
