"""Instructions for one model, kept in the plugin-instruction table and added to every stage's prompt while it serves (behind `MODEL_GUIDANCE`).

The stack's guidance is a row of `plugin_instructions` per language and
framework (`app.plugins.seed`); a model's is a row too, under `model:<served
name>`, appended by the same middleware when that model is the one serving.
Like any row it can be edited in the table, and an edit is never overwritten.

What goes in it is measured, not written from a model card: the deep
diagnosis (`app.models.deep_diagnosis`) asks the model questions shaped like
the stages that went wrong for it, once without guidance and once with each
candidate line, and keeps only the lines that made it do as asked more often.
A model that needs none gets none - a line that changes nothing is prompt
every stage pays for.

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
    """The table key of the serving model's guidance, as one plugin key; [] when off or unknown."""
    if not enabled():
        return []
    served = served_now()
    return [key_for(served)] if served else []


def keep(served: str, lines: list[str]) -> None:
    """Keep `lines` as `served`'s guidance; an empty list clears it."""
    from app.server.plugin_store import PluginStore

    PluginStore.shared().update_instructions(key_for(served), "\n".join(f"- {line}" for line in lines))


def kept(served: str) -> str:
    try:
        from app.server.plugin_store import PluginStore

        return PluginStore.shared().get_instructions(key_for(served)) or ""
    except Exception:  # noqa: BLE001
        return ""


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


__all__ = ["ON_BY_DEFAULT", "PREFIX", "ceiling_for", "enabled", "guidance_key", "keep", "kept", "key_for",
           "deep_if_new", "served_now", "set_ceiling"]
