"""Provider configuration endpoints.

Secrets are never returned. The previous version handed every provider API key
back in plaintext to any authenticated caller, wrote them to ``.env`` on disk at
runtime, and let an unprivileged user change ``openai_base_url`` - which
redirects every subsequent model call, and its credentials, to a host of their
choosing.

What replaces it: a masked read anyone may perform, and an admin-only write that
records who changed what.

Credentials can now be *set* here, because an endpoint that starts requiring a
key is otherwise unfixable without a redeploy - but the direction is one-way.
They are write-only, stored encrypted, excluded from the response model
entirely, and the audit row names which credential changed rather than what it
became.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.server import runtime_settings
from app.server.auth import UserInDB, get_current_active_user, record_audit, require_admin

logger = logging.getLogger(__name__)

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_PROVIDERS = {"local", "openai", "anthropic", "gemini"}


def _mask(secret: str | None) -> str | None:
    """Show only enough of a credential to tell which one is configured."""
    if not secret:
        return None
    if len(secret) <= 8:
        return "****"
    return f"****{secret[-4:]}"


class SettingsView(BaseModel):
    """What the UI is allowed to see."""

    llm_provider: str
    openai_base_url: str
    model_name: str
    openai_api_key_hint: str | None = None
    anthropic_api_key_hint: str | None = None
    google_api_key_hint: str | None = None
    openai_api_key_configured: bool = False
    anthropic_api_key_configured: bool = False
    google_api_key_configured: bool = False


class SettingsUpdate(BaseModel):
    """Configuration an administrator may change at runtime.

    Credentials are **write-only**. They can be set here because a self-hosted
    endpoint that starts requiring a key is otherwise unfixable without a
    redeploy, but nothing ever reads one back: responses carry a masked hint
    only, the audit row records which credential changed and never its value,
    and the stored copy is encrypted.

    Three states per credential, which is what makes the form usable:
      omitted / null - leave whatever is stored alone
      ""             - delete the stored credential; the deployment's own
                       environment applies again
      a value        - set it
    """

    model_config = ConfigDict(extra="forbid")

    llm_provider: str
    openai_base_url: str
    model_name: str = Field(min_length=1, max_length=200)

    openai_api_key: str | None = Field(default=None, max_length=512, repr=False)
    anthropic_api_key: str | None = Field(default=None, max_length=512, repr=False)
    google_api_key: str | None = Field(default=None, max_length=512, repr=False)

    @field_validator("openai_api_key", "anthropic_api_key", "google_api_key")
    @classmethod
    def _clean_credential(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        # A pasted key that still carries the mask the UI displayed means the
        # field was never edited. Treat it as "leave alone" rather than storing
        # literal asterisks and breaking every subsequent model call.
        if cleaned.startswith("****"):
            return None
        if any(c in cleaned for c in "\n\r\x00"):
            raise ValueError("A credential may not contain control characters.")
        return cleaned

    @field_validator("llm_provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in ALLOWED_PROVIDERS:
            raise ValueError(f"Unknown provider '{value}'. Choose one of: {', '.join(sorted(ALLOWED_PROVIDERS))}.")
        return normalised

    @field_validator("openai_base_url")
    @classmethod
    def _safe_base_url(cls, value: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("The base URL must start with http:// or https://.")
        if not parsed.hostname:
            raise ValueError("The base URL must include a host.")

        allowed = os.environ.get("ALLOWED_MODEL_HOSTS", "").strip()
        if allowed:
            permitted = {h.strip().lower() for h in allowed.split(",") if h.strip()}
            if parsed.hostname.lower() not in permitted:
                raise ValueError(
                    f"'{parsed.hostname}' is not an approved model host. "
                    f"Approved hosts: {', '.join(sorted(permitted))}."
                )
        return value.strip()


def _current_view() -> SettingsView:
    # Stored overrides, not this process's environment. Four gunicorn workers
    # answer these requests in rotation, so reading `os.environ` meant each one
    # reported whatever it happened to hold - the page looked like it reverted
    # on its own, and consecutive reads returned different values.
    s = runtime_settings.effective_settings()
    return SettingsView(
        llm_provider=s.llm_provider,
        openai_base_url=s.openai_base_url,
        model_name=s.model_name,
        openai_api_key_hint=_mask(s.openai_api_key),
        anthropic_api_key_hint=_mask(s.anthropic_api_key),
        google_api_key_hint=_mask(s.google_api_key),
        openai_api_key_configured=bool(s.openai_api_key),
        anthropic_api_key_configured=bool(s.anthropic_api_key),
        google_api_key_configured=bool(s.google_api_key),
    )


@settings_router.get("", response_model=SettingsView)
async def get_settings_view(user: UserInDB = Depends(get_current_active_user)) -> SettingsView:
    """Current provider configuration, with credentials masked."""
    return _current_view()


@settings_router.put("", response_model=SettingsView)
async def update_settings(
    payload: SettingsUpdate, user: UserInDB = Depends(require_admin)
) -> SettingsView:
    """Change non-secret provider settings for the whole system.

    Stored in Postgres so every API worker and the Celery worker see one answer,
    and so the change survives a restart. Writing to ``.env`` from a request
    handler (the version before that) mutated a file the deployment also reads at
    startup, which made runtime state and deployed configuration diverge.
    """
    if os.environ.get("SETTINGS_READ_ONLY", "").strip().lower() in {"1", "true", "yes"}:
        raise HTTPException(
            status_code=403,
            detail="Provider settings are managed by deployment configuration and cannot be "
                   "changed through the API in this environment.",
        )

    # Persisted, not written to this process's environment. The agents do not
    # even run in this container - they run in the Celery worker, which has its
    # own environment and would never have observed the change.
    runtime_settings.save(
        {
            "llm_provider": payload.llm_provider,
            "openai_base_url": payload.openai_base_url,
            "model_name": payload.model_name,
        },
        actor=user.username,
    )

    submitted = {
        "openai_api_key": payload.openai_api_key,
        "anthropic_api_key": payload.anthropic_api_key,
        "google_api_key": payload.google_api_key,
    }
    # None means "leave alone"; "" means "delete". Only the keys the form
    # actually touched are written.
    changed_credentials = runtime_settings.save_secrets(
        {k: v for k, v in submitted.items() if v is not None}, actor=user.username
    )

    record_audit(
        actor=user.username,
        tenant_id=user.tenant_id,
        action="settings.update",
        subject="provider-configuration",
        detail={
            "llm_provider": payload.llm_provider,
            "openai_base_url": payload.openai_base_url,
            "model_name": payload.model_name,
            # Which credentials changed, never their values. This row is
            # long-lived and is read by people investigating incidents.
            "credentials_changed": sorted(changed_credentials),
        },
    )
    logger.info(
        "Provider settings updated by %s (credentials changed: %s)",
        user.username, ", ".join(sorted(changed_credentials)) or "none",
    )
    return _current_view()


__all__ = ["settings_router"]
