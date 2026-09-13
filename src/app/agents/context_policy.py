"""Thresholds that keep an agent's conversation inside the model's window.

Read from the effective environment - the deployed environment plus any
override an administrator has stored - so a value can be changed without a
rebuild. Every field has a default that works unconfigured.

Deliberately not wired into `SETTABLE_KEYS`: that map is what the settings API
writes through, and its request model has a fixed set of fields. Adding keys
there without extending that model would produce settings nothing can write.
"""

from __future__ import annotations

import logging
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ContextPolicy(BaseModel):
    """How much context an agent may use, and when to compact it."""

    model_config = ConfigDict(extra="forbid")

    max_context_tokens: int = Field(
        default=200_000,
        description="The model's usable input window, in tokens.",
    )
    soft_trigger_ratio: float = Field(
        default=0.8,
        ge=0.1,
        le=0.95,
        description="Fraction of the window at which compaction runs.",
    )
    keep_recent_messages: int = Field(
        default=15,
        ge=2,
        description="Messages left untouched at the tail when compacting.",
    )
    trim_tokens_to_summarize: int = Field(
        default=4_000,
        ge=500,
        description="Token budget the summariser itself may spend.",
    )
    compaction_model: str = Field(
        default="",
        description="Model id for summarising. Empty means use the run's own model.",
    )
    enabled: bool = Field(
        default=True,
        description="Master switch. False removes the middleware entirely.",
    )

    @property
    def trigger_tokens(self) -> int:
        """Absolute token count at which compaction runs."""
        return int(self.max_context_tokens * self.soft_trigger_ratio)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "ContextPolicy":
        """Build the policy from CTX_* variables, falling back to defaults.

        Never raises. A malformed value logs a warning and yields the default,
        because a typo in one threshold must not stop every agent from starting.
        """
        if environment is None:
            from app.server.runtime_settings import effective_environment

            try:
                environment = effective_environment()
            except Exception:  # noqa: BLE001 - the environment is still valid config
                import os

                environment = dict(os.environ)

        def _read(name: str, default, cast):
            raw = str(environment.get(name, "")).strip()
            if not raw:
                return default
            try:
                return cast(raw)
            except (TypeError, ValueError):
                logger.warning("Ignoring malformed %s=%r; using %r", name, raw, default)
                return default

        def _flag(raw: str) -> bool:
            return raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            max_context_tokens=_read("CTX_MAX_TOKENS", 75_000, int),
            soft_trigger_ratio=_read("CTX_SOFT_TRIGGER_RATIO", 0.8, float),
            keep_recent_messages=_read("CTX_KEEP_MESSAGES", 15, int),
            trim_tokens_to_summarize=_read("CTX_SUMMARY_BUDGET", 4_000, int),
            compaction_model=str(environment.get("CTX_COMPACTION_MODEL", "")).strip(),
            enabled=_read("CTX_COMPACTION_ENABLED", True, _flag),
        )


__all__ = ["ContextPolicy"]
