"""The internet lookup sources' keys are set on the admin page, stored as the provider keys are (plan WL.3).

A free Stack Apps key raises Stack Exchange's limit from 300 requests a day to 10,000, and a GitHub token raises the
issue search's; before, either could be set only in the deployment's environment. A key saved here is encrypted with
the other credentials, shown masked, sent only to its own source, and never laid into a model's environment.
"""
from __future__ import annotations

import pytest

from app.server import runtime_settings
from app.tools import lookups


@pytest.fixture(autouse=True)
def clean_secrets(test_db, monkeypatch):
    monkeypatch.delenv("STACKEXCHANGE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("SWITCH_OVERRIDES_FROM_SETTINGS", "on")
    runtime_settings.reset_cache()
    runtime_settings.clear_secrets()
    yield
    runtime_settings.clear_secrets()
    runtime_settings.reset_cache()


def _sent_by_a_lookup() -> list[tuple[str, dict[str, str]]]:
    sent: list[tuple[str, dict[str, str]]] = []

    def fetch(url, headers):
        sent.append((url, headers))
        return 200, '{"items": []}'

    lookups.look_up("TypeError: Argument #2 must be of type callable", "PHP", fetch=fetch)
    return sent


def test_saved_keys_are_shown_masked_and_reach_only_their_sources(client):
    saved = client.put("/api/settings/lookup-keys",
                       json={"stackexchange_key": "stack-key-canary-1234", "github_token": "ghp_canary_token_9876"})

    assert saved.status_code == 200
    shown = client.get("/api/settings/lookup-keys").json()
    assert (shown["stackexchange_key_hint"], shown["github_token_hint"]) == ("****1234", "****9876")
    assert shown["stackexchange_key_configured"] and shown["github_token_configured"]
    assert "canary" not in saved.text + str(shown)
    sent = _sent_by_a_lookup()
    stack_exchange = [url for url, _ in sent if "api.stackexchange.com" in url]
    github = [headers for url, headers in sent if "api.github.com" in url]
    assert stack_exchange and all("key=stack-key-canary-1234" in url for url in stack_exchange)
    assert github == [{"Accept": "application/vnd.github+json", "Authorization": "Bearer ghp_canary_token_9876"}]


def test_the_deployment_s_key_beats_a_saved_one_and_an_empty_value_deletes_it(client, monkeypatch):
    client.put("/api/settings/lookup-keys", json={"stackexchange_key": "saved-key-0000"})
    monkeypatch.setenv("STACKEXCHANGE_KEY", "deployed-key-1111")

    assert all("key=deployed-key-1111" in url for url, _ in _sent_by_a_lookup() if "stackexchange" in url)
    assert client.get("/api/settings/lookup-keys").json()["stackexchange_key_from_environment"] is True

    monkeypatch.delenv("STACKEXCHANGE_KEY")
    client.put("/api/settings/lookup-keys", json={"stackexchange_key": ""})

    assert client.get("/api/settings/lookup-keys").json()["stackexchange_key_configured"] is False
    assert not any("key=" in url for url, _ in _sent_by_a_lookup())


def test_a_saved_lookup_key_is_never_in_a_model_s_environment():
    runtime_settings.save_secrets({"github_token": "ghp_canary_token_9876", "stackexchange_key": "stack-key-1234"})

    environment = runtime_settings.effective_environment(base={})

    assert "GITHUB_TOKEN" not in environment and "STACKEXCHANGE_KEY" not in environment

