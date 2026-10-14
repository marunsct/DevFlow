"""Provider settings: masked reads, admin-only writes, and base-URL validation."""

import os

import pytest
from fastapi import HTTPException
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


# ---------------------------------------------------------------------------
# A change must hold for the whole system, not for one process
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_runtime_settings(test_db):
    from app.server import runtime_settings

    runtime_settings.reset_cache()
    runtime_settings.clear()
    yield
    runtime_settings.clear()
    runtime_settings.reset_cache()


def test_a_saved_setting_survives_a_process_that_never_saw_the_write(client, monkeypatch):
    """The reported bug: four gunicorn workers, each with its own value.

    Clearing the cache stands in for one of the *other* API workers - or the
    Celery worker container - answering the next request.
    """
    from app.server import runtime_settings

    monkeypatch.setenv("OPENAI_BASE_URL", "http://old-host:1234/v1")

    client.put("/api/settings", json={
        "llm_provider": "local",
        "openai_base_url": "http://new-host:5678/v1",
        "model_name": "qwen-30b",
    })
    runtime_settings.reset_cache()

    body = client.get("/api/settings").json()
    assert body["openai_base_url"] == "http://new-host:5678/v1"
    assert body["model_name"] == "qwen-30b"


def test_repeated_reads_agree_with_each_other(client, monkeypatch):
    """Consecutive GETs used to return different values as the load balancer
    rotated between workers holding different environments."""
    from app.server import runtime_settings

    monkeypatch.setenv("OPENAI_BASE_URL", "http://old-host:1234/v1")
    client.put("/api/settings", json={
        "llm_provider": "local",
        "openai_base_url": "http://new-host:5678/v1",
        "model_name": "qwen-30b",
    })

    seen = set()
    for _ in range(6):
        runtime_settings.reset_cache()
        seen.add(client.get("/api/settings").json()["openai_base_url"])

    assert seen == {"http://new-host:5678/v1"}


def test_the_write_does_not_mutate_the_process_environment(client, monkeypatch):
    """Writing to os.environ is what made the change invisible elsewhere."""
    monkeypatch.setenv("OPENAI_BASE_URL", "http://old-host:1234/v1")

    client.put("/api/settings", json={
        "llm_provider": "local",
        "openai_base_url": "http://new-host:5678/v1",
        "model_name": "qwen-30b",
    })

    assert os.environ["OPENAI_BASE_URL"] == "http://old-host:1234/v1"


def test_the_agent_model_is_built_from_the_saved_setting(client, monkeypatch):
    """The point of the whole change: the worker calls the corrected URL."""
    monkeypatch.setenv("OPENAI_BASE_URL", "http://old-host:1234/v1")
    client.put("/api/settings", json={
        "llm_provider": "local",
        "openai_base_url": "http://new-host:5678/v1",
        "model_name": "qwen-30b",
    })

    from app.server.runtime_settings import effective_settings

    assert effective_settings().openai_base_url == "http://new-host:5678/v1"


# ---------------------------------------------------------------------------
# Credentials: settable, never readable
# ---------------------------------------------------------------------------


def _provider_body(**extra):
    body = {
        "llm_provider": "openai",
        "openai_base_url": "https://api.example.com/v1",
        "model_name": "gpt-4o",
    }
    body.update(extra)
    return body


def test_an_admin_can_set_a_credential(client):
    from app.server.runtime_settings import secrets

    response = client.put("/api/settings", json=_provider_body(openai_api_key="sk-real-key"))

    assert response.status_code == 200
    assert secrets()["openai_api_key"] == "sk-real-key"


def test_a_set_credential_is_never_returned(client):
    response = client.put("/api/settings", json=_provider_body(openai_api_key="sk-real-key"))

    body = response.text
    assert "sk-real-key" not in body
    assert response.json()["openai_api_key_configured"] is True
    assert response.json()["openai_api_key_hint"] == "****-key"


def test_reading_settings_never_returns_a_credential(client):
    client.put("/api/settings", json=_provider_body(openai_api_key="sk-real-key"))

    assert "sk-real-key" not in client.get("/api/settings").text


def test_an_omitted_credential_leaves_the_stored_one_alone(client):
    from app.server.runtime_settings import secrets

    client.put("/api/settings", json=_provider_body(openai_api_key="sk-real-key"))
    client.put("/api/settings", json=_provider_body(model_name="gpt-4o-mini"))

    assert secrets()["openai_api_key"] == "sk-real-key"


def test_an_empty_credential_removes_it(client):
    from app.server.runtime_settings import secrets

    client.put("/api/settings", json=_provider_body(openai_api_key="sk-real-key"))
    client.put("/api/settings", json=_provider_body(openai_api_key="   "))

    assert "openai_api_key" not in secrets()


def test_a_resubmitted_mask_is_not_stored_as_a_key(client):
    """The UI shows `****abcd`; pasting it back must not become the key."""
    from app.server.runtime_settings import secrets

    client.put("/api/settings", json=_provider_body(openai_api_key="sk-real-key"))
    client.put("/api/settings", json=_provider_body(openai_api_key="****-key"))

    assert secrets()["openai_api_key"] == "sk-real-key"


def test_a_credential_with_control_characters_is_rejected(client):
    response = client.put("/api/settings", json=_provider_body(openai_api_key="sk-bad\nInjected: header"))

    assert response.status_code == 422


def test_the_audit_row_names_the_credential_but_not_its_value(client):
    from app.server.auth import get_db_connection

    client.put("/api/settings", json=_provider_body(openai_api_key="sk-audit-canary"))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT detail::text FROM audit_log WHERE action = 'settings.update' "
                "ORDER BY occurred_at DESC LIMIT 1"
            )
            detail = cur.fetchone()[0]

    assert "openai_api_key" in detail
    assert "sk-audit-canary" not in detail


def test_a_non_admin_cannot_set_a_credential(authed_app):
    from app.server.auth import require_admin

    async def _forbidden():
        raise HTTPException(status_code=403, detail="Admin role required.")

    authed_app.dependency_overrides[require_admin] = _forbidden
    with TestClient(authed_app) as operator:
        response = operator.put("/api/settings", json=_provider_body(openai_api_key="sk-nope"))

    assert response.status_code == 403


def test_an_unknown_field_is_refused(client):
    """extra="forbid" stops a typo silently doing nothing."""
    response = client.put("/api/settings", json=_provider_body(aws_secret_access_key="nope"))

    assert response.status_code == 422


def test_a_save_without_the_delivery_mode_keeps_the_stored_one(client):
    """A page loaded before the delivery mode existed sent no value, and a
    default saved "thorough" over the deployment's "fast" for an owner who had
    only changed the model's address."""
    from app.server import runtime_settings

    base = {"llm_provider": "openai", "openai_base_url": "https://api.openai.com/v1", "model_name": "gpt-4o"}
    assert client.put("/api/settings", json={**base, "delivery_mode": "fast"}).status_code == 200
    runtime_settings.reset_cache()

    assert client.put("/api/settings", json=base).status_code == 200
    runtime_settings.reset_cache()

    assert runtime_settings.effective_environment().get("DELIVERY_MODE") == "fast"
    assert client.get("/api/settings").json()["delivery_mode"] == "fast"
