"""Whether an LM Studio model reads images is taken from LM Studio's own report of it, not assumed (LF.1569).

LM Studio's `/api/v0/models` gives each model a `type` - `vlm` when it holds a vision part for it, `llm` when not -
and `/api/v1/models` gives `capabilities.vision`. The profile read neither, so it said nothing, and the model card's
word stood: on a llama.cpp server the same gap sent pages to a model with no vision part and every fix call was
refused ("image input is not supported"). The bodies below are shaped as LM Studio's server writes them (its daemon's
model-list handlers: `id, object, type, publisher, arch, compatibility_type, quantization, state,
max_context_length, loaded_context_length, capabilities` for v0; `type, key, ..., loaded_instances, capabilities:
{vision, trained_for_tool_use}` for v1).
"""
from __future__ import annotations

import io
import json

import pytest

from app.models import server_profile

#: The real reader: the suite's conftest replaces `read` for every test so none reads a developer's own server.
REAL_READ = server_profile.read


def _v0(model_type: str | None) -> dict:
    entry = {"id": "qwen3.6-35b-a3b-mtp@iq4_nl", "object": "model", "publisher": "lmstudio-community",
             "arch": "qwen3moe", "compatibility_type": "gguf", "quantization": "IQ4_NL", "state": "loaded",
             "max_context_length": 262144, "loaded_context_length": 182528, "capabilities": ["tool_use"]}
    return {"object": "list", "data": [{**entry, "type": model_type} if model_type else entry]}


def _v1(vision: bool) -> dict:
    return {"models": [{"type": "llm", "publisher": "lmstudio-community", "key": "qwen3.6-35b-a3b-mtp@iq4_nl",
                        "display_name": "Qwen3.6 35B A3B", "loaded_instances": [
                            {"id": "qwen3.6-35b-a3b-mtp@iq4_nl", "config": {"context_length": 182528, "parallel": 4}}],
                        "capabilities": {"vision": vision, "trained_for_tool_use": True}}]}


@pytest.fixture
def lm_studio(monkeypatch):
    bodies: dict[str, dict] = {}

    def urlopen(request, timeout=None):
        url = request.full_url
        if url.endswith("/props"):
            body = {"error": "Unexpected endpoint or method. (GET /props)"}
        elif url.endswith("/api/v0/models"):
            body = bodies["v0"]
        elif url.endswith("/api/v1/models"):
            body = bodies["v1"]
        else:
            raise OSError("no such endpoint")
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(server_profile.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr("app.models.endpoints.reached_from_here", lambda url: (url, {}))
    server_profile._WITHOUT_PROPS.clear()
    yield bodies
    server_profile._WITHOUT_PROPS.clear()


@pytest.mark.parametrize(("model_type", "reads"), [("llm", False), ("vlm", True)])
def test_the_model_s_type_says_whether_it_reads_images(lm_studio, model_type, reads):
    lm_studio.update(v0=_v0(model_type), v1={"models": []})

    assert REAL_READ("http://lmstudio:1234/v1").reads_images is reads


def test_without_a_type_the_model_s_capabilities_say_it(lm_studio):
    lm_studio.update(v0=_v0(None), v1=_v1(vision=False))

    assert REAL_READ("http://lmstudio:1234/v1").reads_images is False


def test_a_server_that_says_nothing_of_vision_is_not_taken_to_say_no(lm_studio):
    lm_studio.update(v0=_v0(None), v1={"models": []})

    assert REAL_READ("http://lmstudio:1234/v1").reads_images is None
