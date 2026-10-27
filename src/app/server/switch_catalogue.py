"""Every switch, what it does and where its value comes from, for the admin page (`/admin`).

The list is `observability.provenance.SWITCHES`, the registry each run's KPI row
already reads, so a switch added there appears here with nothing else to do.
Each entry's explanation is the switch's own documentation: what its object
says of itself (`explanation`), a guide's title and line, its `enabled`
function's docstring, or its module's docstring, in that order. The value is
the admin page's setting when one is stored, else the deployed environment
(the compose file), else the code's own default (`ON_BY_DEFAULT`).
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _paragraphs(text: str) -> tuple[str, str]:
    """The first paragraph of `text` on one line, and the rest as written."""
    parts = [part.strip() for part in str(text or "").strip().split("\n\n") if part.strip()]
    if not parts:
        return "", ""
    return " ".join(parts[0].split()), "\n\n".join(parts[1:])


def explanation(spec: str, obj: Any) -> tuple[str, str]:
    """`(summary, details)` for the switch `spec` names, from its own documentation."""
    if ":" not in spec:
        return _paragraphs(inspect.getdoc(obj) or "")
    said = getattr(obj, "explanation", "")
    if said:
        return " ".join(str(said).split()), ""
    guide = getattr(obj, "guide", None)
    if guide is not None:
        return f"{guide.title}: {' '.join(str(guide.line).split())}", (
            f"A model guide in the {guide.area} area. The model guidance on the Settings page chooses it per "
            "model; this switch turns it off for every model when it is off.")
    enabled = getattr(obj, "enabled", None)
    if callable(enabled) and inspect.getdoc(enabled):
        return _paragraphs(inspect.getdoc(enabled) or "")
    return _paragraphs(inspect.getdoc(inspect.getmodule(obj)) or "")


def entries() -> list[dict[str, Any]]:
    """One entry a switch, in the registry's order. A switch whose module cannot be read is listed as unreadable."""
    from app import switches
    from app.observability.provenance import SWITCHES, switch
    from app.server import runtime_settings

    stored = runtime_settings.switch_overrides()
    listed: list[dict[str, Any]] = []
    for name, spec in SWITCHES.items():
        entry: dict[str, Any] = {"name": name, "module": spec}
        setting = stored.get(name)
        environment = switches.from_the_environment(name)
        try:
            obj = switch(spec)
            default = bool(getattr(obj, "ON_BY_DEFAULT", False))
            summary, details = explanation(spec, obj)
        except Exception:  # noqa: BLE001 - one unreadable module does not hide the others
            logger.warning("Could not read the switch %s", name, exc_info=True)
            default, summary, details = False, "This switch's module could not be read.", ""
        if setting is not None:
            on, source = setting, "setting"
        elif environment is not None:
            on, source = environment, "docker"
        else:
            on, source = default, "default"
        entry.update(summary=summary, details=details, default=default, docker=environment, setting=setting,
                     on=on, source=source)
        listed.append(entry)
    return listed


__all__ = ["entries", "explanation"]
