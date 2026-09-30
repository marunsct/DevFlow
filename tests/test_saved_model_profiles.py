"""A model configuration that was applied can be picked again later.

Switching model meant typing the provider, endpoint, model name, context
window, reply ceiling and thinking settings again - and the window has to
match the loaded model exactly.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

GPT = {
    "llm_provider": "local",
    "openai_base_url": "http://host.docker.internal:1234/v1",
    "model_name": "openai/gpt-oss-20b",
    "model_context_window": 131072,
    "model_max_output_tokens": 20000,
    "thinking_mode": "default",
    "thinking_effort": "medium",
    "execution_mode": "linear",
}
GLM = {**GPT, "model_name": "zai-org/glm-4.7-flash", "model_context_window": 185000}


@pytest.fixture(autouse=True)
def no_profiles(setup_db):
    from app.server.auth import get_db_connection
    from app.server.model_profiles import PROFILES_TABLE_SQL
    from app.server.schema_lock import ensure_table

    def _empty() -> None:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                ensure_table(cur, "model_profiles", PROFILES_TABLE_SQL)
                cur.execute("TRUNCATE TABLE model_profiles")
            conn.commit()

    _empty()
    yield
    _empty()
    # Applying settings stores whatever the payload carried, credentials
    # included; none of it may outlive the test.
    from app.server import runtime_settings

    runtime_settings.clear_secrets()
    runtime_settings.clear(actor="test")


def test_applying_settings_saves_the_model(client) -> None:
    assert client.put("/api/settings", json=GPT).status_code == 200

    [saved] = client.get("/api/settings/models").json()
    assert saved["label"] == "openai/gpt-oss-20b (local)"
    assert saved["model_context_window"] == 131072
    assert saved["model_max_output_tokens"] == 20000
    assert "execution_mode" not in saved


def test_saving_the_same_model_again_updates_it_rather_than_adding_one(client) -> None:
    client.put("/api/settings", json=GPT)
    client.put("/api/settings", json={**GPT, "model_context_window": 65536})

    saved = client.get("/api/settings/models").json()
    assert len(saved) == 1 and saved[0]["model_context_window"] == 65536


def test_each_model_is_kept_most_recent_first(client) -> None:
    client.put("/api/settings", json=GPT)
    client.put("/api/settings", json=GLM)

    labels = [p["label"] for p in client.get("/api/settings/models").json()]
    assert labels == ["zai-org/glm-4.7-flash (local)", "openai/gpt-oss-20b (local)"]


def test_a_credential_is_never_part_of_a_profile(client) -> None:
    client.put("/api/settings", json={**GPT, "openai_api_key": "sk-profile-secret-9876"})

    assert "sk-profile-secret-9876" not in str(client.get("/api/settings/models").json())


def test_a_saved_model_can_be_forgotten(client) -> None:
    client.put("/api/settings", json=GPT)
    [saved] = client.get("/api/settings/models").json()

    assert client.delete(f"/api/settings/models/{saved['id']}").status_code == 204
    assert client.get("/api/settings/models").json() == []
    assert client.delete(f"/api/settings/models/{saved['id']}").status_code == 404


def test_only_an_admin_can_forget_one(authed_app, client) -> None:
    from app.server.auth import UserInDB, get_current_active_user, require_admin, require_operator

    client.put("/api/settings", json=GPT)
    [saved] = client.get("/api/settings/models").json()
    operator = UserInDB(username="olive", hashed_password="x", disabled=False, role="operator", tenant_id="acme")

    async def _as_operator():
        return operator

    authed_app.dependency_overrides.pop(require_admin, None)
    for dependency in (get_current_active_user, require_operator):
        authed_app.dependency_overrides[dependency] = _as_operator
    with TestClient(authed_app) as as_operator:
        assert as_operator.get("/api/settings/models").status_code == 200
        assert as_operator.delete(f"/api/settings/models/{saved['id']}").status_code == 403
