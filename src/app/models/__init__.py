"""Shared chat-model factory for Deep Agents role workers.

Every role agent (Product Manager, Tools and Models Architect, Principal
Architect, Scrum Master, Technical Lead, specialists) needs the same provider
connection details: base URL, API key, and model name. Centralizing that
lookup here means each new agent module does not re-implement environment
loading or default handling; only this module changes if the provider setup
changes.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import Settings, load_settings
from .router import ModelRouter


class CompatibleChatOpenAI(ChatOpenAI):
    """`ChatOpenAI` that omits ``name`` on everything except tool messages.

    LangChain serializes a message's ``name`` onto the wire for ``system``,
    ``user`` and ``assistant`` roles. The OpenAI API tolerates that - it is an
    optional participant label - but several OpenAI-*compatible* servers apply
    the stricter reading and reject the whole request:

        400 - messages.2: Value error, "name" is only valid on role="tool" messages.

    That is fatal rather than cosmetic: the request never reaches the model, so
    the stage fails outright. Nothing here needs the field either - deepagents
    sets it to the agent's own name as bookkeeping, and no prompt in this
    workflow addresses a named participant - so it is dropped on the way out
    rather than being made a setting nobody would know to turn on.

    ``_get_request_payload`` is the single place the request dict is assembled,
    so overriding it covers invoke, stream, batch, tool calls and structured
    output alike.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):  # type: ignore[override]
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for message in payload.get("messages", []):
            if isinstance(message, dict) and message.get("role") != "tool":
                message.pop("name", None)
        return payload


def _fallback_model(env_var: str, default: str) -> str:
    """Fallback model ids come from configuration, not from source.

    They were hardcoded, and the Anthropic one had aged out - a provider
    deprecation should be a config change, not a code change.
    """
    import os

    return os.environ.get(env_var, default).strip() or default


def _runtime_settings() -> Settings:
    """Settings including admin overrides, falling back to the environment.

    Imported lazily and guarded: this module is used by the CLI and by tests
    that have no database, and a model factory must not start requiring one.
    """
    try:
        from app.server.runtime_settings import effective_settings

        return effective_settings()
    except Exception:  # noqa: BLE001 - the environment is still a valid config
        return load_settings()


def build_default_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Construct the chat model role agents use, from validated settings.

    Passing a real `ChatOpenAI` instance to `create_deep_agent` (instead of a
    bare "openai:<model>" string) means the client is built from our own
    validated `Settings`, so behavior does not depend on whether some other
    part of the process happened to load `.env` first.
    """
    # `effective_settings` is `load_settings` plus anything an administrator has
    # changed through the settings API. Reading the bare environment here meant a
    # corrected model URL never reached the worker that actually calls the model.
    resolved_settings = settings or _runtime_settings()
    
    primary = None
    fallback = None

    if resolved_settings.llm_provider == "anthropic":
        primary = ChatAnthropic(
            api_key=resolved_settings.anthropic_api_key,
            model=resolved_settings.model_name,
            max_retries=3,
        )
        if resolved_settings.openai_api_key:
            fallback = CompatibleChatOpenAI(
                api_key=resolved_settings.openai_api_key,
                model=_fallback_model("OPENAI_FALLBACK_MODEL", "gpt-4o-mini"),
                max_retries=3,
            )
    elif resolved_settings.llm_provider == "gemini":
        primary = ChatGoogleGenerativeAI(
            api_key=resolved_settings.google_api_key,
            model=resolved_settings.model_name,
            max_retries=3,
        )
        if resolved_settings.openai_api_key:
            fallback = CompatibleChatOpenAI(
                api_key=resolved_settings.openai_api_key,
                model=_fallback_model("OPENAI_FALLBACK_MODEL", "gpt-4o-mini"),
                max_retries=3,
            )
    else:
        # Defaults to OpenAI or Local
        primary = CompatibleChatOpenAI(
            base_url=resolved_settings.openai_base_url,
            api_key=resolved_settings.openai_api_key,
            model=resolved_settings.model_name,
            max_retries=3,
        )
        # If it's a local model that fails, fallback to Anthropic if available
        if resolved_settings.openai_base_url and resolved_settings.anthropic_api_key:
             fallback = ChatAnthropic(
                api_key=resolved_settings.anthropic_api_key,
                model=_fallback_model("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5-20251001"),
                max_retries=3,
             )

    models = [{"name": "primary", "model": primary}]
    if fallback:
        models.append({"name": "fallback", "model": fallback})

    # A per-configuration router rather than one process-wide singleton that
    # every agent construction reset: two runs with different provider settings
    # in the same worker used to overwrite each other's models.
    router = ModelRouter.for_configuration(resolved_settings, models)
    return router.get_healthy_model()


__all__ = ["build_default_chat_model"]
