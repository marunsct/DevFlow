"""A run pinned to one server is judged by that server's model, not by the one the global settings name.

Measured on one run: the global model read images, the run was pinned to a server whose model does not, a screenshot
was sent, the server answered 400 on every retry, and the run failed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models import capabilities, model_guidance, model_pin, vision

SEES, BLIND = "the-global-model", "the-pinned-model"


def _setup(monkeypatch, pinned):
    monkeypatch.setattr(model_guidance, "served_now", lambda: SEES)
    monkeypatch.setattr(capabilities, "value", lambda name, field: {SEES: True, BLIND: False}.get(name))
    monkeypatch.setattr(model_pin, "pinned_snapshot", lambda: pinned)


def test_a_pinned_run_is_not_given_the_global_model_s_sight(monkeypatch):
    _setup(monkeypatch, {"MODEL_NAME": BLIND})
    assert vision.reads_images(SimpleNamespace(model_name=BLIND, llm_provider="local")) is False


def test_a_pinned_model_never_measured_is_not_given_it_either(monkeypatch):
    _setup(monkeypatch, {"MODEL_NAME": "never-measured"})
    assert vision.reads_images(SimpleNamespace(model_name="never-measured", llm_provider="local")) is False


def test_an_unpinned_run_still_reads_the_served_model(monkeypatch):
    _setup(monkeypatch, None)
    assert vision.reads_images(SimpleNamespace(model_name="anything", llm_provider="local")) is True
