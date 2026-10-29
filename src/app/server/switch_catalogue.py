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


#: What each premium bundle is, for the admin page; its features' own lines follow it.
BUNDLE_SUMMARIES = {
    "PREMIUM_MODEL_TUNING": "Adaptive model tuning: the model's reasoning and replies tuned to the model serving the run.",
    "PREMIUM_PROJECT_INTELLIGENCE": "Project intelligence: shared facts, project memory, the code graph and lessons from "
                                    "earlier runs, for every stage.",
    "PREMIUM_DEEP_VERIFICATION": "Deep verification: mutation-guided tests, the regression contract, page scoring, "
                                 "release audits and documents, and the specification's assumptions asked first.",
    "PREMIUM_CHANGE_REQUESTS": "Change requests: follow-up runs that change a finished product on request.",
}


def _a_bundle(name: str, stored: dict[str, bool]) -> dict[str, Any]:
    """A premium bundle's entry: its summary, the features it holds, and its value."""
    from app import switches
    from app.observability.provenance import SWITCHES, switch

    lines = []
    for member in switches.BUNDLES[name]:
        try:
            summary, _ = explanation(SWITCHES[member], switch(SWITCHES[member]))
        except Exception:  # noqa: BLE001 - one unreadable feature does not hide the bundle
            summary = "its module could not be read"
        lines.append(f"- {member}: {summary}")
    setting, environment = stored.get(name), switches.from_the_environment(name)
    on, source = ((setting, "setting") if setting is not None else
                  (environment, "docker") if environment is not None else (False, "default"))
    return {"name": name, "module": "app.switches", "summary": BUNDLE_SUMMARIES.get(name, name),
            "details": "\n".join(lines), "default": False, "docker": environment, "setting": setting,
            "on": on, "source": source}


def entries() -> list[dict[str, Any]]:
    """One entry a switch an operator sets - the premium bundles, then the experiments (owner, 2026-10-29).

    Built-in fixes are not listed: they are always on. A switch whose module cannot be read is listed as unreadable.
    """
    from app import switches
    from app.observability.provenance import SWITCHES, switch
    from app.server import runtime_settings

    stored = runtime_settings.switch_overrides()
    listed: list[dict[str, Any]] = [_a_bundle(name, stored) for name in switches.BUNDLES]
    for name, spec in ((name, SWITCHES[name]) for name in switches.EXPERIMENTS):
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


__all__ = ["BUNDLE_SUMMARIES", "entries", "explanation"]
