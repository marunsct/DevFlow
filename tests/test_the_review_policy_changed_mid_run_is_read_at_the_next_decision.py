"""The owner can change which reviews a live run stops at, and the run's next gate follows the change (plan WS.3).

Before, a run's reviews were fixed when it started: the policy was copied into the graph's state once, so an owner
who wanted to see the plan after all, or no longer wanted to stop after each sprint, had to cancel and start again.
"""
from __future__ import annotations

from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_architecture,
    _script_through_sprint,
    agents,
)

from app.graph.workflow import start_workflow
from app.observability.transcript import read_transcript
from app.server.run_store import RunStore


def _a_run(client, tmp_path, status: str) -> str:
    response = client.post("/api/runs", files=[("files", ("brief.md", b"# A small service", "text/markdown"))])
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]
    store = RunStore()
    record = store.load(run_id)
    record.status = status
    record.repo_root = str(tmp_path)
    store.save(record)
    return run_id


def test_a_live_run_s_reviews_change_and_a_worker_saving_its_old_record_does_not_undo_it(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    run_id = _a_run(client, tmp_path, "running")
    store = RunStore()
    loaded_by_the_worker = store.load(run_id)

    answer = client.put(f"/api/runs/{run_id}/review-policy", json={"review_policy": {"sprint_plan": True}})
    store.save(loaded_by_the_worker)  # the worker persists the record it loaded before the change

    assert answer.status_code == 200, answer.text
    assert answer.json()["review_policy"]["sprint_plan"] is True
    assert store.load(run_id).review_policy.get("sprint_plan") is True
    [changed] = read_transcript(run_id, {"review_policy_changed"})
    assert changed["changed"] == {"sprint_plan": True}


def test_an_unknown_review_point_or_a_finished_run_is_refused(client, tmp_path):
    live = _a_run(client, tmp_path, "running")
    finished = _a_run(client, tmp_path, "completed")

    unknown = client.put(f"/api/runs/{live}/review-policy", json={"review_policy": {"lunch": True}})
    done = client.put(f"/api/runs/{finished}/review-policy", json={"review_policy": {"sprint": True}})

    assert unknown.status_code == 422 and "lunch" in unknown.json()["detail"]
    assert done.status_code == 409


def test_the_run_s_next_gate_follows_the_policy_on_its_record_not_the_one_it_started_with(client, agents, tmp_path):
    run_id = _a_run(client, tmp_path, "running")
    on = {"review_policy": {"technical_specification": True}}
    assert client.put(f"/api/runs/{run_id}/review-policy", json=on).status_code == 200
    _script_through_architecture(agents, _approved_review())
    _script_through_sprint(agents)

    state = start_workflow(_graph(), _document(), _repository(tmp_path), run_id, review_policy={}, run_id=run_id)

    assert state["stage"] == "awaiting_user_review:technical_specification"
