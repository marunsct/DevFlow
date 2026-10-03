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
from typing import Any, Literal

from app.agents.thinking import thinking_budget_tokens

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents import context_budget
from app.agents.context_budget import DEFAULT_CONTEXT_WINDOW
from app.server import runtime_settings
from app.server.auth import UserInDB, get_current_active_user, record_audit, require_admin

logger = logging.getLogger(__name__)

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_PROVIDERS = {"local", "openai", "anthropic", "gemini"}


MIN_CONTEXT_WINDOW = 8_000
"""Below this nothing runs: the framing alone is most of it."""

MAX_CONTEXT_WINDOW = 2_000_000
"""A sanity bound, not a prediction. A typo of 100000000 would otherwise
schedule compaction past any real window and disable it silently."""


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
    model_context_window: int
    model_max_output_tokens: int
    thinking_mode: str = "default"
    thinking_effort: str = "medium"
    #: Read-only: what the window currently implies, so the form can show the
    #: consequences of a change instead of only the number.
    derived_budgets: dict[str, int] = {}
    #: Read-only: the tokens thinking would actually get at the current setting,
    #: which is a share of the reply budget rather than a separate allowance.
    thinking_budget_tokens: int = 0
    openai_api_key_hint: str | None = None
    anthropic_api_key_hint: str | None = None
    google_api_key_hint: str | None = None
    openai_api_key_configured: bool = False
    anthropic_api_key_configured: bool = False
    google_api_key_configured: bool = False
    execution_mode: str = "linear"
    #: The judgement model (`app.models.roles`). An empty name means every
    #: stage runs on the model above.
    judgement_provider: str = ""
    judgement_base_url: str = ""
    judgement_model_name: str = ""
    judgement_context_window: int = 0
    judgement_api_key_hint: str | None = None
    judgement_api_key_configured: bool = False


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
    model_context_window: int = Field(
        default=DEFAULT_CONTEXT_WINDOW,
        ge=MIN_CONTEXT_WINDOW,
        le=MAX_CONTEXT_WINDOW,
        description=(
            "The model's context window in tokens. Every context budget in the "
            "pipeline is derived from this, so it must match the model actually "
            "loaded - a window larger than the truth schedules compaction to "
            "fire at a point the model never reaches."
        ),
    )

    model_max_output_tokens: int = Field(
        default=0,
        ge=0,
        le=MAX_CONTEXT_WINDOW,
        description=(
            "The longest single reply, in tokens. 0 derives it from the context "
            "window (a quarter of it, capped). The reply and the conversation "
            "share one window, so raising this shrinks the conversation - every "
            "other budget is re-derived from what it leaves behind."
        ),
    )
    thinking_mode: Literal["default", "on", "off"] = Field(
        default="default",
        description=(
            "'default' sends nothing and leaves the model server's own setting in "
            "force; 'on' asks a reasoning-capable model to deliberate; 'off' "
            "explicitly disables it. 'off' is not the absence of 'on' - a server "
            "launched with reasoning enabled keeps it under 'default'."
        ),
    )
    thinking_effort: Literal["low", "medium", "high"] = Field(
        default="medium",
        description=(
            "How much of the reply budget thinking may spend: low a quarter, "
            "medium a half, high three quarters. Thinking tokens are output "
            "tokens, so a higher setting leaves less room for the answer."
        ),
    )

    openai_api_key: str | None = Field(default=None, max_length=512, repr=False)
    anthropic_api_key: str | None = Field(default=None, max_length=512, repr=False)
    google_api_key: str | None = Field(default=None, max_length=512, repr=False)
    execution_mode: Literal["linear", "parallel"] = Field(
        default="linear",
        description=(
            "'linear' runs sprint stages one at a time; 'parallel' fans out "
            "specialist tasks using LangGraph's Send API for concurrent execution."
        ),
    )

    # The judgement model: the architect, QA, the reviews, the test rounds and
    # the fixes run on it (see `app.models.roles`). Empty fields are the default
    # model's; an empty name turns it off.
    judgement_provider: str = Field(default="", max_length=40)
    judgement_base_url: str = Field(default="", max_length=500)
    judgement_model_name: str = Field(default="", max_length=200)
    judgement_context_window: int = Field(default=0, ge=0, le=MAX_CONTEXT_WINDOW)
    judgement_api_key: str | None = Field(default=None, max_length=512, repr=False)

    @field_validator("openai_api_key", "anthropic_api_key", "google_api_key", "judgement_api_key")
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

    @field_validator("judgement_provider")
    @classmethod
    def _known_judgement_provider(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised and normalised not in ALLOWED_PROVIDERS:
            raise ValueError(f"Unknown provider '{value}'. Choose one of: {', '.join(sorted(ALLOWED_PROVIDERS))}.")
        return normalised

    @field_validator("judgement_base_url")
    @classmethod
    def _safe_judgement_base_url(cls, value: str) -> str:
        return cls._safe_base_url(value) if value.strip() else ""

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
    budget = context_budget.ContextBudget.resolve(runtime_settings.effective_environment())
    return SettingsView(
        llm_provider=s.llm_provider,
        openai_base_url=s.openai_base_url,
        model_name=s.model_name,
        model_context_window=budget.window_tokens,
        model_max_output_tokens=budget.max_output_tokens,
        thinking_mode=getattr(s, "thinking_mode", "default"),
        thinking_effort=getattr(s, "thinking_effort", "medium"),
        thinking_budget_tokens=thinking_budget_tokens(
            getattr(s, "thinking_effort", None), budget.max_output_tokens
        )
        if getattr(s, "thinking_mode", "default") == "on"
        else 0,
        derived_budgets={
            "reply_ceiling_tokens": budget.max_output_tokens,
            "input_ceiling_tokens": budget.input_ceiling_tokens,
            "compaction_trigger_tokens": budget.trigger_tokens,
            "protected_tail_tokens": budget.protected_tail_tokens,
            "keep_recent_messages": budget.keep_recent_messages,
            "document_budget_chars": budget.document_budget_chars,
            "specification_budget_chars": budget.specification_budget_chars,
            "command_output_bytes": budget.tool_output_bytes,
        },
        openai_api_key_hint=_mask(s.openai_api_key),
        anthropic_api_key_hint=_mask(s.anthropic_api_key),
        google_api_key_hint=_mask(s.google_api_key),
        openai_api_key_configured=bool(s.openai_api_key),
        anthropic_api_key_configured=bool(s.anthropic_api_key),
        google_api_key_configured=bool(s.google_api_key),
        execution_mode=getattr(s, "execution_mode", "linear") or "linear",
        **_judgement_view(),
    )


def _judgement_view() -> dict[str, Any]:
    environment = runtime_settings.effective_environment()
    try:
        window = int(str(environment.get("JUDGEMENT_CONTEXT_WINDOW") or "0").strip() or 0)
    except ValueError:
        window = 0
    key = str(environment.get("JUDGEMENT_API_KEY") or "")
    return {
        "judgement_provider": str(environment.get("JUDGEMENT_PROVIDER") or ""),
        "judgement_base_url": str(environment.get("JUDGEMENT_BASE_URL") or ""),
        "judgement_model_name": str(environment.get("JUDGEMENT_MODEL") or ""),
        "judgement_context_window": window,
        "judgement_api_key_hint": _mask(key),
        "judgement_api_key_configured": bool(key),
    }


@settings_router.get("", response_model=SettingsView)
async def get_settings_view(user: UserInDB = Depends(get_current_active_user)) -> SettingsView:
    """Current provider configuration, with credentials masked."""
    return _current_view()


class DetectedWindow(BaseModel):
    """What a context-window probe found, and how."""

    model_config = ConfigDict(extra="forbid")

    detected: int | None = Field(
        default=None, description="Tokens the server reported, or null if it could not be measured."
    )
    explanation: str = Field(description="What happened, in a sentence the operator can act on.")


@settings_router.post("/detect-context-window", response_model=DetectedWindow)
async def detect_context_window_endpoint(
    user: UserInDB = Depends(require_admin),
) -> DetectedWindow:
    """Measure the configured server's context window by asking it to refuse.

    Admin-only and rate-limited by its own cost: it sends one deliberately
    oversized request, which the server rejects before generating anything.

    This exists because the window is the one setting that must be right and the
    one nobody reliably knows. A model's advertised window is not what it was
    loaded with - the same `gpt-oss-20b` serves 131,072 tokens or 8,192
    depending on a slider - and no standard endpoint reports it. The refusal
    does.
    """
    from app.models.window_probe import detect_from_settings

    detected, explanation = detect_from_settings(
        runtime_settings.effective_environment(), runtime_settings.secrets()
    )
    logger.info("Context-window probe by %s: %s", user.username, explanation)
    return DetectedWindow(detected=detected, explanation=explanation)


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
            "model_context_window": str(payload.model_context_window),
            # Empty clears the override, so the reply ceiling goes back to being
            # derived from the window rather than pinned to a stale number.
            "model_max_output_tokens": (
                str(payload.model_max_output_tokens)
                if payload.model_max_output_tokens
                else ""
            ),
            # Stored as the strings `_read_bool` and the effort lookup expect,
            # so a value read back out of Postgres parses the same way one read
            # out of the environment does.
            "thinking_mode": payload.thinking_mode,
            "thinking_effort": payload.thinking_effort,
            "execution_mode": payload.execution_mode,
            # Empty clears each override, which with an empty name turns the
            # judgement model off.
            "judgement_provider": payload.judgement_provider,
            "judgement_base_url": payload.judgement_base_url,
            "judgement_model_name": payload.judgement_model_name.strip(),
            "judgement_context_window": (
                str(payload.judgement_context_window) if payload.judgement_context_window else ""
            ),
        },
        actor=user.username,
    )

    # Remembered as a saved model, so switching back to it later is a pick
    # from a list rather than six fields typed again. A failure here must not
    # undo a settings change that has already been applied.
    try:
        from app.server import model_profiles

        model_profiles.remember(payload.model_dump(), actor=user.username)
    except Exception:  # noqa: BLE001 - the applied settings stand either way
        logger.warning("Could not remember the model configuration", exc_info=True)

    submitted = {
        "openai_api_key": payload.openai_api_key,
        "anthropic_api_key": payload.anthropic_api_key,
        "google_api_key": payload.google_api_key,
        "judgement_api_key": payload.judgement_api_key,
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
            "judgement_model_name": payload.judgement_model_name.strip(),
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


class ModelProfile(BaseModel):
    """A model configuration saved earlier, ready to fill the form again.

    Never a credential: those stay write-only and are shared by every profile
    for the same provider.
    """

    id: str
    label: str
    llm_provider: str | None = None
    openai_base_url: str | None = None
    model_name: str | None = None
    model_context_window: int | None = None
    model_max_output_tokens: int | None = None
    thinking_mode: str | None = None
    thinking_effort: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None


@settings_router.get("/models", response_model=list[ModelProfile])
async def list_model_profiles(user: UserInDB = Depends(get_current_active_user)) -> list[ModelProfile]:
    """Every model configuration saved so far, most recently saved first."""
    from app.server import model_profiles

    return [ModelProfile(**profile) for profile in model_profiles.list_profiles()]


@settings_router.delete("/models/{profile_id}", status_code=204)
async def delete_model_profile(profile_id: str, user: UserInDB = Depends(require_admin)) -> None:
    """Forget one saved configuration. The active settings are not changed."""
    from app.server import model_profiles

    if not model_profiles.forget(profile_id):
        raise HTTPException(status_code=404, detail="No saved model with that id.")
    record_audit(
        actor=user.username,
        tenant_id=user.tenant_id,
        action="settings.model_profile.delete",
        subject=profile_id,
        detail={},
    )


__all__ = ["settings_router"]
