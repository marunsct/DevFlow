"""Provider settings: masked reads, admin-only writes, and base-URL validation."""

import pytest
from fastapi.testclient import TestClient


def test_credentials_are_never_returned(client, monkeypatch):
    """The endpoint used to return every provider key in plaintext."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-super-secret-value-1234")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value-5678")

    body = client.get("/api/settings").json()
    serialised = str(body)

    assert "sk-super-secret-value-1234" not in serialised
    assert "sk-ant-secret-value-5678" not in serialised
    assert body["openai_api_key_configured"] is True
    assert body["openai_api_key_hint"].endswith("1234")
    assert body["openai_api_key_hint"].startswith("****")


def test_an_unconfigured_credential_reports_as_such(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    body = client.get("/api/settings").json()
    assert body["google_api_key_configured"] is False
    assert body["google_api_key_hint"] is None


def test_a_short_secret_is_fully_masked(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "short")
    assert client.get("/api/settings").json()["openai_api_key_hint"] == "****"


def test_settings_can_be_updated_by_an_admin(client):
    response = client.put(
        "/api/settings",
        json={
            "llm_provider": "openai",
            "openai_base_url": "https://api.openai.com/v1",
            "model_name": "gpt-4o",
        },
    )
    assert response.status_code == 200
    assert response.json()["model_name"] == "gpt-4o"


def test_an_unknown_provider_is_rejected(client):
    response = client.put(
        "/api/settings",
        json={
            "llm_provider": "definitely-not-a-provider",
            "openai_base_url": "https://api.openai.com/v1",
            "model_name": "x",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("bad_url", ["file:///etc/passwd", "gopher://x", "not-a-url", "ftp://host/x"])
def test_a_non_http_base_url_is_rejected(client, bad_url):
    response = client.put(
        "/api/settings",
        json={"llm_provider": "openai", "openai_base_url": bad_url, "model_name": "x"},
    )
    assert response.status_code == 422


def test_the_base_url_host_can_be_restricted(client, monkeypatch):
    """Without this, changing the base URL redirects model traffic - and its
    credentials - to an arbitrary host."""
    monkeypatch.setenv("ALLOWED_MODEL_HOSTS", "api.openai.com,api.anthropic.com")

    blocked = client.put(
        "/api/settings",
        json={
            "llm_provider": "openai",
            "openai_base_url": "https://attacker.example.com/v1",
            "model_name": "x",
        },
    )
    assert blocked.status_code == 422

    allowed = client.put(
        "/api/settings",
        json={
            "llm_provider": "openai",
            "openai_base_url": "https://api.openai.com/v1",
            "model_name": "x",
        },
    )
    assert allowed.status_code == 200


def test_writes_can_be_disabled_entirely(client, monkeypatch):
    monkeypatch.setenv("SETTINGS_READ_ONLY", "true")
    response = client.put(
        "/api/settings",
        json={
            "llm_provider": "openai",
            "openai_base_url": "https://api.openai.com/v1",
            "model_name": "x",
        },
    )
    assert response.status_code == 403


def test_a_non_admin_cannot_change_settings(authed_app):
    from app.server.auth import UserInDB, get_current_active_user, require_admin, require_operator

    operator = UserInDB(
        username="olive", hashed_password="x", disabled=False, role="operator", tenant_id="acme"
    )

    async def _as_operator():
        return operator

    # Restore the real admin gate; keep the others satisfied.
    authed_app.dependency_overrides.pop(require_admin, None)
    for dependency in (get_current_active_user, require_operator):
        authed_app.dependency_overrides[dependency] = _as_operator

    with TestClient(authed_app) as test_client:
        response = test_client.put(
            "/api/settings",
            json={
                "llm_provider": "openai",
                "openai_base_url": "https://api.openai.com/v1",
                "model_name": "x",
            },
        )
    assert response.status_code == 403
