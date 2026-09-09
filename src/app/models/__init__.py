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


def _fallback_model(env_var: str, default: str) -> str:
    """Fallback model ids come from configuration, not from source.

    They were hardcoded, and the Anthropic one had aged out - a provider
    deprecation should be a config change, not a code change.
    """
    import os

    return os.environ.get(env_var, default).strip() or default


def build_default_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Construct the chat model role agents use, from validated settings.

    Passing a real `ChatOpenAI` instance to `create_deep_agent` (instead of a
    bare "openai:<model>" string) means the client is built from our own
    validated `Settings`, so behavior does not depend on whether some other
    part of the process happened to load `.env` first.
    """
    resolved_settings = settings or load_settings()
    
    primary = None
    fallback = None

    if resolved_settings.llm_provider == "anthropic":
        primary = ChatAnthropic(
            api_key=resolved_settings.anthropic_api_key,
            model=resolved_settings.model_name,
            max_retries=3,
        )
        if resolved_settings.openai_api_key:
            fallback = ChatOpenAI(
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
            fallback = ChatOpenAI(
                api_key=resolved_settings.openai_api_key,
                model=_fallback_model("OPENAI_FALLBACK_MODEL", "gpt-4o-mini"),
                max_retries=3,
            )
    else:
        # Defaults to OpenAI or Local
        primary = ChatOpenAI(
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
