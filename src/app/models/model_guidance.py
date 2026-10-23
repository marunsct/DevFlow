"""The serving model's steering in every stage's request (behind `MODEL_GUIDANCE`).

The guidance itself is general - one catalogue, each item its own switch
(`app.models.guidance`) - and kept as `guide:<id>` rows of the plugin-
instruction table, which the plugin middleware appends after the stack's rows.
Which items a model gets, and whether it also gets them repeated at the end of
each request, is its steering profile, chosen by its deep diagnosis
(`app.models.deep_diagnosis`) and changed per item on the settings page. A
model that needs none gets none - a line that changes nothing is prompt every
stage pays for.

With it, a per-model reply ceiling: where the deployment leaves replies
uncapped and the model was measured to loop to its limit, its requests carry
the ceiling the diagnosis chose, so a loop ends in minutes instead of at the
request timeout. The deployment's own ceiling, when it sets one, wins.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `MODEL_GUIDANCE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The table key a model's guidance is kept under.
PREFIX = "model:"

_CEILINGS: dict[str, int] = {}
_LOCK = threading.Lock()


def enabled() -> bool:
    return is_on("MODEL_GUIDANCE", ON_BY_DEFAULT)


def key_for(served: str) -> str:
    from app.models.registry import _slug

    return PREFIX + _slug(served).lower()


def served_now() -> str:
    """The served model's name, as its measurements are kept under; "" when not known."""
    try:
        from app.models.server_profile import current

        profile = current()
        if profile is not None and profile.model:
            return profile.model
        from app.models import _runtime_settings

        return str(_runtime_settings().model_name or "")
    except Exception:  # noqa: BLE001
        return ""


def guidance_key() -> list[str]:
    """The table keys of the guides active for the serving model (`app.models.guidance`); [] when off or unknown."""
    if not enabled():
        return []
    served = served_now()
    if not served:
        return []
    from app.models.guidance import active_keys

    return active_keys(served)


def reminder() -> str:
    """The end-of-request reminder for the serving model, when its profile asks for one; "" otherwise."""
    if not enabled():
        return ""
    served = served_now()
    if not served:
        return ""
    from app.models.guidance import reminder as its_reminder

    return its_reminder(served)


def deep_if_new(model: Any) -> None:
    """The serving model's deep diagnosis, made now when it has none and kept. Never raises; nothing when off."""
    if not enabled():
        return
    try:
        from app.models import deep_diagnosis
        from app.models.reply_salvage import served_name

        name = served_name(model)
        if deep_diagnosis.recorded(name) is not None:
            return
        try:
            from app.models.server_profile import current

            workers = (current().slots if current() is not None else None) or 1
        except Exception:  # noqa: BLE001
            workers = 1
        deep_diagnosis.keep(deep_diagnosis.diagnose(model, name, workers=workers))
    except Exception:  # noqa: BLE001
        logger.debug("Could not make the deep diagnosis", exc_info=True)


def set_ceiling(server: tuple[str, str], tokens: int | None) -> None:
    with _LOCK:
        if tokens:
            _CEILINGS[server] = int(tokens)
        else:
            _CEILINGS.pop(server, None)


def ceiling_for(server: tuple[str, str]) -> int | None:
    """The reply ceiling chosen for this server's model, when on and the deployment sets none."""
    if not enabled():
        return None
    with _LOCK:
        return _CEILINGS.get(server)


__all__ = ["ON_BY_DEFAULT", "PREFIX", "ceiling_for", "deep_if_new", "enabled", "guidance_key", "key_for", "reminder",
           "served_now", "set_ceiling"]
