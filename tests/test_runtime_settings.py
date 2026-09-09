"""Provider settings that an administrator changes while the system is running.

These exist because of one report: "I moved the AI to a different URL, changed
it in Settings, and it reverted back on its own." It was not reverting. The
setting was written to the handling process's `os.environ`, the API runs four
gunicorn workers, and each GET was answered by whichever worker the load
balancer picked - so consecutive reads returned whatever each process happened
to hold. The agents, which run in a *different container* entirely, never saw
the change at all.
"""

import pytest

from app.server import runtime_settings


@pytest.fixture(autouse=True)
def clean_settings(test_db):
    runtime_settings.reset_cache()
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    yield
    runtime_settings.clear()
    runtime_settings.clear_secrets()
    runtime_settings.reset_cache()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def test_nothing_stored_means_the_environment_applies():
    assert runtime_settings.overrides() == {}


def test_a_saved_value_comes_back():
    runtime_settings.save({"openai_base_url": "http://new-host:1234/v1"}, actor="admin")

    assert runtime_settings.overrides()["openai_base_url"] == "http://new-host:1234/v1"


def test_saving_again_replaces_rather_than_duplicating():
    runtime_settings.save({"model_name": "first"})
    runtime_settings.save({"model_name": "second"})

    assert runtime_settings.overrides()["model_name"] == "second"


def test_clearing_restores_the_environment():
    runtime_settings.save({"openai_base_url": "http://new-host:1234/v1"})

    runtime_settings.clear()

    assert runtime_settings.overrides() == {}


def test_only_settable_keys_are_accepted():
    """Credentials must never land in a row a database backup copies around."""
    with pytest.raises(ValueError, match="Not a settable key"):
        runtime_settings.save({"openai_api_key": "sk-secret"})


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


def test_a_stored_override_beats_the_deployed_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://old-host:1234/v1")
    runtime_settings.save({"openai_base_url": "http://new-host:5678/v1"})

    assert runtime_settings.effective_settings().openai_base_url == "http://new-host:5678/v1"


def test_the_environment_applies_where_nothing_is_stored(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://deployed:1234/v1")

    assert runtime_settings.effective_settings().openai_base_url == "http://deployed:1234/v1"


def test_an_empty_stored_value_does_not_blank_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "deployed-model")
    runtime_settings.save({"model_name": ""})

    assert runtime_settings.effective_settings().model_name == "deployed-model"


# ---------------------------------------------------------------------------
# Every process sees one answer
# ---------------------------------------------------------------------------


def test_a_second_process_sees_a_change_made_by_the_first(monkeypatch):
    """The bug: four API workers, each holding its own value.

    A fresh cache stands in for a different process - the API's other workers
    and the Celery worker container both read the same row.
    """
    monkeypatch.setenv("OPENAI_BASE_URL", "http://old-host:1234/v1")
    runtime_settings.save({"openai_base_url": "http://new-host:5678/v1"})

    runtime_settings.reset_cache()  # a different process, with nothing cached

    assert runtime_settings.overrides()["openai_base_url"] == "http://new-host:5678/v1"


def test_a_write_is_visible_immediately_in_the_writing_process():
    """The PUT returns the new view, so the page must not need a reload."""
    runtime_settings.overrides()  # warm the cache with the empty state
    runtime_settings.save({"model_name": "just-set"})

    assert runtime_settings.overrides()["model_name"] == "just-set"


# ---------------------------------------------------------------------------
# The store being unavailable must not take the model down
# ---------------------------------------------------------------------------


def test_an_unreachable_store_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://deployed:1234/v1")
    runtime_settings.reset_cache()
    monkeypatch.setattr(
        runtime_settings, "_read_overrides_from_db",
        lambda: (_ for _ in ()).throw(RuntimeError("database is down")),
    )

    assert runtime_settings.overrides() == {}
    assert runtime_settings.effective_settings().openai_base_url == "http://deployed:1234/v1"


def test_an_unreachable_store_is_not_queried_on_every_call(monkeypatch):
    """Otherwise an outage puts a failing query in front of every model call."""
    calls = []

    def _boom():
        calls.append(1)
        raise RuntimeError("database is down")

    runtime_settings.reset_cache()
    monkeypatch.setattr(runtime_settings, "_read_overrides_from_db", _boom)

    for _ in range(5):
        runtime_settings.overrides()

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
#
# These can be set through the API because a self-hosted endpoint that starts
# requiring a key is otherwise unfixable without a redeploy. The direction is
# one-way: written, never read back.


def test_no_credential_stored_means_the_environment_applies(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-deployment")

    assert runtime_settings.secrets() == {}
    assert runtime_settings.effective_settings().openai_api_key == "sk-from-deployment"


def test_a_stored_credential_beats_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-deployment")
    runtime_settings.save_secrets({"openai_api_key": "sk-set-by-admin"}, actor="admin")

    assert runtime_settings.effective_settings().openai_api_key == "sk-set-by-admin"


def test_a_credential_is_encrypted_at_rest():
    """A database dump gets copied around far more casually than an environment."""
    from app.server.auth import get_db_connection

    runtime_settings.save_secrets({"openai_api_key": "sk-plaintext-canary"})

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ciphertext FROM runtime_secrets WHERE key = 'openai_api_key'")
            stored = cur.fetchone()[0]

    assert "sk-plaintext-canary" not in stored
    assert runtime_settings.secrets()["openai_api_key"] == "sk-plaintext-canary"


def test_an_empty_value_removes_a_stored_credential(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-deployment")
    runtime_settings.save_secrets({"openai_api_key": "sk-set-by-admin"})

    runtime_settings.save_secrets({"openai_api_key": ""})

    assert runtime_settings.secrets() == {}
    assert runtime_settings.effective_settings().openai_api_key == "sk-from-deployment"


def test_only_known_credentials_are_accepted():
    with pytest.raises(ValueError, match="Not a settable credential"):
        runtime_settings.save_secrets({"aws_secret_access_key": "nope"})


def test_each_provider_has_its_own_credential():
    runtime_settings.save_secrets({
        "openai_api_key": "sk-openai",
        "anthropic_api_key": "sk-ant",
        "google_api_key": "AIza-google",
    })

    settings = runtime_settings.effective_settings()
    assert settings.openai_api_key == "sk-openai"
    assert settings.anthropic_api_key == "sk-ant"
    assert settings.google_api_key == "AIza-google"


def test_a_second_process_can_read_a_credential_the_first_wrote():
    """The worker container is where the model call actually happens."""
    runtime_settings.save_secrets({"openai_api_key": "sk-shared"})
    runtime_settings.reset_cache()

    assert runtime_settings.secrets()["openai_api_key"] == "sk-shared"


def test_a_rotated_encryption_key_degrades_to_the_environment(monkeypatch, caplog):
    """Unreadable is recoverable and visible; silent plaintext would not be."""
    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", "original-key-material")
    runtime_settings.reset_cache()
    runtime_settings.save_secrets({"openai_api_key": "sk-encrypted-with-old-key"})

    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", "a-completely-different-key")
    runtime_settings.reset_cache()

    with caplog.at_level("ERROR"):
        assert runtime_settings.secrets() == {}
    assert "openai_api_key" in caplog.text
    assert "sk-encrypted-with-old-key" not in caplog.text


def test_an_unreadable_secret_store_does_not_take_the_model_down(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-deployment")
    runtime_settings.reset_cache()
    monkeypatch.setattr(
        runtime_settings, "_read_secrets_from_db",
        lambda: (_ for _ in ()).throw(RuntimeError("database is down")),
    )

    assert runtime_settings.secrets() == {}
    assert runtime_settings.effective_settings().openai_api_key == "sk-from-deployment"
