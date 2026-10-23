"""The settings page diagnoses the serving model on request and lets each guide be set for it (plan MD.3).

The owner asked for one action that diagnoses the model and saves the settings
it needs against it, and a switch for each guide, as some models need help in
one area only.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def _served(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.models import guidance, model_guidance

    for guide in guidance.GUIDES:
        monkeypatch.setenv(guide.switch, "on")

    monkeypatch.setattr(model_guidance, "served_now", lambda: "page-model")


def test_the_page_shows_every_guide_with_its_switch(client, _served) -> None:
    body = client.get("/api/settings/model/steering").json()

    assert body["model"] == "page-model" and body["status"] == "idle"
    ids = [g["id"] for g in body["guides"]]
    assert "one_program_a_command" in ids and "paths_as_given" in ids
    first = body["guides"][0]
    assert first["switch"].startswith("GUIDE_") and first["switch_on"] is True and first["override"] is None


def test_a_guide_is_turned_on_off_and_back_to_auto_for_the_model(client, _served) -> None:
    on = client.put("/api/settings/model/steering/guides/paths_as_given", json={"override": True}).json()
    assert next(g for g in on["guides"] if g["id"] == "paths_as_given")["active"] is True

    auto = client.put("/api/settings/model/steering/guides/paths_as_given", json={"override": None}).json()
    guide = next(g for g in auto["guides"] if g["id"] == "paths_as_given")
    assert guide["override"] is None and guide["active"] is False
    assert client.put("/api/settings/model/steering/guides/no_such", json={"override": True}).status_code == 404


def test_the_diagnosis_is_refused_while_a_run_is_live(client, _served, monkeypatch) -> None:
    from app.server import settings

    monkeypatch.setattr(settings, "_a_run_is_live", lambda: True)
    answer = client.post("/api/settings/model/steering/diagnose")
    assert answer.status_code == 409 and "between runs" in answer.json()["detail"]


def test_the_diagnosis_is_queued_for_the_worker(client, _served, monkeypatch) -> None:
    from app.server import settings, tasks

    monkeypatch.setattr(settings, "_a_run_is_live", lambda: False)
    queued = []
    monkeypatch.setattr(tasks.diagnose_the_model, "delay", lambda: queued.append(True))
    answer = client.post("/api/settings/model/steering/diagnose")

    assert answer.status_code == 202 and queued == [True]
    assert client.get("/api/settings/model/steering").json()["status"] == "running"
