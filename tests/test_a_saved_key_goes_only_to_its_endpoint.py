"""A key saved for one endpoint is sent to that endpoint alone, build model and judgement model alike."""

from __future__ import annotations

import pytest

from app.models.roles import judgement_environment
from app.server import runtime_settings
from app.server.runtime_settings import effective_environment, save_endpoint_key

MINE = "http://host.docker.internal:8888/v1"
OTHER = "http://host.docker.internal:1234/v1"
HOSTED = "https://cloud.example/v1"


@pytest.fixture
def clean(test_db):
    def forget():
        runtime_settings.reset_cache()
        runtime_settings.clear()
        runtime_settings.clear_secrets()
        from app.server.auth import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                runtime_settings.ensure_table(cur, "runtime_secrets", runtime_settings.SECRETS_TABLE_SQL)
                cur.execute("DELETE FROM runtime_secrets WHERE key LIKE 'endpoint:%'")
            conn.commit()
        runtime_settings.reset_cache()

    forget()
    yield
    forget()


def _environment(**values):
    return effective_environment(base={"LLM_PROVIDER": "local", **values}, ignore_run=True)


def test_an_endpoint_with_no_key_is_not_sent_the_key_saved_last(clean):
    save_endpoint_key("local", HOSTED, "hosted-key")
    runtime_settings.save_secrets({"openai_api_key": "hosted-key"})
    assert "OPENAI_API_KEY" not in _environment(OPENAI_BASE_URL=OTHER)
    assert _environment(OPENAI_BASE_URL=HOSTED)["OPENAI_API_KEY"] == "hosted-key"


def test_a_key_saved_for_a_hosted_provider_does_not_reach_runs_on_a_local_model(clean):
    save_endpoint_key("anthropic", "https://api.anthropic.com", "anthropic-key")
    runtime_settings.save_secrets({"anthropic_api_key": "anthropic-key"})
    assert "ANTHROPIC_API_KEY" not in _environment(OPENAI_BASE_URL=OTHER)


def test_the_judgement_model_gets_its_own_key_and_no_other(clean):
    save_endpoint_key("local", MINE, "build-key")
    save_endpoint_key("local", HOSTED, "judge-key")
    runtime_settings.save_secrets({"judgement_api_key": "judge-key"})
    found = _environment(OPENAI_BASE_URL=MINE, JUDGEMENT_MODEL="m", JUDGEMENT_BASE_URL=OTHER)
    assert "JUDGEMENT_API_KEY" not in found
    assert judgement_environment(found).get("OPENAI_API_KEY") is None
    found = _environment(OPENAI_BASE_URL=MINE, JUDGEMENT_MODEL="m", JUDGEMENT_BASE_URL=HOSTED)
    assert judgement_environment(found)["OPENAI_API_KEY"] == "judge-key"


def test_a_key_from_the_deployment_still_applies_when_no_endpoint_saved_it(clean):
    save_endpoint_key("local", HOSTED, "hosted-key")
    assert _environment(OPENAI_BASE_URL=OTHER, OPENAI_API_KEY="from-the-deployment")["OPENAI_API_KEY"] == "from-the-deployment"
