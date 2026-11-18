"""A harness mechanism that did not run leaves a record in the run's transcript, and the run doctor counts it.

Deep review 2026-11-18, item D5: a few hundred `except Exception` handlers in the graph logged at debug and carried
on, so a check, a probe, a gate, a measurement or a workspace snapshot could fail on every call of a run and nothing
in the run's records said so - the mechanism behind features "built but silent".
"""

from __future__ import annotations

from app.observability import run_doctor
from app.observability.transcript import read_transcript
from app.tools import version_control
from app.tools.version_control import initialise_repository
from test_a_run_can_be_rewound_to_a_stage import _script
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_architecture,
    agents,
)


def test_a_workspace_snapshot_that_fails_is_recorded_in_the_run_s_transcript(agents, tmp_path, monkeypatch):
    from app.graph.workflow import start_workflow

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initialise_repository(workspace)
    taking = version_control.snapshot_workspace

    def git_fails_for_the_scrum_master(root, label, *args, **kwargs):
        return None if label == "scrum_master" else taking(root, label, *args, **kwargs)

    monkeypatch.setattr(version_control, "snapshot_workspace", git_fails_for_the_scrum_master)
    _script_through_architecture(agents, _approved_review())
    _script(agents)

    start_workflow(_graph(), _document(), _repository(workspace), "thread-degraded", run_id="run-degraded")

    recorded = [r for r in read_transcript("run-degraded", kinds={"degraded"}) if r["mechanism"] == "workspace_snapshot"]
    assert [r["of"] for r in recorded] == ["scrum_master"]


def _at(minute: int) -> str:
    return f"2026-11-18T10:{minute:02d}:00+00:00"


def test_the_doctor_counts_each_mechanism_that_did_not_run_and_says_so():
    records = [
        {"kind": "model_request", "stage": "technical_lead", "at": _at(0)},
        {"kind": "degraded", "stage": "test_round_1", "at": _at(1), "mechanism": "round_check.edge_case",
         "error_type": "KeyError", "message": "'repository'"},
        {"kind": "degraded", "stage": "test_round_2", "at": _at(2), "mechanism": "round_check.edge_case",
         "error_type": "KeyError", "message": "'repository'"},
        {"kind": "degraded", "stage": "scrum_master", "at": _at(3), "mechanism": "workspace_snapshot",
         "error_type": "", "message": ""},
    ]

    said = run_doctor.diagnose(records, status="running", now=None)

    assert [(d["mechanism"], d["count"]) for d in said["degraded"]] == [
        ("round_check.edge_case", 2), ("workspace_snapshot", 1)]
    assert said["degraded"][0]["stages"] == ["test_round_1", "test_round_2"]
    assert "KeyError" in said["degraded"][0]["last_error"]
    reported = next(s for s in said["suggestions"] if s["action"] == "report_degraded")
    assert "round_check.edge_case" in reported["said"] and "workspace_snapshot" in reported["said"]


def test_a_run_with_every_mechanism_running_has_nothing_degraded():
    said = run_doctor.diagnose([{"kind": "model_request", "stage": "architect", "at": _at(0)}], status="completed")

    assert said["degraded"] == []
    assert [s["action"] for s in said["suggestions"]] == ["none"]


def test_each_failure_is_recorded_with_its_mechanism_and_error_and_the_handler_goes_on(tmp_path, monkeypatch):
    from app.observability.degraded import degraded
    from app.observability.log_context import for_the_run

    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    with for_the_run("run-twice"):
        for _ in range(2):
            try:
                raise OSError("No space left on device")
            except OSError as error:
                degraded("measure.accepted_state", error, file="a" * 1_000)

    recorded = read_transcript("run-twice", kinds={"degraded"})
    assert [(r["mechanism"], r["error_type"]) for r in recorded] == [("measure.accepted_state", "OSError")] * 2
    assert "No space left" in recorded[0]["message"]
    assert len(recorded[0]["file"]) < 1_000
