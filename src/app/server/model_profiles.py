"""Model configurations an administrator has saved, to switch back to later.

The settings page holds one active configuration. Changing model meant
re-typing the provider, endpoint, model name, context window, reply ceiling
and thinking settings every time - and the window is the one number that has
to match the loaded model exactly, so a switch back to a model used last week
was also a chance to get it wrong.

Every configuration that is applied is remembered here, keyed by what makes it
a different model - provider, endpoint and model name - so saving the same
model again updates its entry instead of adding another. The settings page
lists them and fills the form from one.

Credentials are never part of a profile. They stay write-only and encrypted in
`runtime_secrets`, shared by every profile that uses the same provider.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Mapping

from app.server.schema_lock import ensure_table

logger = logging.getLogger(__name__)

PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS model_profiles (
    id         TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    settings   TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
)
"""

#: What a profile holds: the model and what has to match it. Execution mode is
#: a property of how a run is scheduled, not of a model, and is left out.
PROFILE_FIELDS = (
    "llm_provider",
    "openai_base_url",
    "model_name",
    "model_context_window",
    "model_max_output_tokens",
    "thinking_mode",
    "thinking_effort",
)

#: How many profiles are kept. Past this the least recently saved is dropped,
#: so a long-lived deployment's list stays short enough to choose from.
MOST_PROFILES = 50


def profile_id(llm_provider: str, openai_base_url: str, model_name: str) -> str:
    """The identity of a model configuration: the same model at the same endpoint."""
    key = "|".join(
        str(part or "").strip().lower().rstrip("/")
        for part in (llm_provider, openai_base_url, model_name)
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _label(values: Mapping[str, Any]) -> str:
    model = str(values.get("model_name") or "").strip() or "unnamed model"
    provider = str(values.get("llm_provider") or "").strip()
    return f"{model} ({provider})" if provider else model


def remember(values: Mapping[str, Any], *, actor: str = "unknown") -> dict[str, Any]:
    """Store the configuration just applied, replacing any entry for the same model."""
    from app.server.auth import get_db_connection

    kept = {field: values.get(field) for field in PROFILE_FIELDS}
    identity = profile_id(kept["llm_provider"], kept["openai_base_url"], kept["model_name"])
    label = _label(kept)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "model_profiles", PROFILES_TABLE_SQL)
            cur.execute(
                """
                INSERT INTO model_profiles (id, label, settings, updated_at, updated_by)
                VALUES (%s, %s, %s, NOW(), %s)
                ON CONFLICT (id) DO UPDATE
                   SET label = EXCLUDED.label,
                       settings = EXCLUDED.settings,
                       updated_at = EXCLUDED.updated_at,
                       updated_by = EXCLUDED.updated_by
                """,
                (identity, label, json.dumps(kept, sort_keys=True), actor),
            )
            cur.execute(
                """
                DELETE FROM model_profiles WHERE id IN (
                    SELECT id FROM model_profiles ORDER BY updated_at DESC OFFSET %s
                )
                """,
                (MOST_PROFILES,),
            )
        conn.commit()
    return {"id": identity, "label": label, **kept}


def list_profiles() -> list[dict[str, Any]]:
    """Every saved configuration, most recently saved first."""
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "model_profiles", PROFILES_TABLE_SQL)
            cur.execute(
                "SELECT id, label, settings, updated_at, updated_by FROM model_profiles "
                "ORDER BY updated_at DESC"
            )
            rows = cur.fetchall()
    profiles: list[dict[str, Any]] = []
    for identity, label, settings, updated_at, updated_by in rows:
        try:
            stored = json.loads(settings or "{}")
        except ValueError:
            logger.warning("Model profile %s is unreadable; skipping it", identity)
            continue
        profiles.append({
            "id": identity,
            "label": label,
            **{field: stored.get(field) for field in PROFILE_FIELDS},
            "updated_at": updated_at.isoformat() if updated_at else None,
            "updated_by": updated_by,
        })
    return profiles


def forget(identity: str) -> bool:
    """Delete one saved configuration. True when there was one to delete."""
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            ensure_table(cur, "model_profiles", PROFILES_TABLE_SQL)
            cur.execute("DELETE FROM model_profiles WHERE id = %s", (identity,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


__all__ = ["MOST_PROFILES", "PROFILE_FIELDS", "forget", "list_profiles", "profile_id", "remember"]
