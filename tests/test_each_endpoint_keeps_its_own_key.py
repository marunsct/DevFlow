"""Each endpoint keeps its own API key; one provider with several models shares one.

A key used to belong to a provider: one OpenAI-compatible key for every
OpenAI-compatible server. On one run's model change the local server, a hosted
preview API and a cloud API were all "OpenAI-compatible", and switching to the
cloud API kept sending the preview API's key - every call refused with 401.
A key typed in the settings is now kept for the endpoint (provider and address)
it was typed for, and chosen whenever that endpoint is.
"""

from __future__ import annotations

import pytest

from app.server import runtime_settings
from app.server.runtime_settings import effective_environment, endpoint_id, judgement_endpoint, save_endpoint_key

LOCAL = "http://host.docker.internal:1234/v1"
CLOUD = "https://cloud.example/compatible-mode/v1"


@pytest.fixture
def clean(test_db):
    runtime_settings.reset_cache()
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    _forget_endpoint_keys()
    yield
    _forget_endpoint_keys()
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    runtime_settings.reset_cache()


def _forget_endpoint_keys():
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            runtime_settings.ensure_table(cur, "runtime_secrets", runtime_settings.SECRETS_TABLE_SQL)
            cur.execute("DELETE FROM runtime_secrets WHERE key LIKE 'endpoint:%'")
        conn.commit()


def test_an_endpoint_is_its_provider_and_address():
    assert endpoint_id("local", LOCAL) == endpoint_id("LOCAL", LOCAL.upper() + "/")
    assert endpoint_id("local", LOCAL) != endpoint_id("local", CLOUD)
    assert endpoint_id("openai", "") != endpoint_id("anthropic", "")


def test_switching_endpoints_switches_keys(clean):
    save_endpoint_key("local", LOCAL, "local-key")
    save_endpoint_key("local", CLOUD, "cloud-key")
    base = {"LLM_PROVIDER": "local", "OPENAI_API_KEY": "shared-key"}

    assert effective_environment({**base, "OPENAI_BASE_URL": LOCAL})["OPENAI_API_KEY"] == "local-key"
    assert effective_environment({**base, "OPENAI_BASE_URL": CLOUD})["OPENAI_API_KEY"] == "cloud-key"
    other = "https://elsewhere.example/v1"
    assert effective_environment({**base, "OPENAI_BASE_URL": other})["OPENAI_API_KEY"] == "shared-key", (
        "an endpoint with no key of its own falls back to the provider's"
    )


def test_the_judgement_model_on_another_endpoint_uses_that_endpoint_s_key(clean):
    save_endpoint_key("local", LOCAL, "local-key")
    save_endpoint_key("local", CLOUD, "cloud-key")

    env = effective_environment({
        "LLM_PROVIDER": "local", "OPENAI_BASE_URL": LOCAL,
        "JUDGEMENT_MODEL": "frontier", "JUDGEMENT_BASE_URL": CLOUD,
    })

    assert env["OPENAI_API_KEY"] == "local-key"
    assert env["JUDGEMENT_API_KEY"] == "cloud-key"


def test_one_provider_with_two_models_shares_one_key(clean):
    """Frontier and build model from one account: the same endpoint, so the same key."""
    save_endpoint_key("local", CLOUD, "cloud-key")

    for judgement_base in ("", CLOUD, CLOUD + "/"):
        env = effective_environment({
            "LLM_PROVIDER": "local", "OPENAI_BASE_URL": CLOUD, "OPENAI_MODEL": "fast-model",
            "JUDGEMENT_MODEL": "frontier-model", "JUDGEMENT_BASE_URL": judgement_base,
        })
        assert env["OPENAI_API_KEY"] == "cloud-key"
        assert env["JUDGEMENT_API_KEY"] == "cloud-key", judgement_base


def test_the_judgement_endpoint_is_found_as_the_model_is_built():
    assert judgement_endpoint({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": LOCAL}) == ("local", LOCAL)
    assert judgement_endpoint({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": LOCAL, "JUDGEMENT_PROVIDER": "anthropic"}) == ("anthropic", "")


def test_a_removed_key_stops_being_used(clean):
    save_endpoint_key("local", LOCAL, "local-key")
    save_endpoint_key("local", LOCAL, "")

    assert effective_environment({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": LOCAL, "OPENAI_API_KEY": "shared"})["OPENAI_API_KEY"] == "shared"


def test_the_settings_view_says_which_endpoints_have_a_key(clean):
    from app.server.settings import _endpoints_with_keys

    save_endpoint_key("local", CLOUD, "cloud-key")

    assert _endpoints_with_keys({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": CLOUD}) == {
        "endpoint_key_saved": True, "judgement_endpoint_key_saved": False,
    }
    assert _endpoints_with_keys({
        "LLM_PROVIDER": "local", "OPENAI_BASE_URL": LOCAL, "JUDGEMENT_MODEL": "f", "JUDGEMENT_BASE_URL": CLOUD,
    }) == {"endpoint_key_saved": False, "judgement_endpoint_key_saved": True}


def test_endpoint_keys_never_leak_into_the_provider_credentials(clean):
    save_endpoint_key("local", CLOUD, "cloud-key")

    assert all(not key.startswith("endpoint:") for key in runtime_settings.secrets(refresh=True))
