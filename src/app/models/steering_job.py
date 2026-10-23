"""The settings page's "diagnose this model" action: diagnose the serving model, save what it needs against it, show it.

Run in the worker (`tasks.diagnose_the_model`), which reaches the model server
the way a run does. A few minutes of small requests: the tool diagnosis
(`diagnostics`), reply salvage (`reply_salvage`) and the deep diagnosis with
its steering profile (`deep_diagnosis`, `guidance`) - all measured afresh,
since the owner asks for it after changing something. While it runs, and when
it ends, its state is a small file the page polls (`status`).

Refused while a run is live: the diagnosis would share the model's slots with
the run, slowing it and making its measurements the diagnosis's too.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _status_file() -> Path:
    return Path(os.environ.get("DATA_DIR") or "data") / "model-fitness" / "_diagnosis-status.json"


def set_status(status: str, message: str = "") -> None:
    path = _status_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": status, "message": message,
                                "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}), encoding="utf-8")


def status() -> dict[str, str]:
    try:
        found = json.loads(_status_file().read_text(encoding="utf-8"))
        return {"status": str(found.get("status") or "idle"), "message": str(found.get("message") or "")}
    except (OSError, ValueError):
        return {"status": "idle", "message": ""}


def run() -> None:
    """Diagnose the serving model afresh and keep everything against it. Never raises; failure is a status."""
    try:
        from app.models import build_default_chat_model, deep_diagnosis, diagnostics, reply_salvage, server_profile

        set_status("running", "asking the model the tool questions")
        server_profile.record()
        model = build_default_chat_model()
        name = reply_salvage.served_name(model)
        tools = diagnostics.diagnose(model, name)
        diagnostics.keep(tools)
        set_status("running", "measuring whether a cut-off reply can be finished")
        reply_salvage.measure(model, name)
        set_status("running", "asking the stage-shaped questions, with and without each guide")
        workers = (server_profile.current().slots if server_profile.current() is not None else None) or 1
        deep_diagnosis.keep(deep_diagnosis.diagnose(model, name, workers=workers))
        diagnostics.apply(model, diagnostics.recorded(name))
        set_status("idle", f"{name} diagnosed and its guidance saved")
    except Exception as error:  # noqa: BLE001 - the page shows why
        logger.warning("The model's diagnosis failed", exc_info=True)
        set_status("failed", f"{type(error).__name__}: {str(error)[:300]}")


def view() -> dict[str, Any]:
    """What the settings page shows of the serving model's steering."""
    from app.models import deep_diagnosis, diagnostics, guidance
    from app.models.model_guidance import served_now

    name = served_now()
    profile = guidance.recorded(name) if name else None
    deep = deep_diagnosis.recorded(name) if name else None
    tools = diagnostics.recorded(name) if name else None
    checks = []
    area = {check: g.area for g in guidance.GUIDES for check in g.checks}
    for result in (deep or {}).get("baseline") or []:
        checks.append({"name": result["check"], "area": area.get(result["check"], "instructions"),
                       "passed": result["passed"], "tries": result["tries"]})
    store_rows: dict[str, str] = {}
    try:
        from app.server.plugin_store import PluginStore

        store = PluginStore.shared()
        store_rows = {g.id: store.get_instructions(guidance.PREFIX + g.id) or "" for g in guidance.GUIDES}
    except Exception:  # noqa: BLE001
        pass
    guides = []
    for g in guidance.GUIDES:
        guides.append({
            "id": g.id, "title": g.title, "area": g.area, "text": store_rows.get(g.id) or g.line,
            "switch": g.switch, "switch_on": guidance.switch_on(g),
            "chosen": bool(profile and profile.chosen.get(g.id)),
            "override": (profile.overrides.get(g.id) if profile else None),
            "active": bool(profile and profile.active(g)),
        })
    settings = {
        "structured_answers": tools.settings.structured_answers if tools else "forced",
        "reasoning_effort": (tools.settings.least_reasoning_effort or "not honoured") if tools else "",
        "reply_ceiling": (deep or {}).get("reply_ceiling"),
        "tail_reminder": bool(profile and profile.tail_reminder),
    }
    return {"model": name, "measured_at": (profile.measured_at if profile else None) or None, **status(),
            "tier": (profile.tier if profile else None) or None, "score": profile.score if profile else None,
            "checks": checks, "guides": guides, "settings": settings}


__all__ = ["run", "set_status", "status", "view"]
