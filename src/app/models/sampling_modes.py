"""Sampling for each of three modes of a call, derived for any model, kept per model, sent only once the owner turns it on.

A reasoning model is called two ways here: with its thinking on (the architect, the reviews, the lead, the agent
fixers) and with it off (fast delivery's builders and rewrites, an answer salvaged after a cut-off). Model cards give
different sampling for each - Qwen3.6's: thinking general temperature 1.0 / top_p 0.95 / presence 1.5, thinking for
precise coding temperature 0.6 / presence 0, no thinking temperature 0.7 / top_p 0.8 / presence 1.5 - and one setting
sent to every call fits neither. Three modes, each with its own values:

- `thinking_precise`: a call that reasons and writes code, tests or a structured answer - the harness's usual work;
- `thinking_general`: a call that reasons about prose; chosen for thinking calls only when the owner says so;
- `no_thinking`: a call sent with the model's thinking switched off.

Each mode's values are derived in order: the model card's own text for that mode, then its family's known values
(`app.models.registry`), then the card's one unlabelled set. A presence penalty above 0 is taken down to 0 in the two
modes that write code and answers to a schema, and said so: it penalises every token already used, and code and JSON
reuse their names and keys by design. The owner's values for a mode win; sampling is the owner's (ADR-0008), so
nothing is sent until "send sampling by mode" is turned on.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Where the derived values, the owner's values and the owner's choices are kept in the model's record.
FOUND_KEY = "sampling_modes_found"
OWNER_KEY = "sampling_modes_owner"
CHOICES_KEY = "sampling_modes_choices"

#: The settings a mode may carry, in the order a page shows them.
SETTINGS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty")


@dataclass(frozen=True)
class Mode:
    id: str
    label: str
    used_for: str
    what_it_does: str


MODES: tuple[Mode, ...] = (
    Mode("thinking_precise", "Thinking - precise",
         "Calls that reason first and then write code, tests or an answer in a fixed form: the architect, the "
         "reviews, the technical lead and the agent fixers. Used for every thinking call unless you choose the "
         "general mode below.",
         "Low randomness, so code, names and JSON stay consistent from one reply to the next. Repetition is not "
         "penalised, because code and structured answers repeat their own names and keys by design."),
    Mode("thinking_general", "Thinking - general",
         "Calls that reason first and answer in prose. Used for thinking calls only if you choose it below.",
         "More varied wording than the precise mode; usually a higher temperature and a presence penalty that "
         "discourages repeating itself. Better for open-ended writing, worse for code and strict formats."),
    Mode("no_thinking", "No thinking",
         "Calls sent with the model's thinking switched off: fast delivery's builders and rewrite fixers, an answer "
         "asked for after a reply was cut off, and any review the harness runs without reasoning.",
         "Answers straight away with no reasoning first. Usually a slightly tighter top_p than thinking mode; the "
         "presence penalty is kept at 0 here too, because these calls write code and structured answers."),
)
BY_ID = {mode.id: mode for mode in MODES}
#: The two modes whose calls write code and answers to a schema.
_CODE_MODES = frozenset({"thinking_precise", "no_thinking"})

_NUMBER = r"(-?\d+(?:\.\d+)?)"
_A_SETTING = re.compile(r"\b(temperature|top[_-]?p|top[_-]?k|min[_-]?p|presence[_-]?penalty|repetition[_-]?penalty)"
                        r"\s*(?:=|:|\s)\s*`?" + _NUMBER, re.I)
#: Words that say which mode a passage of a model card is about, most specific first.
_SAYS_NO_THINKING = re.compile(r"non[- ]?thinking|no[- ]thinking|instruct(?:ion)?(?:[- ]following)? mode|"
                               r"thinking (?:is )?(?:off|disabled)|enable_thinking\s*=\s*false", re.I)
_SAYS_PRECISE = re.compile(r"\b(?:coding|code|precise|webdev|programming|agentic|tool[- ]?(?:use|call))", re.I)
_SAYS_THINKING = re.compile(r"\bthinking\b|reasoning mode", re.I)


def _setting_name(raw: str) -> str:
    return raw.lower().replace("-", "_").replace("topp", "top_p").replace("topk", "top_k").replace("minp", "min_p")


def _settings_in(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for raw, number in _A_SETTING.findall(text):
        name = _setting_name(raw)
        if name in SETTINGS and name not in found:
            value = float(number)
            found[name] = int(value) if name == "top_k" else value
    return found


#: A passage about a benchmark's own run, not a recommendation: read only when the card has no other.
_A_BENCHMARK = re.compile(r"bench|\bbfcl\b|\baime\b|\bswe\b|evaluat|\btau\b|\u03c4|leaderboard|max_turns", re.I)
#: Words that make a passage the card's recommendation, whatever heading it sits under.
_RECOMMENDED = re.compile(r"default|recommend|most tasks|best practice|generation parameters|sampling parameters|"
                          r"suggested|we advise", re.I)


def _passages(lines: list[str]) -> list[tuple[int, int, dict[str, float]]]:
    """(first line, last line, settings) of each passage: a line with two settings or more, or a run of lines with one
    setting each (a list written one setting a line, as LFM2.5's and GLM-4.7's cards are)."""
    out: list[tuple[int, int, dict[str, float]]] = []
    at = 0
    while at < len(lines):
        settings = _settings_in(lines[at])
        if len(settings) >= 2:
            out.append((at, at, settings))
            at += 1
            continue
        if len(settings) == 1:
            start, merged = at, dict(settings)
            while at + 1 < len(lines) and len(one := _settings_in(lines[at + 1])) == 1 and not set(one) & set(merged):
                at += 1
                merged.update(one)
            if len(merged) >= 2 or start != at or "temperature" in merged:
                out.append((start, at, merged))
        at += 1
    return out


def from_the_card(readme: str) -> dict[str, dict[str, float]]:
    """{mode: settings} read from a model card's text, each passage given the mode the words before it name.

    A passage with settings but no mode word is "any". A passage about a benchmark's own run is read only when the
    card has nothing else: LFM2.5's card recommends temperature 0.1 and lists AutomationBench's 0.6 lower down.
    """
    lines = (readme or "").splitlines()
    recommended: dict[str, dict[str, float]] = {}
    benchmarks: dict[str, dict[str, float]] = {}
    for start, end, settings in _passages(lines):
        context = " ".join(lines[max(0, start - 3):end + 1])
        near = " ".join(lines[max(0, start - 3):start + 1])
        if _SAYS_NO_THINKING.search(near):
            mode = "no_thinking"
        elif _SAYS_THINKING.search(near) and _SAYS_PRECISE.search(near):
            mode = "thinking_precise"
        elif _SAYS_THINKING.search(near):
            mode = "thinking_general"
        else:
            mode = "any"
        table = benchmarks if _A_BENCHMARK.search(context) and not _RECOMMENDED.search(context) else recommended
        table.setdefault(mode, settings)
    return recommended or benchmarks


def _from_the_family(model: str) -> dict[str, dict[str, float]]:
    from app.models.registry import profile_for

    profile = profile_for(model)
    text = str(getattr(profile, "sampling", "") or "")
    parts = dict(re.findall(r"(no thinking|thinking)\s*:\s*([^;]+)", text, re.I))
    if parts:
        thinking = _settings_in(parts.get("thinking", "") or parts.get("Thinking", ""))
        no_thinking = _settings_in(parts.get("no thinking", "") or parts.get("No thinking", ""))
        return {k: v for k, v in (("thinking_precise", thinking), ("thinking_general", thinking),
                                  ("no_thinking", no_thinking)) if v}
    settings = _settings_in(text)
    return {"any": settings} if settings else {}


def derive(model: str, readme: str = "") -> dict[str, dict[str, Any]]:
    """{mode: {"values", "source", "note"}} for every mode, from the card, then the family, then the card's one set."""
    card = from_the_card(readme)
    family = _from_the_family(model)
    out: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        for source, table, key in (("model card", card, mode.id), ("model family", family, mode.id),
                                   ("model card", card, "any"), ("model family", family, "any")):
            if table.get(key):
                values = dict(table[key])
                note = (f"the card's settings for this mode" if source == "model card" and key == mode.id else
                        f"the card's one set, for every mode" if source == "model card" else
                        f"what the harness knows of this model's family")
                if mode.id == "thinking_general" and key != mode.id and "thinking_precise" in card and source == "model card":
                    note = "the card names no general set; its thinking set"
                if mode.id in _CODE_MODES and float(values.get("presence_penalty", 0) or 0) > 0:
                    values["presence_penalty"] = 0.0
                    note += "; presence penalty taken to 0 by the harness: it penalises reused tokens, and code and " \
                            "JSON reuse their names and keys"
                out[mode.id] = {"values": values, "source": source, "note": note}
                break
        else:
            out[mode.id] = {"values": {}, "source": "unknown", "note": "nothing found: set it here, or leave the "
                                                                     "server's own defaults"}
    return out


# --- what is kept for a model ------------------------------------------------------------------------------------------

#: A packaging suffix that names how a model is stored, not which model it is.
_PACKAGING = re.compile(r"[-_.](?:gguf|ggml|mlx|awq|gptq|exl2|fp8|fp16|bf16|f16|i?q\d[\w]*)$", re.I)


def canonical(model: str) -> str:
    """One name for one model however a server or a run's pin spells it: no publisher, no packaging, lower case.

    Measured: the settings page named the served model `Qwen3.6-35B-A3B-MTP-GGUF`, a run pinned to that server
    `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` and another server `qwen3.6-35b-a3b-mtp` - three records, so sampling turned
    on in the page reached no run on either port.
    """
    name = str(model or "").strip().split("/")[-1]
    while (shorter := _PACKAGING.sub("", name)) != name:
        name = shorter
    return name.lower()


def _record(model: str) -> dict:
    from app.models import capabilities

    return capabilities._record(canonical(model))  # noqa: SLF001 - one record a model


def found(model: str) -> dict[str, dict[str, Any]]:
    return dict(_record(model).get(FOUND_KEY) or {})


def owner(model: str) -> dict[str, dict[str, float]]:
    return dict(_record(model).get(OWNER_KEY) or {})


def choices(model: str) -> dict[str, Any]:
    """The owner's choices: whether to send sampling by mode, and which mode a thinking call uses."""
    kept = dict(_record(model).get(CHOICES_KEY) or {})
    return {"send": bool(kept.get("send", False)),
            "thinking_calls": kept.get("thinking_calls") if kept.get("thinking_calls") in BY_ID else "thinking_precise"}


def keep_found(model: str, derived: dict[str, dict[str, Any]]) -> None:
    from datetime import datetime, timezone

    from app.models.registry import merge_into_fitness

    merge_into_fitness(canonical(model), {FOUND_KEY: {**derived, "_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}})


def set_owner(model: str, mode: str, values: dict[str, Any] | None) -> None:
    """The owner's values for one mode; None gives the mode back to what was derived."""
    from app.models.registry import merge_into_fitness

    if mode not in BY_ID:
        raise KeyError(mode)
    kept = owner(model)
    if values is None:
        kept.pop(mode, None)
    else:
        clean: dict[str, float] = {}
        for name, number in values.items():
            if name not in SETTINGS:
                raise KeyError(name)
            if number is None or number == "":
                continue
            number = float(number)
            clean[name] = int(number) if name == "top_k" else number
        kept[mode] = clean
    merge_into_fitness(canonical(model), {OWNER_KEY: kept})


def set_choices(model: str, send: bool | None = None, thinking_calls: str | None = None) -> None:
    from app.models.registry import merge_into_fitness

    kept = choices(model)
    if send is not None:
        kept["send"] = bool(send)
    if thinking_calls is not None:
        if thinking_calls not in ("thinking_precise", "thinking_general"):
            raise ValueError(f"a thinking call uses thinking_precise or thinking_general, not {thinking_calls}")
        kept["thinking_calls"] = thinking_calls
    merge_into_fitness(canonical(model), {CHOICES_KEY: kept})


def values_for(model: str, mode: str) -> dict[str, float]:
    """The values a call in `mode` is sent: the owner's for the mode, else what was derived."""
    if mode in owner(model):
        return dict(owner(model)[mode])
    return dict((found(model).get(mode) or {}).get("values") or {})


def view(model: str) -> dict[str, Any]:
    """What the settings page shows: each mode, what it is for, its values and where they came from."""
    derived, owned = found(model), owner(model)
    rows = []
    for mode in MODES:
        mine = owned.get(mode.id)
        seen = derived.get(mode.id) or {}
        rows.append({
            "id": mode.id, "label": mode.label, "used_for": mode.used_for, "what_it_does": mode.what_it_does,
            "values": dict(mine if mine is not None else seen.get("values") or {}),
            "source": "owner" if mine is not None else seen.get("source", "unknown"),
            "note": "set on this page" if mine is not None else seen.get("note", "not yet determined"),
            "derived": dict(seen.get("values") or {}), "owner_set": mine is not None,
        })
    return {"model": model, "settings": list(SETTINGS), "modes": rows, "choices": choices(model),
            "determined_at": derived.get("_at", "")}


# --- per call ----------------------------------------------------------------------------------------------------------

def thinking_is_off(payload: dict) -> bool:
    """Whether a request has the model's thinking switched off, by either switch the harness sends."""
    extra = payload.get("extra_body") or {}
    template = extra.get("chat_template_kwargs") or {}
    effort = str(payload.get("reasoning_effort") or extra.get("reasoning_effort") or "").lower()
    return template.get("enable_thinking") is False or effort in ("none", "minimal")


def mode_of(payload: dict, model: str) -> str:
    return "no_thinking" if thinking_is_off(payload) else choices(model)["thinking_calls"]


_OPENAI = frozenset({"temperature", "top_p", "presence_penalty"})
_SERVER_NAMES = {"top_k": "top_k", "min_p": "min_p", "repetition_penalty": "repeat_penalty"}


#: How long a model's choices and values are reused: this runs in every call.
CACHE_SECONDS = 15.0
_CACHE: dict[str, tuple[float, dict[str, Any], dict[str, dict[str, float]]]] = {}


def forget() -> None:
    """Drop the cached values; after the owner changes one, and for tests."""
    _CACHE.clear()


def _cached(model: str) -> tuple[dict[str, Any], dict[str, dict[str, float]]]:
    import time

    now = time.perf_counter()
    model = canonical(model)
    held = _CACHE.get(model)
    if held and held[0] > now:
        return held[1], held[2]
    chosen = choices(model)
    values = {mode.id: values_for(model, mode.id) for mode in MODES} if chosen["send"] else {}
    _CACHE[model] = (now + CACHE_SECONDS, chosen, values)
    return chosen, values


def with_the_mode_s_sampling(payload: dict, model: str) -> bool:
    """Add the call's mode's sampling to `payload` when the owner turned it on; whether anything was added.

    A value the request already carries wins. Never raises.
    """
    try:
        if not model:
            return False
        chosen, table = _cached(model)
        if not chosen["send"]:
            return False
        values = table.get("no_thinking" if thinking_is_off(payload) else chosen["thinking_calls"]) or {}
        if not values:
            return False
        body = dict(payload.get("extra_body") or {})
        for name, number in values.items():
            if name in _OPENAI:
                payload.setdefault(name, number)
            elif name in _SERVER_NAMES and _SERVER_NAMES[name] not in payload:
                body.setdefault(_SERVER_NAMES[name], number)
        if body:
            payload["extra_body"] = body
        return True
    except Exception:  # noqa: BLE001 - the request as it was
        logger.debug("Could not add the mode's sampling", exc_info=True)
        return False


def determine(model: str) -> dict[str, dict[str, Any]]:
    """Derive every mode for `model` from its model card and family and keep it. Never raises."""
    readme = ""
    try:
        from app.models import capabilities

        repo = capabilities._the_repo(model)  # noqa: SLF001
        # A quantised repack's card often leaves the sampling out: its `base_model`'s card is read next.
        for _ in range(2):
            if not repo:
                break
            text = capabilities._get(f"https://huggingface.co/{repo}/raw/main/README.md")  # noqa: SLF001
            readme = text if isinstance(text, str) else ""
            if from_the_card(readme):
                break
            card = (capabilities._get(f"https://huggingface.co/api/models/{repo}") or {}).get("cardData") or {}  # noqa: SLF001
            base = card.get("base_model")
            repo = (base[0] if isinstance(base, list) and base else base) if base else ""
    except Exception:  # noqa: BLE001 - no card: the family's values
        logger.debug("Could not read the model card", exc_info=True)
    derived = derive(model, readme)
    keep_found(model, derived)
    return derived


__all__ = ["canonical", "CACHE_SECONDS", "forget", "BY_ID", "MODES", "SETTINGS", "choices", "derive", "determine", "found", "from_the_card", "mode_of", "owner",
           "set_choices", "set_owner", "thinking_is_off", "values_for", "view", "with_the_mode_s_sampling"]
