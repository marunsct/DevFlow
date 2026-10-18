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
    found = _QUANT.findall(path.rsplit("/", 1)[-1])
    return ServerProfile(
        slots=slots if isinstance(slots, int) and slots > 0 else None,
        slot_context=context if isinstance(context, int) and context > 0 else None,
        quantisation=found[-1].upper() if found else "",
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


def record() -> ServerProfile | None:
    """Read the build model's server profile and keep it for this process. Never raises."""
    global _RECORDED
    try:
        from app.models import _runtime_settings

        settings = _runtime_settings()
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


def current() -> ServerProfile | None:
    """The profile recorded for this process, or None. No network."""
    return _RECORDED


def forget() -> None:
    global _RECORDED
    _RECORDED = None


__all__ = ["ServerProfile", "current", "forget", "from_props", "read", "record"]
