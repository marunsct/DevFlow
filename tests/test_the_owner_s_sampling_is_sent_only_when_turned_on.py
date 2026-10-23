"""The sampling the owner turns on for the serving model is sent with every request - and nothing until then.

Sampling is the owner's (ADR-0008): the model card's recommendation was only
shown. A model whose card recommends near-greedy decoding looped; the DRY
repetition sampler cut verbatim loops by about half in its evaluation, and is
off on the server by default. Both are now fields the owner turns on per model
on the settings page; then every request carries them, and a value the
request already has wins.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.models import capabilities


@pytest.fixture(autouse=True)
def _serving(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app.models as models
    from app.models import model_guidance

    from app.models import server_profile

    monkeypatch.setattr(models, "_runtime_settings", lambda: SimpleNamespace(model_name="build-model"))
    monkeypatch.setattr(model_guidance, "served_now", lambda: "served-model")
    # The served name as a worker knows it: from the server's own account of itself.
    monkeypatch.setattr(server_profile, "current", lambda: server_profile.ServerProfile(model="served-model"))
    capabilities.forget_sampling()
    yield
    capabilities.forget_sampling()


def _payload(**kwargs):
    from app.models import CompatibleChatOpenAI

    client = CompatibleChatOpenAI(model="build-model", base_url="http://server/v1", api_key="x", max_retries=0)
    return client._get_request_payload([HumanMessage(content="hi")], **kwargs)


def test_nothing_is_sent_until_the_owner_turns_it_on():
    capabilities.set_owner_values("served-model", {"sampling_to_send": "temperature 0.6, top_k 50"})
    payload = _payload()

    assert "temperature" not in payload and "top_k" not in (payload.get("extra_body") or {})
    rows = {r["key"]: r for r in capabilities.resolved("served-model")}
    assert rows["send_sampling"]["value"] is False and rows["dry_sampler"]["value"] is False


def test_the_sampling_turned_on_is_sent_with_every_request():
    capabilities.set_owner_values("served-model", {
        "send_sampling": True, "sampling_to_send": "temperature 0.6, top_k 50, top_p 0.95, repetition_penalty 1.05"})
    payload = _payload()

    assert payload["temperature"] == 0.6 and payload["top_p"] == 0.95
    assert payload["extra_body"]["top_k"] == 50 and payload["extra_body"]["repeat_penalty"] == 1.05


def test_the_dry_sampler_is_sent_with_its_long_window():
    capabilities.set_owner_values("served-model", {"dry_sampler": True})
    body = _payload()["extra_body"]

    assert body == {"dry_multiplier": 0.8, "dry_base": 1.75, "dry_allowed_length": 2, "dry_penalty_last_n": 1024}


def test_a_value_the_request_already_has_wins():
    capabilities.set_owner_values("served-model", {"send_sampling": True, "sampling_to_send": "temperature 0.6"})
    assert _payload(temperature=0.2)["temperature"] == 0.2


def test_another_model_s_requests_carry_none_of_it():
    from app.models import CompatibleChatOpenAI

    capabilities.set_owner_values("served-model", {"send_sampling": True, "sampling_to_send": "temperature 0.6"})
    other = CompatibleChatOpenAI(model="frontier-model", base_url="http://elsewhere/v1", api_key="x", max_retries=0)
    assert "temperature" not in other._get_request_payload([HumanMessage(content="hi")])


def test_the_parser_takes_known_settings_and_leaves_the_rest():
    parsed = capabilities.parsed_sampling("Use temperature=0.7, top_k: 20 and min_p 0; seed 42, banana 3.")
    assert parsed == {"temperature": ("temperature", 0.7, True), "top_k": ("top_k", 20, False),
                      "min_p": ("min_p", 0.0, False)}


def test_the_card_s_recommendation_is_what_would_be_sent(monkeypatch):
    monkeypatch.setattr(capabilities, "look_up", lambda names: {
        "recommended_sampling": capabilities._found("temperature 0.6, top_k 50", "model card", "")})
    monkeypatch.setattr(capabilities, "from_the_server", lambda: {})
    monkeypatch.setattr(capabilities, "from_what_was_measured", lambda name: {})
    monkeypatch.setattr(capabilities, "measure", lambda model: {})
    capabilities.fill(SimpleNamespace(), "served-model")

    assert capabilities.value("served-model", "sampling_to_send") == "temperature 0.6, top_k 50"
    assert capabilities.value("served-model", "send_sampling") is False
