"""Whether the model reviewing a sprint can be shown images.

A page's screenshots help a reviewer only if its model reads images; sent to
one that does not, they cost a refused request or a context full of base64.
The owner can say so outright (`MODEL_READS_IMAGES=yes|no`); otherwise it is
decided from the provider and the model's name, and a model this cannot place
is taken not to read them - a review without pictures is the review there was
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
    if str(getattr(settings, "llm_provider", "") or "").strip().lower() in _PROVIDERS_THAT_SEE:
        return True
    return bool(_FAMILIES_THAT_SEE.search(str(getattr(settings, "model_name", "") or "")))


def the_reviewer_reads_images() -> bool:
    """Whether the model that judges this run - the judgement model when one is set - reads images.

    Never raises: settings that cannot be read are taken to say no.
    """
    try:
        from app.config import load_settings
        from app.models.roles import judgement_environment
        from app.server.runtime_settings import effective_environment

        environment = effective_environment()
        judging = judgement_environment(environment)
        return reads_images(load_settings(judging if judging is not None else environment))
    except Exception:  # noqa: BLE001
        return False


__all__ = ["reads_images", "the_reviewer_reads_images"]
