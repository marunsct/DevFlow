"""LM Studio's parallel requests share the one loaded window, and the run is held to them.

Measured on one run: seven fixers sent at once to LM Studio, whose model was loaded with 182,528 tokens and
`parallel: 4`, were refused "Context size has been exceeded" in waves for half an hour. The harness read the model
list without the instance's `parallel`, so it took the slots for unknown and the whole window for each request.
"""
from __future__ import annotations

import io
import json

import pytest

from app.graph import workflow
from app.models import server_profile

REAL_READ = server_profile.read

MODELS_V0 = {"data": [{"id": "qwen3.6-35b-a3b-mtp@iq4_nl", "state": "loaded", "max_context_length": 262144,
                       "loaded_context_length": 182528, "quantization": "IQ4_NL"}]}
MODELS_V1 = {"models": [{"key": "qwen3.6-35b-a3b-mtp@iq4_nl", "loaded_instances": [
    {"id": "qwen3.6-35b-a3b-mtp@iq4_nl", "config": {"context_length": 182528, "parallel": 4}}]}]}


@pytest.fixture
def lm_studio(monkeypatch):
    def urlopen(request, timeout=None):
        url = request.full_url
        if url.endswith("/props"):
            body = {"error": "Unexpected endpoint or method. (GET /props)"}
        elif url.endswith("/api/v0/models"):
            body = MODELS_V0
        elif url.endswith("/api/v1/models"):
            body = MODELS_V1
        else:
            raise OSError("no such endpoint")
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(server_profile.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr("app.models.endpoints.reached_from_here", lambda url: (url, {}))
    server_profile._WITHOUT_PROPS.clear()
    yield
    server_profile._WITHOUT_PROPS.clear()


def test_the_instance_s_parallel_requests_are_its_slots_each_with_a_share_of_the_window(lm_studio):
    profile = REAL_READ("http://lmstudio:1234/v1")
    assert profile.slots == 4
    assert profile.slot_context == 45632


def test_a_fan_out_is_sent_no_wider_than_the_slots(lm_studio, monkeypatch):
    profile = REAL_READ("http://lmstudio:1234/v1")
    monkeypatch.setattr(server_profile, "current", lambda: profile)
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "7")
    assert workflow.concurrent_requests() == 4
