"""A stage thread left running after its run was paused or cancelled makes no more model calls in that process.

Measured on one run: after a pause, the paused stage's agent loop - in an executor thread the stopped task did not end -
kept calling the model for five minutes, beside the same run rewound in the other worker process, and could have
written into the workspace the rewind had just restored.
"""
from __future__ import annotations

import inspect

import pytest

from app.models import call_gate as models
from app.graph import workflow
from app.server import runner


def _in_run(monkeypatch, run_id):
    monkeypatch.setattr("langgraph.config.get_config", lambda: {"configurable": {"app_run_id": run_id}})


def test_a_call_for_a_run_this_process_stopped_raises_and_a_resume_lets_it_through(monkeypatch):
    _in_run(monkeypatch, "run-stopped-here")
    workflow.remember_the_stop("run-stopped-here")
    try:
        with pytest.raises(workflow.RunCancelled):
            models._stop_if_this_run_was_stopped()
        workflow.forget_the_stop("run-stopped-here")
        models._stop_if_this_run_was_stopped()
    finally:
        workflow.forget_the_stop("run-stopped-here")


def test_another_run_and_no_run_are_left(monkeypatch):
    workflow.remember_the_stop("run-a")
    try:
        _in_run(monkeypatch, "run-b")
        models._stop_if_this_run_was_stopped()
        _in_run(monkeypatch, None)
        models._stop_if_this_run_was_stopped()
    finally:
        workflow.forget_the_stop("run-a")


def test_pausing_and_cancelling_remember_the_stop_and_every_call_asks():
    assert "_remember_the_stop(record.run_id)" in inspect.getsource(runner.RunManager._finish_paused) \
        if hasattr(runner, "RunManager") else "_remember_the_stop(record.run_id)" in inspect.getsource(runner)
    assert inspect.getsource(runner).count("_remember_the_stop(record.run_id)") == 2
    from app.models import CompatibleChatOpenAI
    assert "_stop_if_this_run_was_stopped()" in inspect.getsource(CompatibleChatOpenAI._generate)
