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
    target     TEXT NOT NULL DEFAULT 'build',
    settings   TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
)
"""

BUILD_PROFILE_FIELDS = (
    "llm_provider",
    "openai_base_url",
    "model_name",
    "model_context_window",
    "model_max_output_tokens",
    "thinking_mode",
    "thinking_effort",
)

FRONTIER_PROFILE_FIELDS = (
    "judgement_provider",
    "judgement_base_url",
    "judgement_model_name",
    "judgement_context_window",
    "judgement_max_output_tokens",
    "escalate_after_attempts",
    "plan_on_judgement_model",
)

PROFILE_FIELDS = BUILD_PROFILE_FIELDS

#: How many profiles are kept per target. Past this the least recently saved is dropped.
MOST_PROFILES = 50


def _ensure_profiles_schema(cur: Any) -> None:
    ensure_table(cur, "model_profiles", PROFILES_TABLE_SQL)
    cur.execute("ALTER TABLE model_profiles ADD COLUMN IF NOT EXISTS target TEXT NOT NULL DEFAULT 'build'")
    cur.execute("CREATE INDEX IF NOT EXISTS model_profiles_target_idx ON model_profiles (target, updated_at DESC)")


def profile_id(
    llm_provider: str,
    openai_base_url: str,
    model_name: str,
    *,
    target: str = "build",
) -> str:
    """The identity of a model configuration: the same model at the same endpoint."""
    parts = (llm_provider, openai_base_url, model_name) if target == "build" else (target, llm_provider, openai_base_url, model_name)
    key = "|".join(
        str(part or "").strip().lower().rstrip("/")
        for part in parts
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _label(values: Mapping[str, Any], *, target: str = "build") -> str:
    if target == "frontier":
        model = str(values.get("judgement_model_name") or values.get("model_name") or "").strip()
        provider = str(values.get("judgement_provider") or values.get("llm_provider") or "").strip()
    else:
        model = str(values.get("model_name") or "").strip()
        provider = str(values.get("llm_provider") or "").strip()
    model = model or "unnamed model"
    return f"{model} ({provider})" if provider else model


def remember(
    values: Mapping[str, Any],
    *,
    target: str = "build",
    actor: str = "unknown",
) -> dict[str, Any] | None:
    """Store the configuration just applied, replacing any entry for the same model."""
    from app.server.auth import get_db_connection

    if target == "frontier":
        model = str(values.get("judgement_model_name") or values.get("model_name") or "").strip()
        if not model:
            return None
        provider = str(values.get("judgement_provider") or values.get("llm_provider") or "").strip()
        base_url = str(values.get("judgement_base_url") or values.get("openai_base_url") or "").strip()
        ctx = int(values.get("judgement_context_window") or values.get("model_context_window") or 0)
        reply = int(values.get("judgement_max_output_tokens") or values.get("model_max_output_tokens") or 0)
        escalate = int(values.get("escalate_after_attempts") or 2)
        plan = bool(values.get("plan_on_judgement_model", True))
        kept: dict[str, Any] = {
            "target": "frontier",
            "judgement_provider": provider,
            "judgement_base_url": base_url,
            "judgement_model_name": model,
            "judgement_context_window": ctx,
            "judgement_max_output_tokens": reply,
            "escalate_after_attempts": escalate,
            "plan_on_judgement_model": plan,
            # Mirrors standard build keys for generic profile consumers
            "llm_provider": provider,
            "openai_base_url": base_url,
            "model_name": model,
            "model_context_window": ctx,
            "model_max_output_tokens": reply,
        }
        identity = profile_id(provider, base_url, model, target="frontier")
        label = _label(kept, target="frontier")
    else:
        model = str(values.get("model_name") or "").strip()
        provider = str(values.get("llm_provider") or "").strip()
        base_url = str(values.get("openai_base_url") or "").strip()
        kept = {
            "target": "build",
            **{field: values.get(field) for field in BUILD_PROFILE_FIELDS},
        }
        identity = profile_id(provider, base_url, model, target="build")
        label = _label(kept, target="build")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _ensure_profiles_schema(cur)
            cur.execute(
                """
                INSERT INTO model_profiles (id, label, target, settings, updated_at, updated_by)
                VALUES (%s, %s, %s, %s, NOW(), %s)
                ON CONFLICT (id) DO UPDATE
                   SET label = EXCLUDED.label,
                       target = EXCLUDED.target,
                       settings = EXCLUDED.settings,
                       updated_at = EXCLUDED.updated_at,
                       updated_by = EXCLUDED.updated_by
                """,
                (identity, label, target, json.dumps(kept, sort_keys=True), actor),
            )
            cur.execute(
                """
                DELETE FROM model_profiles WHERE id IN (
                    SELECT id FROM model_profiles WHERE target = %s ORDER BY updated_at DESC OFFSET %s
                )
                """,
                (target, MOST_PROFILES),
            )
        conn.commit()
    return {"id": identity, "label": label, **kept}


def list_profiles(target: str | None = None) -> list[dict[str, Any]]:
    """Every saved configuration, most recently saved first, optionally filtered by target."""
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _ensure_profiles_schema(cur)
            if target and target in ("build", "frontier"):
                cur.execute(
                    "SELECT id, label, target, settings, updated_at, updated_by FROM model_profiles "
                    "WHERE target = %s ORDER BY updated_at DESC",
                    (target,),
                )
            else:
                cur.execute(
                    "SELECT id, label, target, settings, updated_at, updated_by FROM model_profiles "
                    "ORDER BY updated_at DESC"
                )
            rows = cur.fetchall()
    profiles: list[dict[str, Any]] = []
    for identity, label, row_target, settings, updated_at, updated_by in rows:
        try:
            stored = json.loads(settings or "{}")
        except ValueError:
            logger.warning("Model profile %s is unreadable; skipping it", identity)
            continue
        item = {
            "id": identity,
            "label": label,
            "target": row_target or stored.get("target", "build"),
            "updated_at": updated_at.isoformat() if updated_at else None,
            "updated_by": updated_by,
        }
        item.update(stored)
        profiles.append(item)
    return profiles


def forget(identity: str) -> bool:
    """Delete one saved configuration. True when there was one to delete."""
    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            _ensure_profiles_schema(cur)
            cur.execute("DELETE FROM model_profiles WHERE id = %s", (identity,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


__all__ = [
    "BUILD_PROFILE_FIELDS",
    "FRONTIER_PROFILE_FIELDS",
    "MOST_PROFILES",
    "PROFILE_FIELDS",
    "forget",
    "list_profiles",
    "profile_id",
    "remember",
]
