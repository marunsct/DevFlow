"""What the serving model can do is set by the owner, or found - asked of the server, the model and its card - and used.

Whether a model reads images was guessed from its name, and a name the rules
could not place was taken to read none; fixers were never shown the page at
all, only the reviewer. Now each capability is a field the owner can set on
the settings page, found when not set, and `reads_images` decides who sees
the page.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.models import capabilities


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.models import model_guidance

    monkeypatch.setattr(model_guidance, "served_now", lambda: "seen-model")
    monkeypatch.delenv("MODEL_READS_IMAGES", raising=False)


def _completion(content):
    return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}


class _Sees_and_speaks_japanese:
    def __init__(self):
        self.sent = []

    def create(self, **payload):
        self.sent.append(payload)
        content = payload["messages"][-1]["content"]
        if payload.get("tool_choice") == "required":
            return {"choices": [{"finish_reason": "stop", "message": {"content": "Hello!"}}]}
        if isinstance(content, list):
            return _completion("Red.")
        if payload.get("response_format"):
            return _completion(json.dumps({"city": "Paris", "population": 2100000}))
        if "train" in content:
            return {"choices": [{"finish_reason": "stop", "message": {"content": "12:15",
                                                                         "reasoning_content": "9:40 plus 2:35 is 12:15."}}]}
        return _completion("日本の首都は東京です。")


class _Blind:
    def create(self, **payload):
        if isinstance(payload["messages"][-1]["content"], list):
            raise RuntimeError("400 - image input is not supported")
        return _completion("Tokyo is the capital.")


def _model(server):
    return SimpleNamespace(model_name="seen-model", root_client=SimpleNamespace(chat=SimpleNamespace(completions=server)))


def test_the_model_is_asked_what_only_it_can_say():
    found = capabilities.measure(_model(_Sees_and_speaks_japanese()))
    assert found["reads_images"]["value"] is True and "red square" in found["reads_images"]["note"]
    assert found["json_schema_answers"]["value"] is True
    assert found["multilingual"]["value"] is True
    assert found["reasons"]["value"] is True and "24 characters" in found["reasons"]["note"]
    assert found["forced_tool_enforced"]["value"] is False and "answered in text" in found["forced_tool_enforced"]["note"]


def test_a_model_that_refuses_an_image_does_not_read_one():
    found = capabilities.measure(_model(_Blind()))
    assert found["reads_images"]["value"] is False and "refused" in found["reads_images"]["note"]
    assert found["multilingual"]["value"] is False
    assert found["reasons"]["value"] is False  # no reasoning came back


def test_the_model_card_is_read_for_what_the_model_cannot_be_asked(monkeypatch):
    pages = {
        "https://huggingface.co/api/models/org/Vision-12B-A3B-GGUF": {
            "pipeline_tag": "image-text-to-text", "cardData": {"language": ["en", "ja", "fr"]}, "gguf": {"total": 12_100_000_000}},
        "https://huggingface.co/org/Vision-12B-A3B-GGUF/raw/main/README.md": "Use temperature=0.7, top_p: 0.8 and top_k = 20.",
    }
    monkeypatch.setattr(capabilities, "_get", lambda url: pages[url])
    found = capabilities.look_up(["org/Vision-12B-A3B-GGUF"])

    assert found["reads_images"]["value"] is True and found["reads_images"]["source"] == "model card"
    assert found["languages"]["value"] == "en, ja, fr" and found["multilingual"]["value"] is True
    assert found["parameters"]["value"].startswith("12.1B")
    assert found["recommended_sampling"]["value"] == "temperature 0.7, top_p 0.8, top_k 20"


def test_the_owner_s_value_wins_and_none_gives_it_back(monkeypatch):
    monkeypatch.setattr(capabilities, "look_up", lambda names: {})
    monkeypatch.setattr(capabilities, "from_the_server", lambda: {"context_window": capabilities._found(131072, "server", "")})
    capabilities.fill(_model(_Blind()), "seen-model")
    capabilities.set_owner_values("seen-model", {"reads_images": True})

    rows = {r["key"]: r for r in capabilities.resolved("seen-model")}
    assert rows["reads_images"]["value"] is True and rows["reads_images"]["source"] == "owner"
    assert rows["context_window"] == {**rows["context_window"], "value": 131072, "source": "server"}
    assert rows["parameters"]["source"] == "unknown"
    capabilities.set_owner_values("seen-model", {"reads_images": None})
    assert capabilities.value("seen-model", "reads_images") is False
    with pytest.raises(KeyError):
        capabilities.set_owner_values("seen-model", {"no_such": True})


def test_a_model_measured_to_read_images_is_shown_them_whatever_its_name():
    from app.models.vision import reads_images

    settings = SimpleNamespace(model_reads_images="auto", llm_provider="local", model_name="seen-model")
    assert reads_images(settings) is False  # the name says nothing
    capabilities.set_owner_values("seen-model", {"reads_images": True})
    assert reads_images(settings) is True
    assert reads_images(SimpleNamespace(**{**vars(settings), "model_reads_images": "no"})) is False  # the owner's word


def test_a_fixer_on_a_model_that_reads_images_is_shown_the_page(tmp_path, monkeypatch):
    from app.agents import page_screenshots
    from app.models import vision

    monkeypatch.setattr(page_screenshots, "_the_screenshots", lambda root: [("at a phone's width (375px)", b"\x89PNG")])
    request = {"messages": [{"role": "user", "content": "Fix the defect: the form overflows on a phone."}]}

    monkeypatch.setattr(vision, "the_build_model_reads_images", lambda: False)
    assert page_screenshots.with_the_page_for_a_fixer(request, tmp_path) is request

    monkeypatch.setattr(vision, "the_build_model_reads_images", lambda: True)
    shown = page_screenshots.with_the_page_for_a_fixer(request, tmp_path)
    parts = shown["messages"][-1]["content"]
    assert parts[0]["text"].endswith(page_screenshots.FIXER_NOTE.format(shots="at a phone's width (375px)"))
    assert parts[1]["type"] == "image_url"


def test_the_page_shows_every_capability_and_saves_the_owner_s(client) -> None:
    body = client.get("/api/settings/model/capabilities").json()
    assert body["model"] == "seen-model" and {f["key"] for f in body["fields"]} >= {"reads_images", "multilingual"}

    saved = client.put("/api/settings/model/capabilities", json={"values": {"reads_images": True}}).json()
    assert next(f for f in saved["fields"] if f["key"] == "reads_images")["source"] == "owner"
    assert client.put("/api/settings/model/capabilities", json={"values": {"no_such": 1}}).status_code == 404


def test_finding_them_is_refused_while_a_run_is_live(client, monkeypatch) -> None:
    from app.server import settings

    monkeypatch.setattr(settings, "_a_run_is_live", lambda: True)
    assert client.post("/api/settings/model/capabilities/fill").status_code == 409
