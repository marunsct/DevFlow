"""A run doctor says what happened in a run and what to do next, and a diagnostic bundle carries no secret.

Deep review 2026-11-18, item F1: a customer install has no operator running the loop's audit and defect scripts every
ten minutes; the stage order, the defects going round in circles, the commands refused for want of memory and the
actions that fit were only in those scripts' output.
"""
from __future__ import annotations

import io
import json
import zipfile
from types import SimpleNamespace

from app.observability import diagnostic_bundle, run_doctor, transcript


def _at(minute: int) -> str:
    return f"2026-11-18T10:{minute:02d}:00+00:00"


def _a_run_going_round_in_circles() -> list[dict]:
    records = [
        {"kind": "model_request", "stage": "technical_lead", "at": _at(0)},
        {"kind": "model_response", "stage": "technical_lead", "at": _at(5)},
        {"kind": "tool_result", "stage": "specialist_backend_0", "at": _at(10),
         "content": "Not enough memory is free in this container to run that safely (180 MiB free)."},
    ]
    for round_ in (1, 2, 3):
        records += [
            {"kind": "defect", "stage": f"test_round_{round_}", "at": _at(10 + round_ * 5), "event": "raised",
             "defect_id": "d1", "round": round_, "description": "GET /notes answers 500 when the store is empty"},
            {"kind": "defect", "stage": f"defect_fix_{round_}_0", "at": _at(12 + round_ * 5), "event": "reverted",
             "defect_id": "d1", "round": round_},
        ]
    records.append({"kind": "model_request", "stage": "technical_lead", "at": _at(40)})
    return records


def test_the_doctor_names_the_defect_going_round_in_circles_and_the_actions_that_fit():
    said = run_doctor.diagnose(_a_run_going_round_in_circles(), status="failed", error="Escalated")

    assert said["stage_order"][0] == "technical_lead" and said["stage_order"][-1] == "technical_lead"
    assert (said["defects"]["raised"], said["defects"]["reverted"]) == (3, 3)
    assert said["defects"]["repeated"][0]["rounds"] == 3 and "answers 500" in said["defects"]["repeated"][0]["description"]
    assert said["resource_refusals"] == 1
    actions = [s["action"] for s in said["suggestions"]]
    assert {"resume_with_direction", "rewind", "free_resources"} <= set(actions)
    assert next(s for s in said["suggestions"] if s["action"] == "rewind")["stage"] == "technical_lead"


def test_a_quiet_run_with_nothing_wrong_needs_no_action():
    records = [{"kind": "model_request", "stage": "architect", "at": _at(0)},
               {"kind": "model_response", "stage": "architect", "at": _at(1)}]

    said = run_doctor.diagnose(records, status="completed")

    assert [s["action"] for s in said["suggestions"]] == ["none"]


def test_the_bundle_replaces_secret_values_and_credential_shapes_and_keeps_only_named_record_fields():
    record = SimpleNamespace(run_id="run-1", status="failed", error="token hunter2-abcdefgh refused",
                             model_overrides={"api_key": "sk-live-abcdefghijkl"}, repo_root="/data/w")
    environment = {"MODEL_API_KEY": "hunter2-abcdefgh", "HOME": "/home/someone"}

    archive = zipfile.ZipFile(io.BytesIO(diagnostic_bundle.build(
        "run-1", "header Authorization: Bearer abcdefghijklmnop and sk-live-abcdefghijkl", {"suggestions": []},
        diagnostic_bundle.the_record(record), environment)))
    everything = " ".join(archive.read(name).decode() for name in archive.namelist())
    shown = json.loads(archive.read("run-1/run.json"))

    assert "hunter2-abcdefgh" not in everything and "sk-live-abcdefghijkl" not in everything
    assert "abcdefghijklmnop" not in everything
    assert "model_overrides" not in shown and "repo_root" not in shown and shown["status"] == "failed"
    assert {"run-1/transcript.txt", "run-1/doctor.json", "run-1/run.json"} <= set(archive.namelist())


def test_the_server_answers_the_doctor_and_the_bundle(client, tmp_path, monkeypatch):
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]
    monkeypatch.setattr(transcript, "read_transcript", lambda run, kinds=None: _a_run_going_round_in_circles())

    doctor = client.get(f"/api/runs/{run_id}/doctor").json()
    bundle = client.get(f"/api/runs/{run_id}/diagnostic-bundle")

    assert doctor["defects"]["repeated"][0]["id"] == "d1"
    assert f"{run_id}/doctor.json" in zipfile.ZipFile(io.BytesIO(bundle.content)).namelist()
