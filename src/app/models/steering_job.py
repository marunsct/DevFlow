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


#: How often a running job says it is still running.
HEARTBEAT_SECONDS = 30
#: A "running" status not refreshed for this long belongs to a job that is not
#: running: its worker restarted, a deploy stopped it, or none picked it up.
STALE_SECONDS = 120
#: What the page is told of such a job.
STOPPED = ("The diagnosis stopped without finishing - its worker restarted or none picked it up, or the model "
           "server went away. Start it again.")


def _now() -> float:
    import time

    return time.time()


def set_status(status: str, message: str = "") -> None:
    path = _status_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": status, "message": message, "beat": _now(),
                                "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}), encoding="utf-8")


def _beat() -> None:
    """The running status refreshed, its message kept."""
    try:
        found = json.loads(_status_file().read_text(encoding="utf-8"))
        if found.get("status") == "running":
            found["beat"] = _now()
            _status_file().write_text(json.dumps(found), encoding="utf-8")
    except (OSError, ValueError):
        pass


class _Beating:
    """While a job runs, its status is refreshed every `HEARTBEAT_SECONDS`, so a job that dies is seen to have."""

    def __enter__(self) -> "_Beating":
        import threading

        self._stop = threading.Event()

        def loop() -> None:
            while not self._stop.wait(HEARTBEAT_SECONDS):
                _beat()

        threading.Thread(target=loop, daemon=True, name="diagnosis-heartbeat").start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()


def status() -> dict[str, str]:
    """The job's state for the page; a "running" one whose heartbeat stopped is "failed", so it can be started again.

    Measured: the page stayed on "diagnosing" through a closed model server and
    a restart of every container - the file said running, nothing ever said
    otherwise, and the action refused to start while it did.
    """
    try:
        found = json.loads(_status_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "idle", "message": ""}
    state = str(found.get("status") or "idle")
    if state == "running" and _now() - float(found.get("beat") or 0) > STALE_SECONDS:
        return {"status": "failed", "message": STOPPED}
    return {"status": state, "message": str(found.get("message") or "")}


def run() -> None:
    """Diagnose the serving model afresh and keep everything against it. Never raises; failure is a status."""
    with _Beating():
        _run()


def _gone(model: Any) -> bool:
    """Whether the model server stopped answering during the job; said as the job's failure."""
    from app.models import diagnostics

    if diagnostics.the_model_answers(model):
        return False
    set_status("failed", "the model server stopped answering during the diagnosis - nothing from that part was "
                         "kept; load the model, then diagnose it again")
    return True


def _run() -> None:
    try:
        from app.models import build_default_chat_model, deep_diagnosis, diagnostics, reply_salvage, server_profile

        set_status("running", "asking the model the tool questions")
        server_profile.record()
        model = build_default_chat_model()
        name = reply_salvage.served_name(model)
        if not diagnostics.the_model_answers(model):
            set_status("failed", "the model server does not answer a request - load the model, then diagnose it")
            return
        tools = diagnostics.diagnose(model, name)
        if _gone(model):
            return
        diagnostics.keep(tools)
        set_status("running", "measuring whether a cut-off reply can be finished")
        reply_salvage.measure(model, name)
        set_status("running", "asking the stage-shaped questions, with and without each guide")
        workers = (server_profile.current().slots if server_profile.current() is not None else None) or 1
        deep = deep_diagnosis.diagnose(model, name, workers=workers)
        if _gone(model):
            return
        deep_diagnosis.keep(deep)
        diagnostics.apply(model, diagnostics.recorded(name))
        set_status("running", "finding what the model can do: an image, a schema, another language, its model card")
        from app.models import capabilities

        capabilities.fill(model, name, str(getattr(model, "model_name", "") or ""))
        set_status("idle", f"{name} diagnosed and its guidance and capabilities saved")
    except Exception as error:  # noqa: BLE001 - the page shows why
        logger.warning("The model's diagnosis failed", exc_info=True)
        set_status("failed", f"{type(error).__name__}: {str(error)[:300]}")


def fill_capabilities() -> None:
    """The settings page's "find what is missing": the serving model's capabilities found and kept. Never raises."""
    with _Beating():
        _fill_capabilities()


def _fill_capabilities() -> None:
    try:
        from app.models import build_default_chat_model, capabilities, reply_salvage, server_profile

        set_status("running", "finding what the model can do: an image, a schema, another language, its model card")
        server_profile.record()
        model = build_default_chat_model()
        name = reply_salvage.served_name(model)
        capabilities.fill(model, name, str(getattr(model, "model_name", "") or ""))
        set_status("idle", f"{name}: capabilities found and saved")
    except Exception as error:  # noqa: BLE001
        logger.warning("Finding the model's capabilities failed", exc_info=True)
        set_status("failed", f"{type(error).__name__}: {str(error)[:300]}")


def capabilities_view() -> dict[str, Any]:
    from app.models import capabilities
    from app.models.model_guidance import served_now

    name = served_now()
    return {"model": name, **status(), "fields": capabilities.resolved(name) if name else []}


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


__all__ = ["HEARTBEAT_SECONDS", "STALE_SECONDS", "STOPPED", "capabilities_view", "fill_capabilities", "run", "set_status", "status", "view"]
