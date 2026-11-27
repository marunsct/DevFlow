"""The settings a model's diagnosis found, kept with their evidence, applied behind one switch, each overridable (DX.6, DX.7).

The 2026-11-27 diagnosis design (section 4.2): one profile per model, one field per harness setting, each with its
value, where it came from (measured, the owner), its evidence, and whether it is applied. The owner decided
(2026-11-27): what the diagnosis finds is applied behind `PROFILE_FROM_DIAGNOSIS`, every field can be set on the
settings page, and a value the owner set always wins.

Kept in the model's fitness file under `RECORD_KEY`: `fields` (what was measured, replaced by each diagnosis), the
owner's `overrides` (kept across diagnoses), and the `fingerprint` it was measured on (`diagnosis_fingerprint`).

Read at a run segment's start (`apply`, from `diagnostics.apply`) into this process, so a request never reads a
file; an override set on the settings page reaches runs from their next segment.

Which fields are applied with the switch off: only the timeout floor (`timeout_floor`), which only ever lengthens how
long a call is waited for (design 6, DX.6: "always on"). Every other measured field waits for the switch; an owner's
override applies either way, as the owner's settings always do.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

NAME = "PROFILE_FROM_DIAGNOSIS"
RECORD_KEY = "profile"


class _FromDiagnosis:
    """`PROFILE_FROM_DIAGNOSIS` as the switch registry reads one: off in code, on in compose (owner's rule:
    switches on unless a change is drastic; these settings are each measured and each overridable)."""

    ON_BY_DEFAULT = False
    explanation = ("The settings the model's diagnosis measured are used: the parallel cap and the balancer session "
                   "scope from the concurrency probe, and the reasoning effort, reasoning budget and reply cap for a "
                   "working step, a review and a design request from the reasoning dose-response on replayed stage "
                   "requests. Off, those settings stay at their defaults; the timeout floor and the owner's own "
                   "values on the settings page apply either way.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on(NAME, _FromDiagnosis.ON_BY_DEFAULT)


profile_switch = _FromDiagnosis()


@dataclass(frozen=True)
class Field:
    id: str
    title: str
    #: "int", "float" or a tuple of the values it takes.
    kind: Any
    #: Applied with the switch off too (it only lengthens patience).
    always: bool = False


#: The stage kinds the reasoning settings are kept for (`dose_response.stage_kind`).
STAGE_KINDS = ("step", "review", "design")
_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

FIELDS: tuple[Field, ...] = (
    Field("timeout_floor", "Slowest generation planned for (tokens a second)", "float", always=True),
    Field("parallel_cap", "Requests sent at once", "int"),
    Field("session_scope", "Balancer session scope", ("conversation", "request")),
    *(Field(f"effort.{kind}", f"Reasoning effort, {kind}", _EFFORTS) for kind in STAGE_KINDS),
    *(Field(f"budget.{kind}", f"Reasoning budget, {kind} (tokens)", "int") for kind in STAGE_KINDS),
    *(Field(f"cap.{kind}", f"Reply cap, {kind} (tokens)", "int") for kind in STAGE_KINDS),
)
BY_ID = {field.id: field for field in FIELDS}


def _path(model: str):
    from app.models.registry import _slug, fitness_dir

    return fitness_dir() / f"{_slug(model)}.json"


def recorded(model: str) -> dict:
    """The model's kept profile ({} when none): `fields`, `overrides`, `fingerprint`, `measured_at`, raw numbers."""
    try:
        found = json.loads(_path(model).read_text(encoding="utf-8")).get(RECORD_KEY)
    except (OSError, ValueError, AttributeError):
        return {}
    return found if isinstance(found, dict) else {}


def keep(model: str, fields: dict[str, dict], raw: dict[str, Any] | None = None) -> dict:
    """Merge newly measured `fields` (id -> {value, evidence, confidence}) into the model's profile; the owner's
    overrides and fields not measured this time stay. Returns the profile kept."""
    from datetime import datetime, timezone

    from app.models import diagnosis_fingerprint
    from app.models.registry import merge_into_fitness

    profile = recorded(model)
    kept = dict(profile.get("fields") or {})
    for key, entry in fields.items():
        if key in BY_ID and isinstance(entry, dict):
            kept[key] = {**entry, "source": "measured"}
    profile = {**profile, "fields": kept, "overrides": dict(profile.get("overrides") or {}),
               "fingerprint": diagnosis_fingerprint.current(),
               "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    for key, value in (raw or {}).items():
        profile[key] = value
    merge_into_fitness(model, {RECORD_KEY: profile})
    return profile


def _valid(field: Field, value: Any) -> Any:
    if field.kind == "int":
        number = int(value)
        if number < 1:
            raise ValueError(f"{field.id} must be at least 1")
        return number
    if field.kind == "float":
        number = float(value)
        if number <= 0:
            raise ValueError(f"{field.id} must be above 0")
        return number
    text = str(value).strip().lower()
    if text not in field.kind:
        raise ValueError(f"{field.id} takes one of {', '.join(field.kind)}")
    return text


def set_override(model: str, field_id: str, value: Any) -> dict:
    """The owner's value for one field of this model (None: follow the diagnosis). Raises KeyError or ValueError."""
    from app.models.registry import merge_into_fitness

    field = BY_ID[field_id]
    profile = recorded(model)
    overrides = dict(profile.get("overrides") or {})
    if value is None or value == "":
        overrides.pop(field_id, None)
    else:
        overrides[field_id] = _valid(field, value)
    profile = {**profile, "overrides": overrides}
    merge_into_fitness(model, {RECORD_KEY: profile})
    return profile


def resolved(profile: dict) -> dict[str, Any]:
    """Each field's applied value from a kept `profile`: the owner's override always; a measured value where the
    switch is on or the field is always applied; nothing otherwise."""
    out: dict[str, Any] = {}
    fields = profile.get("fields") or {}
    overrides = profile.get("overrides") or {}
    on = profile_switch.enabled()
    for field in FIELDS:
        if field.id in overrides:
            out[field.id] = overrides[field.id]
        elif (on or field.always) and (fields.get(field.id) or {}).get("value") is not None:
            out[field.id] = fields[field.id]["value"]
    return out


#: What `apply` read, per (address, model) a client is built for, and the server the build model is on.
_APPLIED: dict[tuple[str, str], dict[str, Any]] = {}
_OWNER: dict[tuple[str, str], dict[str, Any]] = {}
_DEFAULT: list[tuple[str, str] | None] = [None]
_LOCK = threading.Lock()


def apply(server: tuple[str, str], served: str, *, default: bool = True) -> dict[str, Any]:
    """Read the served model's profile for `server` into this process (the values each field applies). Never
    raises. A profile measured on another model file, template or build than the server's now applies nothing but
    the owner's overrides (DX.5)."""
    try:
        from app.models import diagnosis_fingerprint

        profile = recorded(served)
        if diagnosis_fingerprint.stale(profile.get("fingerprint"), diagnosis_fingerprint.current()):
            profile = {"overrides": profile.get("overrides") or {}}
        values = resolved(profile)
        with _LOCK:
            _APPLIED[server] = values
            _OWNER[server] = dict(profile.get("overrides") or {})
            if default:
                _DEFAULT[0] = server
        return values
    except Exception:  # noqa: BLE001
        logger.debug("Could not apply the model's profile", exc_info=True)
        return {}


def applied(field_id: str, server: tuple[str, str] | None = None) -> Any:
    """The value `field_id` applies for `server` (the build model's when None); None for the default."""
    with _LOCK:
        key = server if server is not None else _DEFAULT[0]
        return (_APPLIED.get(key) or {}).get(field_id) if key is not None else None


def owner(field_id: str, server: tuple[str, str] | None = None) -> Any:
    """The value the owner set for `field_id` on the settings page, for `server` (the build model's); None."""
    with _LOCK:
        key = server if server is not None else _DEFAULT[0]
        return (_OWNER.get(key) or {}).get(field_id) if key is not None else None


def forget() -> None:
    with _LOCK:
        _APPLIED.clear()
        _OWNER.clear()
        _DEFAULT[0] = None


#: The transcript record of a measured field applied to a stage's calls, and its words (the switch's firing signal).
RECORD_KIND = "diagnosis_profile"
SAID = "set from the model's diagnosis:"
_NOTED: set[tuple[str, str, str]] = set()


def from_the_diagnosis(field_id: str, server: tuple[str, str] | None = None) -> Any:
    """The value `field_id` applies for `server`, and None where it is the owner's (the switch did not act) or none."""
    value = applied(field_id, server)
    return None if value is None or owner(field_id, server) is not None else value


def note(what: str) -> None:
    """One transcript record a stage visit and field: what the diagnosis set, in the words the switch register looks
    for. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config, record

        run, stage = str(_run_id_from_config() or ""), str(_stage_from_config("") or "")
        if not run:
            return
        with _LOCK:
            if (run, stage, what) in _NOTED:
                return
            _NOTED.add((run, stage, what))
        record(run, stage, RECORD_KIND, switch=NAME, message=f"{SAID} {what}")
    except Exception:  # noqa: BLE001
        logger.debug("Could not record the profile's setting", exc_info=True)


def view(model: str) -> list[dict[str, Any]]:
    """One row a field for the settings page: measured value and evidence, the owner's value, what applies."""
    profile = recorded(model)
    fields = profile.get("fields") or {}
    overrides = profile.get("overrides") or {}
    applies = resolved(profile)
    rows = []
    for field in FIELDS:
        measured = fields.get(field.id) or {}
        rows.append({
            "id": field.id, "title": field.title,
            "choices": list(field.kind) if isinstance(field.kind, tuple) else None,
            "number": field.kind if field.kind in ("int", "float") else None,
            "measured": measured.get("value"), "evidence": measured.get("evidence", ""),
            "confidence": measured.get("confidence", "not measured" if not measured else ""),
            "override": overrides.get(field.id), "applied": applies.get(field.id),
            "behind_switch": not field.always,
        })
    return rows


__all__ = ["BY_ID", "FIELDS", "Field", "NAME", "RECORD_KEY", "STAGE_KINDS", "apply", "applied", "forget", "keep",
           "owner", "profile_switch", "recorded", "resolved", "set_override", "view"]
