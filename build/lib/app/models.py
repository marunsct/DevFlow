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
            max_retries=2,
        )
        if resolved_settings.openai_api_key:
            fallback = ChatOpenAI(
                api_key=resolved_settings.openai_api_key,
                model="gpt-4o-mini",
            )
    elif resolved_settings.llm_provider == "gemini":
        primary = ChatGoogleGenerativeAI(
            api_key=resolved_settings.google_api_key,
            model=resolved_settings.model_name,
            max_retries=2,
        )
        if resolved_settings.openai_api_key:
            fallback = ChatOpenAI(
                api_key=resolved_settings.openai_api_key,
                model="gpt-4o-mini",
            )
    else:
        # Defaults to OpenAI or Local
        primary = ChatOpenAI(
            base_url=resolved_settings.openai_base_url,
            api_key=resolved_settings.openai_api_key,
            model=resolved_settings.model_name,
            max_retries=2,
        )
        # If it's a local model that fails, fallback to Anthropic if available
        if resolved_settings.openai_base_url and resolved_settings.anthropic_api_key:
             fallback = ChatAnthropic(
                api_key=resolved_settings.anthropic_api_key,
                model="claude-3-haiku-20240307",
             )

    if fallback:
        return primary.with_fallbacks([fallback])
    return primary


__all__ = ["build_default_chat_model"]
