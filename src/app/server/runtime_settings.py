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
    # How much each stage does: `fast` or `thorough`. See `app.delivery`.
    "delivery_mode": "DELIVERY_MODE",
    # Whether the model can be shown images - "yes", "no" or "auto". The
    # milestone review is given screenshots of the page only when it can. See
    # `app.models.vision`.
    "model_reads_images": "MODEL_READS_IMAGES",
    # A second model for the stages that judge rather than produce: the
    # architect, QA, the reviews, the test rounds and the fixes. Empty means
    # every stage uses the model above. See `app.models.roles`.
    "judgement_provider": "JUDGEMENT_PROVIDER",
    "judgement_base_url": "JUDGEMENT_BASE_URL",
    "judgement_model_name": "JUDGEMENT_MODEL",
    "judgement_context_window": "JUDGEMENT_CONTEXT_WINDOW",
    # Its longest single reply; 0 derives it from its own window.
    "judgement_max_output_tokens": "JUDGEMENT_MAX_OUTPUT_TOKENS",
    # Two tiers: the judgement model plans (`PLAN_ON_JUDGEMENT_MODEL`), the
    # default model builds, and a stage or defect the default model failed this
    # many times goes to the judgement model. See `app.models.roles`.
    "escalate_after_attempts": "ESCALATE_AFTER_ATTEMPTS",
    "plan_on_judgement_model": "PLAN_ON_JUDGEMENT_MODEL",
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
    global _cache, _cache_expires_at, _secret_cache, _secret_cache_expires_at, _switch_cache, _switch_cache_expires_at
    with _cache_lock:
        _cache = {}
        _cache_expires_at = 0.0
        _secret_cache = {}
        _secret_cache_expires_at = 0.0
        _switch_cache = {}
        _switch_cache_expires_at = 0.0


# ---------------------------------------------------------------------------
# Switches
# ---------------------------------------------------------------------------

#: A switch an administrator set on the admin page, stored as `switch:<NAME>` = `on` or `off`. A switch with no row
#: follows the deployed environment, and the code's own default after that (`app.switches.is_on`).
SWITCH_PREFIX = "switch:"

_switch_cache: dict[str, bool] = {}
_switch_cache_expires_at = 0.0


def _read_switches_from_db() -> dict[str, bool]:
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_settings", SETTINGS_TABLE_SQL)
            cur.execute("SELECT key, value FROM runtime_settings WHERE key LIKE %s", (SWITCH_PREFIX + "%",))
            rows = cur.fetchall()
        conn.commit()
    return {key[len(SWITCH_PREFIX):]: value == "on" for key, value in rows if value in ("on", "off")}


def switch_overrides(*, refresh: bool = False) -> dict[str, bool]:
    """The switches set on the admin page, cached for `CACHE_TTL_SECONDS` per process. Never raises."""
    global _switch_cache, _switch_cache_expires_at

    now = time.monotonic()
    if not refresh and now < _switch_cache_expires_at:
        return dict(_switch_cache)
    try:
        fresh = _read_switches_from_db()
    except Exception:  # noqa: BLE001 - the environment still decides when the table cannot be read
        logger.warning("Could not read the switch settings; using the environment", exc_info=True)
        with _cache_lock:
            _switch_cache_expires_at = now + CACHE_TTL_SECONDS
        return dict(_switch_cache)
    with _cache_lock:
        _switch_cache = fresh
        _switch_cache_expires_at = now + CACHE_TTL_SECONDS
    return dict(fresh)


def save_switch(name: str, value: bool | None, *, actor: str = "unknown") -> None:
    """Set a switch on or off for every process, or clear it (`None`) so the environment decides again."""
    from app.server.auth import get_db_connection

    key = SWITCH_PREFIX + name
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_settings", SETTINGS_TABLE_SQL)
            if value is None:
                cur.execute("DELETE FROM runtime_settings WHERE key = %s", (key,))
            else:
                cur.execute(
                    """
                    INSERT INTO runtime_settings (key, value, updated_at, updated_by)
                    VALUES (%s, %s, NOW(), %s)
                    ON CONFLICT (key) DO UPDATE
                       SET value = EXCLUDED.value,
                           updated_at = EXCLUDED.updated_at,
                           updated_by = EXCLUDED.updated_by
                    """,
                    (key, "on" if value else "off", actor),
                )
        conn.commit()
    switch_overrides(refresh=True)


#: Where each provider reads its credential from.
_KEY_VARIABLE = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GOOGLE_API_KEY", "google": "GOOGLE_API_KEY"}

#: A stored credential that belongs to one endpoint rather than to a provider.
ENDPOINT_KEY_PREFIX = "endpoint:"


def endpoint_id(provider: str, base_url: str) -> str:
    """The identity of an endpoint: a provider at an address ("" is the provider's own)."""
    import hashlib

    normal = f"{str(provider or 'local').strip().lower()}|{str(base_url or '').strip().lower().rstrip('/')}"
    return ENDPOINT_KEY_PREFIX + hashlib.sha256(normal.encode("utf-8")).hexdigest()[:24]


def endpoint_keys() -> dict[str, str]:
    """Every endpoint's own stored key, by `endpoint_id`. Never raises.

    A key used to belong to a provider: one OpenAI-compatible key for every
    OpenAI-compatible server. Measured on one run's model change: the local
    server, a hosted preview API and a cloud API were all "OpenAI-compatible",
    and switching to the cloud API kept sending the preview API's key - every
    call refused with 401. Each endpoint now keeps its own.
    """
    try:
        from app.server.auth import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                ensure_table(cur, "runtime_secrets", SECRETS_TABLE_SQL)
                cur.execute("SELECT key, ciphertext FROM runtime_secrets WHERE key LIKE %s", (ENDPOINT_KEY_PREFIX + "%",))
                rows = cur.fetchall()
            conn.commit()
    except Exception:  # noqa: BLE001 - the provider's key still applies
        logger.debug("Could not read the endpoints' keys", exc_info=True)
        return {}
    box = _fernet()
    found: dict[str, str] = {}
    for key, ciphertext in rows:
        try:
            found[key] = box.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            logger.error("A stored endpoint key cannot be decrypted; re-enter it in Settings.")
    return found


def save_endpoint_key(provider: str, base_url: str, value: str, *, actor: str = "unknown") -> None:
    """Store `value` as this endpoint's own key, encrypted; an empty value removes it."""
    from app.server.auth import get_db_connection

    identity = endpoint_id(provider, base_url)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "runtime_secrets", SECRETS_TABLE_SQL)
            if not value:
                cur.execute("DELETE FROM runtime_secrets WHERE key = %s", (identity,))
            else:
                cur.execute(
                    """
                    INSERT INTO runtime_secrets (key, ciphertext, updated_at, updated_by)
                    VALUES (%s, %s, NOW(), %s)
                    ON CONFLICT (key) DO UPDATE
                       SET ciphertext = EXCLUDED.ciphertext,
                           updated_at = EXCLUDED.updated_at,
                           updated_by = EXCLUDED.updated_by
                    """,
                    (identity, _fernet().encrypt(value.encode("utf-8")).decode("utf-8"), actor),
                )
        conn.commit()


def judgement_endpoint(environment: Mapping[str, str]) -> tuple[str, str]:
    """(provider, address) the judgement model is served from, as `app.models.roles` builds it."""
    default_provider = str(environment.get("LLM_PROVIDER") or "local").strip().lower()
    provider = str(environment.get("JUDGEMENT_PROVIDER") or "").strip().lower() or default_provider
    base = str(environment.get("JUDGEMENT_BASE_URL") or "").strip()
    if not base and provider == default_provider:
        base = str(environment.get("OPENAI_BASE_URL") or "")
    return provider, base


#: The environment variables that say which model a run talks to - never a credential. A run's `model_last` is a
#: snapshot of exactly these, so that a pinned run can keep working on a model the settings page has since left.
#: The key each endpoint needs is not here: it is resolved server-side, per endpoint, when the run asks.
MODEL_KEYS: tuple[str, ...] = (
    "LLM_PROVIDER",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "MODEL_CONTEXT_WINDOW",
    "MODEL_MAX_OUTPUT_TOKENS",
    "JUDGEMENT_PROVIDER",
    "JUDGEMENT_BASE_URL",
    "JUDGEMENT_MODEL",
    "JUDGEMENT_CONTEXT_WINDOW",
    "JUDGEMENT_MAX_OUTPUT_TOKENS",
)


def _the_run_s_model() -> Mapping[str, str] | None:
    """The model snapshot of the run this call belongs to when that run is pinned, else None. Never raises."""
    try:
        from app.models.model_pin import pinned_snapshot

        return pinned_snapshot()
    except Exception:  # noqa: BLE001 - an unreadable pin is the global view, which is what every run had before
        return None


def _endpoint_of(environment: Mapping[str, str]) -> tuple[str, str]:
    return (
        str(environment.get("LLM_PROVIDER") or "local").strip().lower(),
        str(environment.get("OPENAI_BASE_URL") or "").strip().lower().rstrip("/"),
    )


def _normal(endpoint: tuple[str, str]) -> tuple[str, str]:
    return str(endpoint[0] or "").strip().lower(), str(endpoint[1] or "").strip().lower().rstrip("/")


def global_model_snapshot() -> dict[str, str]:
    """The model the settings name now - the non-secret model keys of the global view, "" where unset.

    Reads the stored overrides and the process environment only (no credential, no per-endpoint key), so it is
    cheap enough to ask on every model request.
    """
    environment = dict(os.environ)
    for key, value in overrides().items():
        if value:
            environment[SETTABLE_KEYS[key]] = value
    return {key: str(environment.get(key) or "").strip() for key in MODEL_KEYS}


def effective_environment(
    base: Mapping[str, str] | None = None,
    *,
    ignore_run: bool = False,
    model: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The environment with stored overrides layered on top, each endpoint with its own key.

    Inside a run whose model is pinned (`app.models.model_pin`), the run's own model - the snapshot it last ran
    with - is laid over the model keys after the stored overrides, so the context budget, the reply ceiling and
    every client built for the run follow that model whatever the settings page says now. Credentials come
    after it and never from it: a model that is not the one the settings name gets its own endpoint's key or
    none, never the key of the endpoint the settings name.

    `ignore_run` gives the global view (what the settings page shows) and `model` the view of a given snapshot.
    A caller that passes `base` gets exactly that environment layered with the overrides, as before.
    """
    environment = dict(base if base is not None else os.environ)
    for key, value in overrides().items():
        if value:
            environment[SETTABLE_KEYS[key]] = value
    snapshot = model
    if snapshot is None and base is None and not ignore_run:
        snapshot = _the_run_s_model()
    withheld: set[str] = set()
    if snapshot:
        was_default = _endpoint_of(environment)
        was_judge = _normal(judgement_endpoint(environment))
        inherited = str(environment.get(_KEY_VARIABLE.get(was_default[0], "OPENAI_API_KEY")) or "")
        for key in MODEL_KEYS:
            if key in snapshot:
                value = str(snapshot.get(key) or "")
                if value:
                    environment[key] = value
                else:
                    environment.pop(key, None)
        judging = bool(str(environment.get("JUDGEMENT_MODEL") or "").strip())
        foreign_judge = judging and _normal(judgement_endpoint(environment)) != was_judge
        if _endpoint_of(environment) != was_default:
            variable = _KEY_VARIABLE.get(_endpoint_of(environment)[0], "OPENAI_API_KEY")
            withheld.add(variable)
            environment.pop(variable, None)
            # The judgement model, still where it was, had been using the default model's key; it keeps it.
            if judging and not foreign_judge and inherited and not environment.get("JUDGEMENT_API_KEY"):
                environment["JUDGEMENT_API_KEY"] = inherited
        if foreign_judge:
            withheld.add("JUDGEMENT_API_KEY")
            environment.pop("JUDGEMENT_API_KEY", None)
    for key, value in secrets().items():
        if value and SETTABLE_SECRETS[key] not in withheld:
            environment[SETTABLE_SECRETS[key]] = value
    keys = endpoint_keys()
    if keys:
        provider = str(environment.get("LLM_PROVIDER") or "local").strip().lower()
        own = keys.get(endpoint_id(provider, str(environment.get("OPENAI_BASE_URL") or "")))
        if own:
            environment[_KEY_VARIABLE.get(provider, "OPENAI_API_KEY")] = own
        if str(environment.get("JUDGEMENT_MODEL") or "").strip():
            judge = keys.get(endpoint_id(*judgement_endpoint(environment)))
            if judge:
                environment["JUDGEMENT_API_KEY"] = judge
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
    "MODEL_KEYS",
    "SETTINGS_TABLE_SQL",
    "global_model_snapshot",
    "clear",
    "clear_secrets",
    "effective_environment",
    "effective_settings",
    "endpoint_id",
    "endpoint_keys",
    "judgement_endpoint",
    "save_endpoint_key",
    "overrides",
    "reset_cache",
    "save",
    "save_secrets",
    "secrets",
]
