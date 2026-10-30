"""What the build model's server says of itself: slots, per-slot context, quantisation (Initiative M.1).

Measured across runs: forty-odd calls refused with "Context size has been
exceeded" at 20,000-48,000 input tokens, while the harness budgeted for a
100,000-token window. They came in parallel waves - six stages at once on a
server that splits its context across its slots, so each request had a slot's
share, not the whole. The settings name the window the owner meant; the
server's `/props` names the one each request actually gets, and how many
requests it serves at once.

Read once per run segment in the worker (`record`), with one GET and never a
model call, and consulted by the context budget and the parallel cap without
touching the network (`current`). A server without `/props` - any hosted API -
records nothing and changes nothing.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PROPS_TIMEOUT_SECONDS = 5

#: A quantisation tag in a GGUF file name, and its bits per weight.
_QUANT = re.compile(r"(?<![A-Za-z0-9])(I?Q[1-8](?:_[A-Z0-9]+)*|F16|BF16|F32)(?![A-Za-z0-9])", re.I)


@dataclass(frozen=True)
class ServerProfile:
    slots: int | None = None
    slot_context: int | None = None
    quantisation: str = ""
    #: The model file the server holds, by its name.
    model: str = ""
    #: Whether the server holds a vision part for it (`modalities.vision`); None when it does not say.
    reads_images: bool | None = None

    @property
    def bits(self) -> int | None:
        """Bits per weight the quantisation names, or None."""
        q = self.quantisation.upper()
        if q in ("F16", "BF16"):
            return 16
        if q == "F32":
            return 32
        found = re.match(r"I?Q(\d)", q)
        return int(found.group(1)) if found else None

    def advisory(self) -> str:
        """A warning for a tool-calling model at four bits or fewer; else ""."""
        if self.bits is not None and self.bits <= 4:
            return (f"served as {self.quantisation} ({self.bits}-bit): low-bit builds call tools "
                    "that do not exist and break long tool arguments more often; a higher-bit "
                    "build of the same model is recommended")
        return ""


def from_props(props: dict[str, Any]) -> ServerProfile:
    """The profile from a llama.cpp-style `/props` body."""
    slots = props.get("total_slots")
    context = (props.get("default_generation_settings") or {}).get("n_ctx")
    path = str(props.get("model_path") or "")
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    found = _QUANT.findall(name)
    vision = (props.get("modalities") or {}).get("vision") if isinstance(props.get("modalities"), dict) else None
    return ServerProfile(
        slots=slots if isinstance(slots, int) and slots > 0 else None,
        slot_context=context if isinstance(context, int) and context > 0 else None,
        quantisation=found[-1].upper() if found else "",
        model=name,
        reads_images=vision if isinstance(vision, bool) else None,
    )


def read(base_url: str, api_key: str = "") -> ServerProfile | None:
    """GET `/props` beside the OpenAI-compatible `base_url`; None when the server has none. Never raises."""
    if not base_url:
        return None
    try:
        from app.models.endpoints import reached_from_here

        reached, naming = reached_from_here(base_url.rstrip("/"))
        root = reached[:-3] if reached.endswith("/v1") else reached
        request = urllib.request.Request(
            root + "/props", headers={**({"Authorization": f"Bearer {api_key}"} if api_key else {}), **naming}
        )
        with urllib.request.urlopen(request, timeout=PROPS_TIMEOUT_SECONDS) as reply:
            props = json.load(reply)
    except Exception:  # noqa: BLE001 - a server without /props says nothing
        return None
    return from_props(props) if isinstance(props, dict) else None


_RECORDED: ServerProfile | None = None
#: When this process last read the server (`record`), on the monotonic clock.
_READ_AT = 0.0
#: Whether a read of the server was attempted in this process. Before it, "no facts" means
#: "not asked yet", which is not what a server that has none is.
_TRIED = False


def record() -> ServerProfile | None:
    """Read the build model's server profile and keep it for this process. Never raises."""
    global _RECORDED, _TRIED, _READ_AT, _DESTINATION
    import time

    _TRIED = True
    _READ_AT = time.monotonic()
    try:
        from app.models import _runtime_settings

        settings = _runtime_settings()
        _DESTINATION = (settings.openai_base_url or "", settings.model_name or "")
        if (settings.llm_provider or "") in {"anthropic", "gemini"}:
            _RECORDED = None
            return None
        _RECORDED = read(settings.openai_base_url or "", settings.openai_api_key or "")
    except Exception:  # noqa: BLE001
        logger.debug("Could not read the model server's profile", exc_info=True)
        _RECORDED = None
    if _RECORDED is not None:
        logger.info(
            "Model server: %s slot(s), %s tokens per slot%s",
            _RECORDED.slots or "?", _RECORDED.slot_context or "?",
            f", {_RECORDED.quantisation}" if _RECORDED.quantisation else "",
        )
    return _RECORDED


#: How often, at most, a running worker asks the server about itself again.
HEALTH_CHECK_SECONDS = 300
_LAST_CHECK = 0.0
_UNREACHABLE = False


def what_changed(before: ServerProfile, after: ServerProfile) -> list[str]:
    """The server facts that differ between two profiles, in words; [] when none do."""
    changes = []
    if before.slots != after.slots:
        changes.append(f"slots {before.slots or '?'} -> {after.slots or '?'}")
    if before.slot_context != after.slot_context:
        changes.append(f"tokens per slot {before.slot_context or '?'} -> {after.slot_context or '?'}")
    if before.quantisation != after.quantisation:
        changes.append(f"quantisation {before.quantisation or '?'} -> {after.quantisation or '?'}")
    # The model itself: a server restarted with another model at the same slots
    # and context was no change at all, and what was measured of the old one
    # (reply salvage, `app.models.reply_salvage`) went on being used for it.
    if before.model != after.model:
        changes.append(f"model {before.model or '?'} -> {after.model or '?'}")
    return changes


#: (address, model) the profile in `_RECORDED` was read for; None before the first read.
_DESTINATION: tuple[str, str] | None = None


def _the_run_moved(run_id: str) -> bool:
    """Whether the run now talks to a different (address, model) than the profile was read for. Never raises."""
    global _DESTINATION
    if not run_id or _RECORDED is None:
        return False
    try:
        from app.models.model_pin import destination

        found = destination("default", run_id)
    except Exception:  # noqa: BLE001
        return False
    if found is None:
        return False
    here = (found.base_url, found.model)
    moved = _DESTINATION is not None and here != _DESTINATION
    _DESTINATION = here
    return moved


def check_again(run_id: str = "", *, clock: Any = None, reader: Any = None) -> str:
    """Ask the server about itself again during a run, at most every `HEALTH_CHECK_SECONDS`; never raises.

    Read once per segment, the profile went stale whenever the owner restarted
    the server: measured on one day, the server went from one slot to two
    between runs, and a run would have kept budgeting for the old slot's
    context until a deploy re-read it. A change, or a server that stopped
    answering after it had answered, is logged and recorded in the run's
    transcript (`server_changed` / `server_unreachable`), and the new facts are
    used from the next call on (Initiative S). Returns what it noticed, or "".
    """
    global _RECORDED, _LAST_CHECK, _UNREACHABLE
    import time

    now = (clock or time.monotonic)()
    # A run moved to another model server (its model pin was toggled, or the settings changed under it) is not
    # waited for: the facts recorded are the old server's, so it asks the new one now.
    moved = _the_run_moved(run_id)
    if not _TRIED or _RECORDED is None or (now - _LAST_CHECK < HEALTH_CHECK_SECONDS and not moved):
        return ""
    _LAST_CHECK = now
    try:
        if reader is not None:
            fresh = reader()
        else:
            from app.models import _runtime_settings

            settings = _runtime_settings()
            fresh = read(settings.openai_base_url or "", settings.openai_api_key or "")
    except Exception:  # noqa: BLE001 - telemetry never stops a call
        return ""
    noticed, kind, details = "", "", {}
    if fresh is None:
        if not _UNREACHABLE:
            _UNREACHABLE = True
            noticed, kind = "The model server did not answer its /props check", "server_unreachable"
    else:
        if _UNREACHABLE:
            _UNREACHABLE = False
            noticed, kind = "The model server answers again", "server_reachable"
        changes = what_changed(_RECORDED, fresh)
        if changes:
            noticed = "The model server changed during the run: " + ", ".join(changes)
            kind, details = "server_changed", {"changes": changes}
            _RECORDED = fresh
    if noticed:
        logger.warning(noticed)
        if run_id:
            try:
                from app.observability.transcript import record as write

                write(run_id, "-", kind, text=noticed, **details)
            except Exception:  # noqa: BLE001
                pass
    return noticed


def current() -> ServerProfile | None:
    """The profile recorded for this process, or None. No network."""
    return _RECORDED


#: How old, at most, the profile the settings page names a model by may be.
PAGE_MAX_AGE_SECONDS = 30


def recent(max_age: float = PAGE_MAX_AGE_SECONDS, *, clock: Any = None) -> ServerProfile | None:
    """The profile, read again when this process's read is older than `max_age` or there was none. Never raises.

    For a process no run reads the server in - the API the settings page asks:
    it never read the server, so it named the model by its configured name
    while the diagnosis kept what it measured under the server's own, and the
    page showed nothing of it. A model swapped since is named afresh too.
    """
    import time

    if not _TRIED or (clock or time.monotonic)() - _READ_AT > max_age:
        return record()
    return _RECORDED


def asked() -> bool:
    """Whether the server's profile has been read in this process (it may have said nothing)."""
    return _TRIED


def forget() -> None:
    global _RECORDED, _TRIED, _LAST_CHECK, _UNREACHABLE, _READ_AT, _DESTINATION
    _DESTINATION = None
    _RECORDED = None
    _READ_AT = 0.0
    _TRIED = False
    _LAST_CHECK = 0.0
    _UNREACHABLE = False


__all__ = ["PAGE_MAX_AGE_SECONDS", "ServerProfile", "asked", "check_again", "current", "forget", "from_props", "read", "recent", "record", "what_changed"]
