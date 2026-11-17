"""The serving model's reasoning tag is read from the server that serves the run, not the default setting's.

Measured: the tag was read only from the default model setting's server, so a run pinned to another server never had
one; reply salvage could not keep the reasoning closed, a cut-off planning reply reasoned again in its text (70,000
characters in one), and planning replies ran to 30-46k tokens past their 20k cap.
"""
from __future__ import annotations

import io
import json

from app.models import capabilities


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_tag_is_read_from_the_given_server_and_kept(monkeypatch):
    asked, kept = [], {}

    def urlopen(request, timeout=None):
        asked.append(request.full_url)
        if request.full_url.endswith("/props"):
            return _Reply(json.dumps({"chat_template": "{{ '<think>' }}"}).encode())
        return _Reply(json.dumps({"tokens": [151667]}).encode())

    monkeypatch.setattr(capabilities.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(capabilities, "value", lambda name, key: kept.get(key))
    monkeypatch.setattr(capabilities, "found_values", lambda name: {})
    import app.models.registry as registry
    monkeypatch.setattr(registry, "merge_into_fitness",
                        lambda name, data: kept.update({"think_tag_tokens": data["capabilities_found"]["think_tag_tokens"]["value"]}))
    import app.models.endpoints as endpoints
    monkeypatch.setattr(endpoints, "reached_from_here", lambda url: (url, {}))

    assert capabilities.reasoning_tag_if_missing("served-model", "http://pinned-server:8888/v1", "k")
    assert asked == ["http://pinned-server:8888/props", "http://pinned-server:8888/tokenize"]
    assert kept["think_tag_tokens"] == "<think> = 151667"


def test_a_run_reads_the_tag_from_the_server_it_is_pinned_to(monkeypatch):
    """A segment reads the tag from the server the run is pinned to, read as the run sees its settings (once checked
    on the source of `execute_workflow_run`)."""
    from unittest import mock

    import app.models as models
    from app.models import model_pin, server_profile
    from app.observability import provenance, transcript
    from app.server import runtime_settings, tasks

    run_id = "run-pinned-tag"
    pinned = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": "http://pinned-server:8888/v1",
              "OPENAI_MODEL": "served-model", "OPENAI_API_KEY": "k"}
    default = {**pinned, "OPENAI_BASE_URL": "http://default-server:1234/v1", "OPENAI_MODEL": "default-model"}
    monkeypatch.setattr(runtime_settings, "effective_environment",
                        lambda *a, **k: pinned if model_pin.current_run_id() == run_id else default)
    monkeypatch.setattr(model_pin, "_DESTINATIONS", {})
    read = []
    monkeypatch.setattr(capabilities, "reasoning_tag_if_missing", lambda *args: read.append(args) or True)
    monkeypatch.setattr(server_profile, "record", lambda *a, **k: None)
    monkeypatch.setattr(models, "build_default_chat_model", mock.Mock(side_effect=RuntimeError("no model here")))
    monkeypatch.setattr(transcript, "record", lambda *a, **k: None)
    monkeypatch.setattr(provenance, "record_the_segment", lambda *a, **k: None)
    runner = mock.MagicMock()
    runner.run_store.is_cancel_requested.return_value = True  # the segment stops right after the tag is read
    with mock.patch.object(tasks, "first_delivery", return_value=True), \
         mock.patch.object(tasks, "_get_runner", return_value=runner), \
         mock.patch.object(tasks, "_record_a_cancellation_nothing_else_will"):
        tasks.execute_workflow_run.run(run_id)

    assert read == [("served-model", "http://pinned-server:8888/v1", "k")]
