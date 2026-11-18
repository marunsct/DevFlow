"""A shorter system prompt for a model measured strong (deep review 2026-11-18, item C7, behind `LEAN_PROMPTS_FOR_STRONG_MODELS`).

A role's system prompt is 15-19k characters, and much of it was written against a small local model's measured
failures: an answer written into the conversation instead of returned, a whole file composed in reasoning and never
written, a result saved to a file. A model the deep diagnosis measures strong (`app.models.guidance.tier_of`) is
already given none of the model guides; with this switch on it is also not given those blocks. The role's own
description, its responsibilities, the stack's facts, the stage's rules and the tools' rules stay as they are: only
the blocks listed in `WEAK_MODEL_ONLY` are left out, and only for a model whose recorded tier is strong.

Optional and in doubt until measured on a strong hosted model, so a switch, off in code.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False


class _LeanPrompts:
    """`LEAN_PROMPTS_FOR_STRONG_MODELS` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("A model the diagnosis measured strong is not given the prompt blocks written against a small "
                   "model's failures (how to return the answer, reasoning is not work, a result is not a file); "
                   "its role, the stack's facts and the stage's rules stay whole.")

    @staticmethod
    def enabled() -> bool:
        return is_on("LEAN_PROMPTS_FOR_STRONG_MODELS", _LeanPrompts.ON_BY_DEFAULT)


lean_prompts_switch = _LeanPrompts()


def enabled() -> bool:
    return lean_prompts_switch.enabled()


def _weak_model_only() -> tuple[str, ...]:
    """The blocks written against a small model's measured failures, as each prompt carries them."""
    from app.agents.role_agent import ARTIFACTS_ARE_NOT_THE_ANSWER, REASONING_IS_NOT_WORK
    from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

    return (STRUCTURED_RESPONSE_RULE, REASONING_IS_NOT_WORK, ARTIFACTS_ARE_NOT_THE_ANSWER)


def lean(prompt: str) -> str:
    """`prompt` without the blocks only a weaker model needs, and without the blank lines they leave."""
    for block in _weak_model_only():
        prompt = prompt.replace(block, "")
    return re.sub(r"\n{3,}", "\n\n", prompt)


def tier_of(model: Any) -> str:
    """The recorded tier of the model serving `model` ("strong", "standard", "weak"), or "" when never measured."""
    try:
        from app.models.guidance import recorded
        from app.models.reply_salvage import served_name

        profile = recorded(served_name(model))
    except Exception:  # noqa: BLE001 - never measured
        return ""
    return str(getattr(profile, "tier", "") or "")


def for_the_model(prompt: str, model: Any) -> str:
    """`prompt` as `model` is given it: lean for a model measured strong while the switch is on, else as it is."""
    if not enabled() or tier_of(model) != "strong":
        return prompt
    return lean(prompt)


__all__ = ["ON_BY_DEFAULT", "enabled", "for_the_model", "lean", "lean_prompts_switch", "tier_of"]
