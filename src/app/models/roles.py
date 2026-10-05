"""Which model each stage runs on.

Two tiers, the way a team has seniors and juniors. The stages that judge -
the architect, QA writing and reviewing the acceptance suite, the test rounds,
the fixes, the security and milestone reviews, the code review - run on the
judgement model. Everything else runs on the default model. With no judgement
model configured, every stage runs on the default model, exactly as before.

The judgement model is configured beside the default one (runtime settings
`judgement_*`, or the `JUDGEMENT_*` environment variables): a model name, and
optionally its own provider, address, key and context window. Anything left
empty is the default model's.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any, Mapping

logger = logging.getLogger(__name__)

#: The key each provider reads its credential from.
_KEY_FOR_PROVIDER = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def judgement_environment(environment: Mapping[str, str]) -> dict[str, str] | None:
    """The environment that builds the judgement model, or None when none is set."""
    name = str(environment.get("JUDGEMENT_MODEL") or "").strip()
    if not name:
        return None
    built = dict(environment)
    built["OPENAI_MODEL"] = name
    provider = str(environment.get("JUDGEMENT_PROVIDER") or "").strip().lower()
    default_provider = str(environment.get("LLM_PROVIDER") or "local").strip().lower()
    if provider:
        built["LLM_PROVIDER"] = provider
        if provider != default_provider:
            # Another provider is somewhere else. Inheriting the default
            # model's address sent a hosted judgement model's requests to the
            # local server; without one, the provider's own address applies.
            built.pop("OPENAI_BASE_URL", None)
    base_url = str(environment.get("JUDGEMENT_BASE_URL") or "").strip()
    if base_url:
        built["OPENAI_BASE_URL"] = base_url
    key = str(environment.get("JUDGEMENT_API_KEY") or "").strip()
    if key:
        built[_KEY_FOR_PROVIDER.get(built.get("LLM_PROVIDER", ""), "OPENAI_API_KEY")] = key
    window = str(environment.get("JUDGEMENT_CONTEXT_WINDOW") or "").strip()
    if window and window != "0":
        built["MODEL_CONTEXT_WINDOW"] = window
        # A reply ceiling pinned for the default model may not fit this one.
        built.pop("MODEL_MAX_OUTPUT_TOKENS", None)
    return built


def judgement_model_name(environment: Mapping[str, str]) -> str:
    """The judgement model's name, or "" when the default model judges too."""
    return str(environment.get("JUDGEMENT_MODEL") or "").strip()


#: Why the configured judgement model was replaced by the default on the graph
#: built last in this context, or None. A configured judgement model is a
#: promise of a stronger review; when it cannot be built the run says so in its
#: own history (`WorkflowRunner`), not only in a worker log nobody reads.
_DOWNGRADE: contextvars.ContextVar[str | None] = contextvars.ContextVar("judgement_downgrade", default=None)


def judgement_downgrade() -> str | None:
    """Why the configured judgement model is not in use, or None when it is (or none is configured)."""
    return _DOWNGRADE.get()


def build_judgement_model(default_model: Any, environment: Mapping[str, str] | None = None) -> Any:
    """The judgement model, or `default_model` when none is configured or it cannot be built."""
    _DOWNGRADE.set(None)
    if environment is None:
        try:
            from app.server.runtime_settings import effective_environment

            environment = effective_environment()
        except Exception:  # noqa: BLE001 - the deployed environment still stands
            import os

            environment = dict(os.environ)
    built = judgement_environment(environment)
    if built is None:
        return default_model
    try:
        from app.config import load_settings
        from app.models import build_default_chat_model

        model = build_default_chat_model(load_settings(built))
    except Exception as error:  # noqa: BLE001 - a broken second model must not stop the run
        logger.warning(
            "The judgement model %r could not be built; every stage uses the default model",
            built.get("OPENAI_MODEL"), exc_info=True,
        )
        _DOWNGRADE.set(
            f"The judgement model {built.get('OPENAI_MODEL')!r} could not be built "
            f"({type(error).__name__}), so the architect, QA, reviews, test rounds and fixes "
            "run on the default model: they are not independent reviews on this run. Fix "
            "the judgement model's settings, or clear it to make this the intended setup."
        )
        return default_model
    logger.info("Judgement stages run on %s", built.get("OPENAI_MODEL"))
    return model
