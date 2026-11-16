"""A stopped run can be resumed with a direction its next model calls carry (LR.35).

Found in the launch review: a direction was refused on any run that was not running, so a failed run could be resumed
only as it was, with the cause of its stop unaddressed, or cloned from the beginning.
"""
from __future__ import annotations

from app.server.run_store import RunStore
from app.server.runner import WorkflowRunner


def _create_run(client) -> str:
    response = client.post("/api/runs", files=[("files", ("brief.md", b"# A small service", "text/markdown"))])
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


def test_a_failed_run_takes_a_direction_and_resumes(client, monkeypatch, tmp_path):
    run_id = _create_run(client)
    assert client.post(f"/api/runs/{run_id}/resume-with-direction", json={"text": "keep the store in one file"}).status_code == 409
    store = RunStore()
    record = store.load(run_id)
    record.status = "failed"
    record.repo_root = str(tmp_path)
    store.save(record)
    resumed = []

    async def resume_run(self, which):
        resumed.append(which)

    monkeypatch.setattr(WorkflowRunner, "resume_run", resume_run)
    answer = client.post(f"/api/runs/{run_id}/resume-with-direction", json={"text": "keep the store in one file"})
    assert answer.status_code == 202, answer.text
    assert resumed == [run_id]
    notes = client.get(f"/api/runs/{run_id}/steering").json()
    assert any("keep the store in one file" in str(note) for note in notes.get("notes", notes))
