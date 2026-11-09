"""Saving a model on the settings page keeps the parallel/linear choice made beside it (owner, 2026-11-03).

The toggle sits in the model's section; the model's own save did not send it, then reloaded the stored mode, and a
choice of parallel came back as linear every time.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def _clean_runtime_settings(test_db):
    from app.server import runtime_settings

    runtime_settings.reset_cache()
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    yield
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    runtime_settings.reset_cache()


LOCAL = {"llm_provider": "local", "openai_base_url": "http://host:1234/v1", "model_name": "small-model",
         "model_context_window": 190000}


def test_the_local_model_save_keeps_parallel_and_a_save_without_it_changes_nothing(client, _clean_runtime_settings):
    assert client.put("/api/settings/local", json={**LOCAL, "execution_mode": "parallel"}).json()["execution_mode"] == "parallel"
    assert client.put("/api/settings/local", json=LOCAL).json()["execution_mode"] == "parallel"
    assert client.put("/api/settings/local", json={**LOCAL, "execution_mode": "linear"}).json()["execution_mode"] == "linear"


def test_the_frontier_save_keeps_it_too_even_with_no_model(client, _clean_runtime_settings):
    body = client.put("/api/settings/frontier", json={"no_model": True, "execution_mode": "parallel"}).json()
    assert body["execution_mode"] == "parallel"
