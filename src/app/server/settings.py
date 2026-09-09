"""Provider configuration endpoints.

Secrets are never returned. The previous version handed every provider API key
back in plaintext to any authenticated caller, wrote them to ``.env`` on disk at
runtime, and let an unprivileged user change ``openai_base_url`` - which
redirects every subsequent model call, and its credentials, to a host of their
choosing.

What replaces it: a masked read anyone may perform, and an admin-only write that
records who changed what.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.config import load_settings
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
    """Non-secret configuration an administrator may change at runtime.

    Credentials are deliberately absent: they belong in the secret store or the
    process environment, not in an API body that lands in access logs.
    """

    llm_provider: str
    openai_base_url: str
    model_name: str = Field(min_length=1, max_length=200)

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
    s = load_settings()
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
    """Change non-secret provider settings for this process.

    Applied to the process environment only. Writing to ``.env`` from a request
    handler mutated a file that the deployment also reads at startup, which made
    runtime state and deployed configuration silently diverge.
    """
    if os.environ.get("SETTINGS_READ_ONLY", "").strip().lower() in {"1", "true", "yes"}:
        raise HTTPException(
            status_code=403,
            detail="Provider settings are managed by deployment configuration and cannot be "
                   "changed through the API in this environment.",
        )

    os.environ["LLM_PROVIDER"] = payload.llm_provider
    os.environ["OPENAI_BASE_URL"] = payload.openai_base_url
    os.environ["OPENAI_MODEL"] = payload.model_name

    record_audit(
        actor=user.username,
        tenant_id=user.tenant_id,
        action="settings.update",
        subject="provider-configuration",
        detail={
            "llm_provider": payload.llm_provider,
            "openai_base_url": payload.openai_base_url,
            "model_name": payload.model_name,
        },
    )
    logger.info("Provider settings updated by %s", user.username)
    return _current_view()


__all__ = ["settings_router"]
