"""A run that had reviews on the build model keeps that gap after a restart (plan item AO.7).

The downgrade was a context variable, reset each time the graph was built. A
restart, or the judgement server coming back for the next segment, made the
gap vanish from a run whose earlier reviews had not been independent.
"""
from __future__ import annotations

from app.graph import delivery
from app.models import roles


def test_the_gap_stands_after_the_context_forgets(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    roles.remember_the_downgrade("run-q", "The judgement model 'x' could not be built, so reviews were not independent.")
    roles._DOWNGRADE.set(None)  # the next segment built it fine

    assert delivery._reviews_that_were_not_independent("run-q") == [
        "The judgement model 'x' could not be built, so reviews were not independent."
    ]


def test_a_run_that_never_had_one_has_no_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    roles._DOWNGRADE.set(None)

    assert delivery._reviews_that_were_not_independent("run-q") == []
    assert delivery._reviews_that_were_not_independent() == []


def test_the_first_note_stands_and_another_run_is_unaffected(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    roles.remember_the_downgrade("run-q", "first")
    roles.remember_the_downgrade("run-q", "second")
    roles._DOWNGRADE.set(None)

    assert roles.downgrade_for("run-q") == "first"
    assert roles.downgrade_for("run-other") is None


def test_the_runner_keeps_it_when_it_says_it(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.server import runner

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    roles._DOWNGRADE.set(None)
    note = "The judgement model 'x' could not be built, so reviews were not independent."
    monkeypatch.setattr(roles, "judgement_downgrade", lambda: note)
    published = []

    async def publish(run_id, event):
        published.append(event.message)

    async def next_sequence(run_id):
        return 1

    the_runner = SimpleNamespace(event_bus=SimpleNamespace(publish=publish, next_sequence=next_sequence))
    record = SimpleNamespace(run_id="run-q", current_stage="principal_architect")

    asyncio.run(runner.WorkflowRunner._say_if_the_judgement_model_was_replaced(the_runner, record))

    assert published == [note]
    monkeypatch.setattr(roles, "judgement_downgrade", lambda: None)  # the next segment built it fine
    assert roles.downgrade_for("run-q") == note
