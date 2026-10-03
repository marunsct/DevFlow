"""Provider settings an administrator can change while the system is running.

Why these cannot live in ``os.environ``
--------------------------------------
The settings page used to write straight to the handling process's environment.
That looks correct in a single-process dev server and is wrong in every real
deployment, because the change reaches exactly one process:

*   The API runs under gunicorn with ``WEB_CONCURRENCY`` workers (4 by default).
    A PUT lands on one of them. The next GET is load-balanced to a different
    one, which still holds the old value - so the page appears to "revert on its
    own", and repeated reads flip between however many distinct values the
    workers happen to be holding.
*   Worse, the agents do not run in the API container at all. They run in the
    Celery worker, a separate container with its own environment, which never
    observes the change under any circumstances. So a corrected model URL could
    never take effect even if every API worker agreed on it.

Storing them in Postgres - the store every process already shares - makes one
answer true for the whole system, and makes it survive a restart.

Precedence
----------
A stored override beats the deployed environment. An administrator changing a
setting through the UI is an explicit, audited act, and a deployment that wants
its configuration to be final sets ``SETTINGS_READ_ONLY`` instead, which refuses
the write outright rather than accepting it and ignoring it.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Mapping

from app.server.schema_lock import ensure_table

logger = logging.getLogger(__name__)

SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runtime_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
)
"""

SECRETS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runtime_secrets (
    key        TEXT PRIMARY KEY,
    ciphertext TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
)
"""
"""Credentials live in their own table, encrypted.

Separate from `runtime_settings` on purpose: a `SELECT *` while debugging
provider configuration should not return credentials at all, even as
ciphertext, and the two tables can be granted separately.

Encrypted because the threat here is not someone with a shell on the box - they
have the environment anyway - it is that database dumps get copied to laptops,
ticket attachments and staging environments far more casually than container
environments ever do.
"""

# Credentials an administrator may set at runtime, mapped to the environment
# variable each overrides.
SETTABLE_SECRETS: dict[str, str] = {
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    # The judgement model's own key, when it is served somewhere the default
    # model is not. See `app.models.roles`.
    "judgement_api_key": "JUDGEMENT_API_KEY",
}

# Settings an administrator may change at runtime, mapped to the environment
# variable each one overrides. Credentials are deliberately absent: they belong
# in the secret store or the process environment, never in a row that a
# database backup copies around.
SETTABLE_KEYS: dict[str, str] = {
    "llm_provider": "LLM_PROVIDER",
    "openai_base_url": "OPENAI_BASE_URL",
    "model_name": "OPENAI_MODEL",
    # The model's context window, in tokens. Every context budget in the
    # pipeline is derived from it (see `app.agents.context_budget`), so it
    # belongs beside the model it describes rather than in a deploy file: the
    # two change together, and a window left behind after a model change is how
    # every overflow in this repository's history began.
    "model_context_window": "MODEL_CONTEXT_WINDOW",
    # Reasoning models can deliberate before answering. Kept beside the model
    # because support is a property of the model, not of the deployment: a
    # window and a thinking budget both change when the model does.
    # The longest single reply. It shares one window with the conversation, so
    # raising it shrinks the room the conversation has - `context_budget`
    # re-derives every other limit from what it leaves behind.
    "model_max_output_tokens": "MODEL_MAX_OUTPUT_TOKENS",
    "thinking_mode": "MODEL_THINKING_MODE",
    "thinking_effort": "MODEL_THINKING_EFFORT",
    # Whether a sprint's specialists run one after another or all at once.
    # `specialist_dispatch_node` reads it through `load_settings()`, the
    # settings page offers it as a toggle, and `SettingsPayload` carries it -
    # and it was missing from here, which is the one list that decides whether
    # a write is allowed at all. `save()` raised
    # `ValueError: Not a settable key: execution_mode` for every attempt, so
    # the toggle could not be turned on and fourteen settings tests that post
    # a whole payload failed with it.
    "execution_mode": "EXECUTION_MODE",
    # A second model for the stages that judge rather than produce: the
    # architect, QA, the reviews, the test rounds and the fixes. Empty means
    # every stage uses the model above. See `app.models.roles`.
    "judgement_provider": "JUDGEMENT_PROVIDER",
    "judgement_base_url": "JUDGEMENT_BASE_URL",
    "judgement_model_name": "JUDGEMENT_MODEL",
    "judgement_context_window": "JUDGEMENT_CONTEXT_WINDOW",
}

CACHE_TTL_SECONDS = float(os.environ.get("SETTINGS_CACHE_TTL", "5"))
"""How long a process may reuse the overrides it last read.

`load_settings` is called on every agent construction - once per node, per
invoke - so reading a row each time would put a query in front of every model
call. Five seconds keeps that cost negligible while making a settings change
visible across every worker almost immediately.
"""

_cache: dict[str, str] = {}
_cache_expires_at = 0.0
_cache_lock = threading.Lock()


def _read_overrides_from_db() -> dict[str, str]:
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_settings", SETTINGS_TABLE_SQL)
            cur.execute("SELECT key, value FROM runtime_settings")
            rows = cur.fetchall()
        conn.commit()
    return {key: value for key, value in rows if key in SETTABLE_KEYS}


def overrides(*, refresh: bool = False) -> dict[str, str]:
    """Stored overrides, cached briefly per process.

    Never raises. If the database is unreachable the deployed environment is
    still a usable configuration, and failing a model call because the *settings
    table* was unavailable would turn a cosmetic outage into a total one.
    """
    global _cache, _cache_expires_at

    now = time.monotonic()
    if not refresh and now < _cache_expires_at:
        return dict(_cache)

    try:
        fresh = _read_overrides_from_db()
    except Exception:  # noqa: BLE001 - see docstring
        logger.warning("Could not read runtime settings; using the environment", exc_info=True)
        # Push the retry out by one TTL rather than querying on every call
        # while the database is down.
        with _cache_lock:
            _cache_expires_at = now + CACHE_TTL_SECONDS
        return dict(_cache)

    with _cache_lock:
        _cache = fresh
        _cache_expires_at = now + CACHE_TTL_SECONDS
    return dict(fresh)


def save(values: Mapping[str, str], *, actor: str = "unknown") -> None:
    """Persist overrides and make them visible to this process immediately."""
    unknown = set(values) - set(SETTABLE_KEYS)
    if unknown:
        raise ValueError(f"Not a settable key: {', '.join(sorted(unknown))}")

    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_settings", SETTINGS_TABLE_SQL)
            for key, value in values.items():
                cur.execute(
                    """
                    INSERT INTO runtime_settings (key, value, updated_at, updated_by)
                    VALUES (%s, %s, NOW(), %s)
                    ON CONFLICT (key) DO UPDATE
                       SET value = EXCLUDED.value,
                           updated_at = EXCLUDED.updated_at,
                           updated_by = EXCLUDED.updated_by
                    """,
                    (key, value, actor),
                )
        conn.commit()

    overrides(refresh=True)


def clear(keys: list[str] | None = None, *, actor: str = "unknown") -> None:
    """Drop stored overrides so the deployed environment applies again."""
    from app.server.auth import get_db_connection

    targets = keys if keys is not None else list(SETTABLE_KEYS)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_settings", SETTINGS_TABLE_SQL)
            cur.execute("DELETE FROM runtime_settings WHERE key = ANY(%s)", (targets,))
        conn.commit()
    overrides(refresh=True)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

_secret_cache: dict[str, str] = {}
_secret_cache_expires_at = 0.0


def _encryption_key() -> bytes:
    """The Fernet key used to encrypt stored credentials.

    `SETTINGS_ENCRYPTION_KEY` is the intended source. It falls back to deriving
    one from the JWT secret so the feature works on an existing deployment
    without a new variable - at the cost that rotating that secret makes stored
    credentials unreadable and they have to be re-entered. That is a
    recoverable, visible failure, which is the right trade against silently
    storing credentials in plaintext.

    In development with no `JWT_SECRET_KEY`, the JWT secret is ephemeral per
    process, so stored credentials do not survive a restart. Set
    `SETTINGS_ENCRYPTION_KEY` to make them durable.
    """
    import base64
    import hashlib

    configured = os.environ.get("SETTINGS_ENCRYPTION_KEY", "").strip()
    if configured:
        material = configured.encode("utf-8")
    else:
        # `SECRET_KEY`, the value resolved once at import - not `_load_secret_key()`,
        # which mints a *fresh* ephemeral key on every call when ENV is a
        # development value. Calling it per operation encrypted and decrypted
        # with different keys, so nothing written could ever be read back.
        from app.server.auth import SECRET_KEY

        material = f"settings-encryption:{SECRET_KEY}".encode("utf-8")

    # Fernet wants 32 url-safe base64 bytes; a hash gives a fixed-width key from
    # material of any length.
    return base64.urlsafe_b64encode(hashlib.sha256(material).digest())


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(_encryption_key())


def _read_secrets_from_db() -> dict[str, str]:
    from cryptography.fernet import InvalidToken

    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_secrets", SECRETS_TABLE_SQL)
            cur.execute("SELECT key, ciphertext FROM runtime_secrets")
            rows = cur.fetchall()
        conn.commit()

    box = _fernet()
    decrypted: dict[str, str] = {}
    for key, ciphertext in rows:
        if key not in SETTABLE_SECRETS:
            continue
        try:
            decrypted[key] = box.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Almost always a rotated encryption key. Name the credential, never
            # the value, and carry on with the others.
            logger.error(
                "Stored credential '%s' cannot be decrypted; the encryption key has "
                "probably changed. Re-enter it in Settings.", key,
            )
    return decrypted


def secrets(*, refresh: bool = False) -> dict[str, str]:
    """Stored credentials, cached briefly per process. Never raises."""
    global _secret_cache, _secret_cache_expires_at

    now = time.monotonic()
    if not refresh and now < _secret_cache_expires_at:
        return dict(_secret_cache)

    try:
        fresh = _read_secrets_from_db()
    except Exception:  # noqa: BLE001 - the environment is still a valid config
        logger.warning("Could not read stored credentials; using the environment", exc_info=True)
        with _cache_lock:
            _secret_cache_expires_at = now + CACHE_TTL_SECONDS
        return dict(_secret_cache)

    with _cache_lock:
        _secret_cache = fresh
        _secret_cache_expires_at = now + CACHE_TTL_SECONDS
    return dict(fresh)


def save_secrets(values: Mapping[str, str], *, actor: str = "unknown") -> list[str]:
    """Store credentials encrypted. Returns the names that changed.

    An empty value deletes the stored credential, so the deployed environment
    applies again - that is how an administrator undoes a mistake without
    needing database access.
    """
    unknown = set(values) - set(SETTABLE_SECRETS)
    if unknown:
        raise ValueError(f"Not a settable credential: {', '.join(sorted(unknown))}")

    from app.server.auth import get_db_connection

    box = _fernet()
    changed: list[str] = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_secrets", SECRETS_TABLE_SQL)
            for key, value in values.items():
                if value == "":
                    cur.execute("DELETE FROM runtime_secrets WHERE key = %s", (key,))
                    changed.append(key)
                    continue
                cur.execute(
                    """
                    INSERT INTO runtime_secrets (key, ciphertext, updated_at, updated_by)
                    VALUES (%s, %s, NOW(), %s)
                    ON CONFLICT (key) DO UPDATE
                       SET ciphertext = EXCLUDED.ciphertext,
                           updated_at = EXCLUDED.updated_at,
                           updated_by = EXCLUDED.updated_by
                    """,
                    (key, box.encrypt(value.encode("utf-8")).decode("utf-8"), actor),
                )
                changed.append(key)
        conn.commit()

    secrets(refresh=True)
    return changed


def clear_secrets(keys: list[str] | None = None) -> None:
    """Delete stored credentials so the deployed environment applies again."""
    from app.server.auth import get_db_connection

    targets = keys if keys is not None else list(SETTABLE_SECRETS)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_secrets", SECRETS_TABLE_SQL)
            cur.execute("DELETE FROM runtime_secrets WHERE key = ANY(%s)", (targets,))
        conn.commit()
    secrets(refresh=True)


def reset_cache() -> None:
    """Forget the cached overrides. For tests and for an explicit refresh."""
    global _cache, _cache_expires_at, _secret_cache, _secret_cache_expires_at
    with _cache_lock:
        _cache = {}
        _cache_expires_at = 0.0
        _secret_cache = {}
        _secret_cache_expires_at = 0.0


def effective_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment with stored overrides layered on top."""
    environment = dict(base if base is not None else os.environ)
    for key, value in overrides().items():
        if value:
            environment[SETTABLE_KEYS[key]] = value
    for key, value in secrets().items():
        if value:
            environment[SETTABLE_SECRETS[key]] = value
    return environment


def effective_settings() -> Any:
    """`load_settings`, but honouring anything an administrator has changed.

    This is what every model-building path should call. `load_settings` itself
    stays a pure function of the environment it is handed, so tests and the CLI
    can keep using it without a database.
    """
    from app.config import load_settings

    return load_settings(effective_environment())


__all__ = [
    "CACHE_TTL_SECONDS",
    "SECRETS_TABLE_SQL",
    "SETTABLE_KEYS",
    "SETTABLE_SECRETS",
    "SETTINGS_TABLE_SQL",
    "clear",
    "clear_secrets",
    "effective_environment",
    "effective_settings",
    "overrides",
    "reset_cache",
    "save",
    "save_secrets",
    "secrets",
]
