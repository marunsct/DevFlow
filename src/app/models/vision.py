"""Whether the model reviewing a sprint can be shown images.

A page's screenshots help a reviewer only if its model reads images; sent to
one that does not, they cost a refused request or a context full of base64.
The owner can say so outright (`MODEL_READS_IMAGES=yes|no`); otherwise what
the model was measured to do (`capabilities.measure`: shown a red square, it
names the colour), and only then the provider and the model's name - a model
none of these can place is taken not to read them - a review without pictures is the review there was
before, while a refused request is a stage lost.
"""

from __future__ import annotations

import re
from typing import Any

#: Providers whose current models all read images.
_PROVIDERS_THAT_SEE = frozenset({"anthropic", "gemini"})

#: Model-name families known to read images, matched as a word in the name.
_FAMILIES_THAT_SEE = re.compile(
    r"(?:^|[-_/.:\s])(?:vl|vision|llava|bakllava|pixtral|minicpm-v|glm-4v|glm-4\.\dv|internvl|molmo"
    r"|gpt-4o|gpt-4\.1|gpt-5|o3|o4-mini|claude|gemini)(?:$|[-_/.:\s\d])",
    re.I,
)

_YES = frozenset({"yes", "true", "on", "1"})
_NO = frozenset({"no", "false", "off", "0"})


def reads_images(settings: Any) -> bool:
    """Whether the model these settings name can be shown images."""
    choice = str(getattr(settings, "model_reads_images", "auto") or "auto").strip().lower()
    if choice in _YES:
        return True
    if choice in _NO:
        return False
    # What the model was found to do - shown a red square, it named the
    # colour or did not (`capabilities`) - before any guess from its name.
    measured = _measured(str(getattr(settings, "model_name", "") or ""))
    if measured is not None:
        return measured
    if str(getattr(settings, "llm_provider", "") or "").strip().lower() in _PROVIDERS_THAT_SEE:
        return True
    return bool(_FAMILIES_THAT_SEE.search(str(getattr(settings, "model_name", "") or "")))


def _measured(model_name: str) -> bool | None:
    """The kept `reads_images` capability of this model - under its served name or its configured one - or None."""
    try:
        from app.models.capabilities import value
        from app.models.model_guidance import served_now

        for name in dict.fromkeys(n for n in (served_now(), model_name) if n):
            found = value(name, "reads_images")
            if isinstance(found, bool):
                return found
    except Exception:  # noqa: BLE001 - unknown
        pass
    return None


def the_build_model_reads_images() -> bool:
    """Whether the model that builds and fixes reads images. Never raises: settings that cannot be read say no."""
    try:
        from app.config import load_settings
        from app.server.runtime_settings import effective_environment

        return reads_images(load_settings(effective_environment()))
    except Exception:  # noqa: BLE001
        return False


def the_reviewer_reads_images() -> bool:
    """Whether the model that judges this run - the judgement model when one is set - reads images.

    Never raises: settings that cannot be read are taken to say no.
    """
    try:
        from app.config import load_settings
        from app.models.roles import build_model_only, judgement_environment
        from app.server.runtime_settings import effective_environment

        environment = effective_environment()
        judging = None if build_model_only() else judgement_environment(environment)
        return reads_images(load_settings(judging if judging is not None else environment))
    except Exception:  # noqa: BLE001
        return False


__all__ = ["reads_images", "the_build_model_reads_images", "the_reviewer_reads_images"]
