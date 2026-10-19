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
from typing import Any, Literal, Mapping

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
    delivery_mode: str = "thorough"
    #: The judgement model (`app.models.roles`). An empty name means every
    #: stage runs on the model above.
    judgement_provider: str = ""
    judgement_base_url: str = ""
    judgement_model_name: str = ""
    judgement_context_window: int = 0
    judgement_max_output_tokens: int = 0
    judgement_api_key_hint: str | None = None
    judgement_api_key_configured: bool = False
    #: The two tiers (`app.models.roles`): failed tries on the build model
    #: before the judgement model takes over, and whether it also plans.
    escalate_after_attempts: int = 2
    plan_on_judgement_model: bool = True
    #: Whether the build model's endpoint, and the judgement model's, have a
    #: key of their own saved (`runtime_settings.endpoint_keys`).
    endpoint_key_saved: bool = False
    judgement_endpoint_key_saved: bool = False


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
    # None keeps what is stored: a page loaded before this field existed sent
    # no value, and a default here saved "thorough" over the deployment's
    # "fast" for one owner who had only changed the model's address.
    delivery_mode: Literal["fast", "thorough"] | None = Field(
        default=None,
        description="fast: one sprint for a small product, files drafted from the specification, "
        "harness-run test rounds, building without reasoning. thorough: the full pipeline. "
        "Left out, the stored choice stands.",
    )
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
    judgement_max_output_tokens: int = Field(
        default=0, ge=0, le=MAX_CONTEXT_WINDOW,
        description="The judgement model's longest single reply, in tokens. 0 derives it from its window.",
    )
    judgement_api_key: str | None = Field(default=None, max_length=512, repr=False)
    escalate_after_attempts: int = Field(
        default=2, ge=1, le=10,
        description="Failed tries on the build model before a stage or a defect goes to the judgement model.",
    )
    plan_on_judgement_model: bool = Field(
        default=True,
        description="Whether intake, stack choice, the sprint plan and the work orders run on the judgement model.",
    )

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
        delivery_mode=_the_delivery_mode(),
        **_judgement_view(),
    )


def _judgement_view() -> dict[str, Any]:
    from app.models.roles import escalate_after, plans_on_the_judgement_model

    environment = runtime_settings.effective_environment()
    try:
        window = int(str(environment.get("JUDGEMENT_CONTEXT_WINDOW") or "0").strip() or 0)
    except ValueError:
        window = 0
    try:
        reply = int(str(environment.get("JUDGEMENT_MAX_OUTPUT_TOKENS") or "0").strip() or 0)
    except ValueError:
        reply = 0
    key = str(environment.get("JUDGEMENT_API_KEY") or "")
    return {
        "judgement_provider": str(environment.get("JUDGEMENT_PROVIDER") or ""),
        "judgement_base_url": str(environment.get("JUDGEMENT_BASE_URL") or ""),
        "judgement_model_name": str(environment.get("JUDGEMENT_MODEL") or ""),
        "judgement_context_window": window,
        "judgement_max_output_tokens": reply,
        "judgement_api_key_hint": _mask(key),
        "judgement_api_key_configured": bool(key),
        "escalate_after_attempts": escalate_after(environment),
        "plan_on_judgement_model": plans_on_the_judgement_model(environment),
        **_endpoints_with_keys(environment),
    }


def _the_delivery_mode() -> str:
    from app import delivery

    try:
        return delivery.mode(runtime_settings.effective_environment())
    except Exception:  # noqa: BLE001 - the page still loads
        return delivery.THOROUGH


def _endpoints_with_keys(environment: Mapping[str, str]) -> dict[str, bool]:
    keys = runtime_settings.endpoint_keys()
    provider = str(environment.get("LLM_PROVIDER") or "local").strip().lower()
    return {
        "endpoint_key_saved": runtime_settings.endpoint_id(provider, str(environment.get("OPENAI_BASE_URL") or "")) in keys,
        "judgement_endpoint_key_saved": bool(str(environment.get("JUDGEMENT_MODEL") or "").strip())
        and runtime_settings.endpoint_id(*runtime_settings.judgement_endpoint(environment)) in keys,
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


def _check_read_only() -> None:
    if os.environ.get("SETTINGS_READ_ONLY", "").strip().lower() in {"1", "true", "yes"}:
        raise HTTPException(
            status_code=403,
            detail="Provider settings are managed by deployment configuration and cannot be "
                   "changed through the API in this environment.",
        )


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
    _check_read_only()

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
            **({"delivery_mode": payload.delivery_mode} if payload.delivery_mode else {}),
            # Empty clears each override, which with an empty name turns the
            # judgement model off.
            "judgement_provider": payload.judgement_provider,
            "judgement_base_url": payload.judgement_base_url,
            "judgement_model_name": payload.judgement_model_name.strip(),
            "judgement_context_window": (
                str(payload.judgement_context_window) if payload.judgement_context_window else ""
            ),
            "judgement_max_output_tokens": (
                str(payload.judgement_max_output_tokens) if payload.judgement_max_output_tokens else ""
            ),
            "escalate_after_attempts": str(payload.escalate_after_attempts),
            "plan_on_judgement_model": "true" if payload.plan_on_judgement_model else "false",
        },
        actor=user.username,
    )

    # Remembered as a saved model, so switching back to it later is a pick
    # from a list rather than six fields typed again. A failure here must not
    # undo a settings change that has already been applied.
    try:
        from app.server import model_profiles

        model_profiles.remember(payload.model_dump(), target="build", actor=user.username)
        if payload.judgement_model_name and payload.judgement_model_name.strip():
            model_profiles.remember(payload.model_dump(), target="frontier", actor=user.username)
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
    # And as the key of the endpoint each was typed for, so every endpoint keeps
    # its own: switching models no longer sends one server's key to another.
    provider = (payload.llm_provider or "local").strip().lower()
    typed = {"anthropic": payload.anthropic_api_key, "gemini": payload.google_api_key,
             "google": payload.google_api_key}.get(provider, payload.openai_api_key)
    if typed is not None:
        runtime_settings.save_endpoint_key(provider, payload.openai_base_url, typed, actor=user.username)
    if payload.judgement_api_key is not None and payload.judgement_model_name.strip():
        runtime_settings.save_endpoint_key(*runtime_settings.judgement_endpoint({
            "LLM_PROVIDER": provider,
            "OPENAI_BASE_URL": payload.openai_base_url,
            "JUDGEMENT_PROVIDER": payload.judgement_provider,
            "JUDGEMENT_BASE_URL": payload.judgement_base_url,
        }), payload.judgement_api_key, actor=user.username)

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

    Never a credential: those stay write-only. Each endpoint keeps the key last
    saved for it (`runtime_settings.endpoint_keys`), so picking a profile picks
    its key too.
    """

    id: str
    label: str
    target: str = "build"
    llm_provider: str | None = None
    openai_base_url: str | None = None
    model_name: str | None = None
    model_context_window: int | None = None
    model_max_output_tokens: int | None = None
    thinking_mode: str | None = None
    thinking_effort: str | None = None
    judgement_provider: str | None = None
    judgement_base_url: str | None = None
    judgement_model_name: str | None = None
    judgement_context_window: int | None = None
    judgement_max_output_tokens: int | None = None
    escalate_after_attempts: int | None = None
    plan_on_judgement_model: bool | None = None
    updated_at: str | None = None
    updated_by: str | None = None


class LocalModelSettingsPayload(BaseModel):
    """Save the local build model configuration specifically."""

    llm_provider: str = Field(default="local")
    openai_base_url: str = Field(default="")
    model_name: str = Field(default="")
    model_context_window: int = Field(default=0, ge=0, le=MAX_CONTEXT_WINDOW)
    model_max_output_tokens: int = Field(default=0, ge=0, le=MAX_CONTEXT_WINDOW)
    thinking_mode: Literal["default", "on", "off"] = Field(default="default")
    thinking_effort: Literal["low", "medium", "high"] = Field(default="medium")
    api_key: str | None = Field(default=None, max_length=512, repr=False)

    @field_validator("api_key")
    @classmethod
    def _clean_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned.startswith("****") or any(c in cleaned for c in "\n\r\x00"):
            return None
        return cleaned


class FrontierModelSettingsPayload(BaseModel):
    """Save the frontier judgement model configuration specifically, or select No Model."""

    judgement_provider: str = Field(default="")
    judgement_base_url: str = Field(default="")
    judgement_model_name: str = Field(default="")
    judgement_context_window: int = Field(default=0, ge=0, le=MAX_CONTEXT_WINDOW)
    judgement_max_output_tokens: int = Field(default=0, ge=0, le=MAX_CONTEXT_WINDOW)
    judgement_api_key: str | None = Field(default=None, max_length=512, repr=False)
    escalate_after_attempts: int = Field(default=2, ge=1, le=10)
    plan_on_judgement_model: bool = Field(default=True)
    no_model: bool = Field(default=False, description="Explicitly select no frontier model (local only).")

    @field_validator("judgement_api_key")
    @classmethod
    def _clean_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned.startswith("****") or any(c in cleaned for c in "\n\r\x00"):
            return None
        return cleaned


@settings_router.put("/local", response_model=SettingsView)
async def update_local_model_settings(
    payload: LocalModelSettingsPayload,
    user: UserInDB = Depends(require_admin),
) -> SettingsView:
    """Save only the local build model settings and remember its profile."""
    _check_read_only()
    runtime_settings.save(
        {
            "llm_provider": payload.llm_provider,
            "openai_base_url": payload.openai_base_url,
            "model_name": payload.model_name,
            "model_context_window": str(payload.model_context_window) if payload.model_context_window else "",
            "model_max_output_tokens": str(payload.model_max_output_tokens) if payload.model_max_output_tokens else "",
            "thinking_mode": payload.thinking_mode,
            "thinking_effort": payload.thinking_effort,
        },
        actor=user.username,
    )
    if payload.api_key is not None:
        provider = (payload.llm_provider or "local").strip().lower()
        runtime_settings.save_endpoint_key(provider, payload.openai_base_url, payload.api_key, actor=user.username)
        key_var = {"anthropic": "anthropic_api_key", "gemini": "google_api_key", "google": "google_api_key"}.get(
            provider, "openai_api_key"
        )
        runtime_settings.save_secrets({key_var: payload.api_key}, actor=user.username)

    try:
        from app.server import model_profiles

        model_profiles.remember(payload.model_dump(), target="build", actor=user.username)
    except Exception:
        logger.warning("Could not remember the local model profile", exc_info=True)

    record_audit(
        actor=user.username,
        tenant_id=user.tenant_id,
        action="settings.local_model.update",
        subject="local-model-configuration",
        detail={
            "llm_provider": payload.llm_provider,
            "openai_base_url": payload.openai_base_url,
            "model_name": payload.model_name,
        },
    )
    return _current_view()


@settings_router.put("/frontier", response_model=SettingsView)
async def update_frontier_model_settings(
    payload: FrontierModelSettingsPayload,
    user: UserInDB = Depends(require_admin),
) -> SettingsView:
    """Save only the frontier judgement model settings, or select No Model to turn it off."""
    _check_read_only()
    if payload.no_model or not payload.judgement_model_name.strip():
        runtime_settings.save(
            {
                "judgement_provider": "",
                "judgement_base_url": "",
                "judgement_model_name": "",
                "judgement_context_window": "0",
                "judgement_max_output_tokens": "",
            },
            actor=user.username,
        )
        record_audit(
            actor=user.username,
            tenant_id=user.tenant_id,
            action="settings.frontier_model.update",
            subject="frontier-model-configuration",
            detail={"no_model": True, "selected_model": "none"},
        )
        return _current_view()

    runtime_settings.save(
        {
            "judgement_provider": payload.judgement_provider,
            "judgement_base_url": payload.judgement_base_url,
            "judgement_model_name": payload.judgement_model_name.strip(),
            "judgement_context_window": (
                str(payload.judgement_context_window) if payload.judgement_context_window else ""
            ),
            "judgement_max_output_tokens": (
                str(payload.judgement_max_output_tokens) if payload.judgement_max_output_tokens else ""
            ),
            "escalate_after_attempts": str(payload.escalate_after_attempts),
            "plan_on_judgement_model": "true" if payload.plan_on_judgement_model else "false",
        },
        actor=user.username,
    )
    if payload.judgement_api_key is not None:
        effective = runtime_settings.effective_environment()
        runtime_settings.save_endpoint_key(
            *runtime_settings.judgement_endpoint({
                "LLM_PROVIDER": effective.get("LLM_PROVIDER", "local"),
                "OPENAI_BASE_URL": effective.get("OPENAI_BASE_URL", ""),
                "JUDGEMENT_PROVIDER": payload.judgement_provider,
                "JUDGEMENT_BASE_URL": payload.judgement_base_url,
            }),
            payload.judgement_api_key,
            actor=user.username,
        )
        runtime_settings.save_secrets({"judgement_api_key": payload.judgement_api_key}, actor=user.username)

    try:
        from app.server import model_profiles

        model_profiles.remember(payload.model_dump(), target="frontier", actor=user.username)
    except Exception:
        logger.warning("Could not remember the frontier model profile", exc_info=True)

    record_audit(
        actor=user.username,
        tenant_id=user.tenant_id,
        action="settings.frontier_model.update",
        subject="frontier-model-configuration",
        detail={
            "judgement_provider": payload.judgement_provider,
            "judgement_base_url": payload.judgement_base_url,
            "judgement_model_name": payload.judgement_model_name.strip(),
            "no_model": False,
        },
    )
    return _current_view()


@settings_router.get("/frontier/status")
async def frontier_status(user: UserInDB = Depends(get_current_active_user)) -> dict[str, Any]:
    """Whether the frontier model a run would use is configured and answering - a model listing, never a model call."""
    from starlette.concurrency import run_in_threadpool

    from app.models.frontier_check import check_frontier

    return await run_in_threadpool(check_frontier)


@settings_router.get("/models", response_model=list[ModelProfile])
async def list_model_profiles(
    target: str | None = None,
    user: UserInDB = Depends(get_current_active_user),
) -> list[ModelProfile]:
    """Every model configuration saved so far, most recently saved first."""
    from app.server import model_profiles

    return [ModelProfile(**profile) for profile in model_profiles.list_profiles(target=target)]


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
