"""A run's row names the stage it has just entered, not the last one that paused.

The row was written only at a pause or the end; a run that went through five
stages without a pause showed "Auto-approving: acceptance_author_1" for an hour.
"""

from __future__ import annotations

import inspect

from app.graph import workflow
from app.server import run_store


def test_entering_a_stage_names_it_on_the_running_run_s_row(monkeypatch):
    named = []

    class _Store:
        def record_stage(self, run_id, stage, meaning, updated_at):
            named.append((run_id, stage, meaning))
            return True

    monkeypatch.setattr(run_store.RunStore, "shared", classmethod(lambda cls: _Store()))

    workflow._name_the_stage_on_the_run("run-x", "technical_lead")

    assert named and named[0][:2] == ("run-x", "technical_lead") and named[0][2]


def test_a_store_that_cannot_answer_never_stops_the_stage(monkeypatch):
    def broken(cls):
        raise RuntimeError("no database")

    monkeypatch.setattr(run_store.RunStore, "shared", classmethod(broken))

    workflow._name_the_stage_on_the_run("run-x", "technical_lead")


def test_only_a_running_row_is_changed_and_every_stage_names_itself():
    source = inspect.getsource(run_store.RunStore.record_stage)
    assert "AND status = 'running'" in source
    assert "_name_the_stage_on_the_run(" in inspect.getsource(workflow._run_gated_agent)
