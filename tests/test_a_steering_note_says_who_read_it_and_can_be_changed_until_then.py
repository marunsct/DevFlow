"""A steering note a person can trust: it says which stage read it, and can be changed or withdrawn until then (WS.3).

Before, a note was sent and nothing on the run's stream said it had been read; a note sent by mistake could not be
taken back, a note with a slip could not be corrected, and a paused run refused a note outright, so a direction for it
had to wait until the person had resumed the run.
"""
from __future__ import annotations

import pytest

from app.server import agent_stream, steering
from app.server.run_store import RunStore


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def stream(monkeypatch):
    sent: list[tuple] = []
    monkeypatch.setattr(agent_stream, "publish_one", lambda *event: sent.append(event) or True, raising=False)
    return sent


def test_a_new_note_is_queued_and_the_first_call_that_reads_it_says_so_on_the_stream(tmp_path, stream):
    note = steering.add(tmp_path, "Keep the sign-in page.", "owner")
    assert note["state"] == "queued" and steering.notes(tmp_path)[0]["state"] == "queued"

    steering.as_instructions(tmp_path, "defect_fix_2_9", "run-s")
    steering.as_instructions(tmp_path, "defect_fix_2_9", "run-s")  # read again: said once

    [(run_id, stage, kind, message, metadata)] = stream
    assert (run_id, stage, kind) == ("run-s", "defect_fix_2_9", "log")
    assert "read by defect_fix_2_9" in message
    assert metadata == {"kind": "steering_read", "note_id": "N-1", "scope": "run"}
    kept = steering.notes(tmp_path)[0]
    assert (kept["state"], kept["applied_stage"]) == ("read", "defect_fix_2_9") and kept["applied_at"]


def test_a_withdrawn_note_reaches_no_later_call(tmp_path, stream):
    steering.add(tmp_path, "Use one table for everything.", "owner")
    steering.add(tmp_path, "Keep the sign-in page.", "owner")

    withdrawn = steering.withdraw(tmp_path, "N-1", "owner")

    assert withdrawn["state"] == "withdrawn" and withdrawn["withdrawn_at"]
    sent = steering.as_instructions(tmp_path, "specialist_backend_1", "run-s")
    assert "Use one table" not in sent and "Keep the sign-in page." in sent
    assert [event[4]["note_id"] for event in stream] == ["N-2"]
    assert steering.notes(tmp_path)[0]["state"] == "withdrawn"


def test_an_edited_note_reaches_the_call_as_edited(tmp_path, stream):
    steering.add(tmp_path, "Keep the sign-in pgae.", "owner")

    edited = steering.edit(tmp_path, "N-1", "Keep the sign-in page as it is.", "owner")

    assert edited["text"] == "Keep the sign-in page as it is." and edited["state"] == "queued" and edited["edited_at"]
    sent = steering.as_instructions(tmp_path, "specialist_backend_1", "run-s")
    assert "Keep the sign-in page as it is." in sent and "pgae" not in sent


def test_a_note_already_read_cannot_be_edited_or_withdrawn_and_the_refusal_names_the_reader(tmp_path, stream):
    steering.add(tmp_path, "Keep the sign-in page.", "owner")
    steering.as_instructions(tmp_path, "defect_fix_1", "run-s")

    with pytest.raises(steering.NoteSettled, match="already read by defect_fix_1"):
        steering.edit(tmp_path, "N-1", "Something else.", "owner")
    with pytest.raises(steering.NoteSettled, match="already read"):
        steering.withdraw(tmp_path, "N-1", "owner")
    with pytest.raises(steering.NoteNotFound):
        steering.withdraw(tmp_path, "N-9", "owner")
    assert steering.notes(tmp_path)[0]["text"] == "Keep the sign-in page."


def test_a_note_kept_before_states_existed_is_read_once_a_call_carried_it(tmp_path):
    assert steering.state_of({"text": "x", "applied_stage": "s"}) == "read"
    assert steering.state_of({"text": "x"}) == "queued"


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


def test_a_paused_run_keeps_a_note_for_when_it_resumes(client, tmp_path):
    run_id = _a_run(client, tmp_path, "paused")

    answer = client.post(f"/api/runs/{run_id}/steering", json={"text": "keep the store in one file"})

    assert answer.status_code == 201, answer.text
    assert answer.json()["note"]["state"] == "queued" and "resumes" in answer.json()["waiting"]
    assert [n["text"] for n in steering.notes(tmp_path)] == ["keep the store in one file"]


def test_the_routes_edit_and_withdraw_a_queued_note_and_refuse_a_read_one(client, tmp_path, stream):
    run_id = _a_run(client, tmp_path, "running")
    for text in ("first note", "second note", "third note"):
        assert client.post(f"/api/runs/{run_id}/steering", json={"text": text}).status_code == 201

    edited = client.patch(f"/api/runs/{run_id}/steering/N-1", json={"text": "first note, corrected"})
    withdrawn = client.post(f"/api/runs/{run_id}/steering/N-2/withdraw")
    steering.as_instructions(tmp_path, "defect_fix_1", run_id)
    too_late = client.patch(f"/api/runs/{run_id}/steering/N-3", json={"text": "changed"})
    missing = client.post(f"/api/runs/{run_id}/steering/N-7/withdraw")

    assert edited.status_code == 200 and edited.json()["note"]["text"] == "first note, corrected"
    assert withdrawn.status_code == 200 and withdrawn.json()["note"]["state"] == "withdrawn"
    assert too_late.status_code == 409 and "already read by defect_fix_1" in too_late.json()["detail"]
    assert missing.status_code == 404
    listed = client.get(f"/api/runs/{run_id}/steering").json()["notes"]
    assert [(n["text"], n["state"]) for n in listed] == [
        ("first note, corrected", "read"), ("second note", "withdrawn"), ("third note", "read"),
    ]
