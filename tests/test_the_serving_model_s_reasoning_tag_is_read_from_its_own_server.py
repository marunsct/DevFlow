"""The serving model's reasoning tag is read from the server that serves the run, not the default setting's.

Measured: the tag was read only from the default model setting's server, so a run pinned to another server never had
one; reply salvage could not keep the reasoning closed, a cut-off planning reply reasoned again in its text (70,000
characters in one), and planning replies ran to 30-46k tokens past their 20k cap.
"""
from __future__ import annotations

import inspect
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


def test_a_run_reads_the_tag_from_the_server_it_is_pinned_to():
    from app.server import tasks

    source = inspect.getsource(tasks.execute_workflow_run)
    assert "with model_pin.as_the_run(run_id):" in source
    assert "capabilities.reasoning_tag_if_missing(" in source
