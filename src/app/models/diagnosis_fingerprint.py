"""What a diagnosis was measured on, kept with every record, so a record is not served to another server (DX.5).

Read from the kept diagnoses: one model family has four records under four names, three of them diagnosed, with
structured answers forced, forced only with thinking off, and required, and one, none and two guides chosen. Some of
that was the server (LM Studio against llama.cpp), which is right; nothing in the record said which server, chat
template or probe set it was measured on, and a record was used for as long as a model of that served name answered
(`diagnose_if_new` re-diagnosed only where there was none).

So each record carries a fingerprint: the served model file, its quantisation, a hash of the chat template, the
server's build, the endpoint layout (endpoints, slots, per-slot context), the provider of a hosted model, and the
versions of the probe set and of the decision rules. All but the last two are read without a model call
(`server_profile`).

A record is stale for the model's behaviour when the model file, quantisation, template or build it was measured on
differs from the server's now; both must be known to differ. Slots, endpoints and per-slot context are the speed and
concurrency profile's (`speed_profile`): a balancer whose second instance is down for a minute reads half the slots,
and that is no reason to ask the model its forty questions again. A record kept before fingerprints existed has none
and is not stale: nothing says it was measured elsewhere.
"""
from __future__ import annotations

from typing import Any

#: The version of the questions the diagnosis asks (its checks, probes and their wording). Changed whenever a check
#: or probe changes, so a profile made with the old set is shown as such.
PROBE_SET_VERSION = "2026-11-27.1"
#: The version of the rules that turn answers into settings (passes, tiers, guides kept, budgets, caps).
RULES_VERSION = "dx-2026-11-27.1"

#: What the model's behaviour depends on: a change in any makes a record of its tools, reasoning and steering stale.
MODEL_KEYS = ("model", "quantisation", "template", "build")
#: What the speed and concurrency profile depends on, beyond the model's own.
SERVER_KEYS = (*MODEL_KEYS, "endpoints", "slots", "slot_context")


def of(profile: Any = None, base_url: str = "", hosted: bool = False) -> dict[str, Any]:
    """The fingerprint of the server `profile` describes (`server_profile.ServerProfile`, or None), at `base_url`."""
    out: dict[str, Any] = {"probes": PROBE_SET_VERSION, "rules": RULES_VERSION}
    if profile is not None:
        out.update({
            "model": str(getattr(profile, "model", "") or ""),
            "quantisation": str(getattr(profile, "quantisation", "") or ""),
            "template": str(getattr(profile, "template_hash", "") or ""),
            "build": str(getattr(profile, "build", "") or ""),
            "endpoints": getattr(profile, "endpoints", None),
            "slots": getattr(profile, "slots", None),
            "slot_context": getattr(profile, "slot_context", None),
        })
    if hosted and base_url:
        from urllib.parse import urlparse

        out["provider"] = (urlparse(base_url).hostname or "").lower()
    return out


def current() -> dict[str, Any]:
    """The fingerprint of the server this process last read (`server_profile.current`). No network. Never raises."""
    try:
        from app.models import _runtime_settings, server_profile
        from app.models.endpoints import is_self_hosted

        base = str(_runtime_settings().openai_base_url or "")
        return of(server_profile.current(), base, hosted=bool(base) and not is_self_hosted(base))
    except Exception:  # noqa: BLE001 - a fingerprint of the versions alone
        return of()


def stale(kept: Any, now: Any, keys: tuple[str, ...] = MODEL_KEYS) -> list[str]:
    """What differs between the fingerprint a record was `kept` with and the server's `now`, in words; [] when
    nothing known on both sides does. A record with no fingerprint is not stale."""
    if not isinstance(kept, dict) or not isinstance(now, dict):
        return []
    changes = []
    for key in keys:
        before, after = kept.get(key), now.get(key)
        if before not in (None, "") and after not in (None, "") and before != after:
            changes.append(f"{key} {before} -> {after}")
    return changes


def older_probes(kept: Any) -> bool:
    """Whether a record was made with an older probe set or older rules than this harness's."""
    if not isinstance(kept, dict):
        return True
    return kept.get("probes") != PROBE_SET_VERSION or kept.get("rules") != RULES_VERSION


__all__ = ["MODEL_KEYS", "PROBE_SET_VERSION", "RULES_VERSION", "SERVER_KEYS", "current", "of", "older_probes", "stale"]
