"""A model server with no `/props` is asked for it once, and an LM Studio server is read through its own model list.

Measured: LM Studio answers `GET /props` with 200 and {"error": "Unexpected endpoint or method"}, and logs an ERROR
each time; the harness asked it about once a minute, read the error body as a server profile with nothing in it, and
never learnt the context the loaded model has (LM Studio's `/api/v0/models` names it).
"""
from __future__ import annotations

import io
import json

import pytest

from app.models import server_profile

#: The real reader: the suite's conftest replaces `read` for every test so none reads a developer's own server.
REAL_READ = server_profile.read

LM_MODELS = {"data": [
    {"id": "other-model", "state": "not-loaded", "loaded_context_length": None, "quantization": "Q8_0"},
    {"id": "qwen3.6-35b-a3b-mtp", "state": "loaded", "max_context_length": 262144,
     "loaded_context_length": 183040, "quantization": "IQ4_XS", "type": "vlm"},
]}


@pytest.fixture
def lm_studio(monkeypatch):
    asked: list[str] = []

    def urlopen(request, timeout=None):
        url = request.full_url
        asked.append(url)
        if url.endswith("/props"):
            body = {"error": "Unexpected endpoint or method. (GET /props)"}
        elif url.endswith("/api/v0/models"):
            body = LM_MODELS
        else:
            raise OSError("no such endpoint")
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(server_profile.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr("app.models.endpoints.reached_from_here", lambda url: (url, {}))
    server_profile._WITHOUT_PROPS.clear()
    yield asked
    server_profile._WITHOUT_PROPS.clear()


def test_the_loaded_model_s_context_is_read_from_lm_studio(lm_studio):
    profile = REAL_READ("http://lmstudio:1234/v1")
    assert profile is not None
    assert profile.slot_context == 183040
    assert profile.quantisation == "IQ4_XS"
    assert profile.model == "qwen3.6-35b-a3b-mtp"
    assert profile.slots is None


def test_props_is_asked_once_of_a_server_that_has_none(lm_studio):
    REAL_READ("http://lmstudio:1234/v1")
    REAL_READ("http://lmstudio:1234/v1")
    REAL_READ("http://lmstudio:1234/v1")
    assert sum(url.endswith("/props") for url in lm_studio) == 1


def test_an_error_body_is_not_a_profile(monkeypatch):
    monkeypatch.setattr(server_profile.urllib.request, "urlopen",
                        lambda request, timeout=None: (_ for _ in ()).throw(OSError("down"))
                        if not request.full_url.endswith("/props")
                        else io.BytesIO(b'{"error": "Unexpected endpoint"}'))
    monkeypatch.setattr("app.models.endpoints.reached_from_here", lambda url: (url, {}))
    server_profile._WITHOUT_PROPS.clear()
    assert REAL_READ("http://hosted:9/v1") is None
    server_profile._WITHOUT_PROPS.clear()


def test_a_llama_cpp_server_is_read_as_before(monkeypatch):
    props = {"total_slots": 4, "default_generation_settings": {"n_ctx": 32768}, "model_path": "/m/Qwen-Q6_K.gguf"}
    monkeypatch.setattr(server_profile.urllib.request, "urlopen",
                        lambda request, timeout=None: io.BytesIO(json.dumps(props).encode()))
    monkeypatch.setattr("app.models.endpoints.reached_from_here", lambda url: (url, {}))
    profile = REAL_READ("http://llama:8888/v1")
    assert (profile.slots, profile.slot_context, profile.quantisation) == (4, 32768, "Q6_K")
