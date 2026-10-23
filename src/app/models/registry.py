"""What the harness knows about a served model's family (Initiative BH).

Per family: the tool-call protocol a server must parse for it, the switch that
turns its thinking on and off, whether a per-request reasoning budget is known
to be honoured, and the sampling its makers recommend per mode - advisory only,
printed by `loop.sh ready` and never sent (ADR-0008: the owner sets sampling).

What is *measured* rather than known - how often a model's whole-file writes and
its find-and-replace edits come back well formed - is kept beside it under
`DATA_DIR/model-fitness/`, written by the fitness probe (`fitness.edit_probe`).
The preference between the two is read from that measurement; nothing here
changes what a stage is offered.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FamilyProfile:
    family: str
    #: The server-side tool-call parser this family needs (vLLM `--tool-call-parser`; llama.cpp
    #: `--jinja` with the family's own template).
    parser: str
    #: How thinking is switched per request ("" when the family has no switch).
    thinking_switch: str
    #: Whether a per-request reasoning budget is known to be honoured; None when unmeasured.
    budget_per_request: bool | None
    #: The makers' recommended sampling per mode, for the owner's server settings.
    sampling: str


GENERIC = FamilyProfile(
    family="generic", parser="the server's default (unverified for this model)", thinking_switch="",
    budget_per_request=None, sampling="as the model card recommends",
)

#: (a pattern on the served model's name, its profile), most specific first.
FAMILIES: tuple[tuple[re.Pattern[str], FamilyProfile], ...] = (
    # Any words between the version and "coder": `qwen3.8-flash-next-coder` was
    # read as plain qwen3 (JSON tool calls) though its template writes XML ones.
    (re.compile(r"qwen3[\w.\- ]*?coder", re.I), FamilyProfile(
        "qwen3-coder", "qwen3_coder (XML tool calls)", "", None,
        "temperature 0.7, top_p 0.8, top_k 20, repetition_penalty 1.05")),
    (re.compile(r"qwen3", re.I), FamilyProfile(
        "qwen3", "hermes (JSON tool calls in <tool_call> tags)",
        "chat_template_kwargs.enable_thinking / reasoning_effort=none", None,
        "thinking: temperature 0.6, top_p 0.95, top_k 20; no thinking: temperature 0.7, top_p 0.8, top_k 20")),
    (re.compile(r"devstral|mistral|codestral", re.I), FamilyProfile(
        "mistral", "mistral", "", None, "temperature 0.15")),
    (re.compile(r"glm[-_ ]?4", re.I), FamilyProfile(
        "glm", "glm45", "chat_template_kwargs.enable_thinking", None, "temperature 0.6, top_p 0.95")),
    (re.compile(r"gpt[-_ ]?oss", re.I), FamilyProfile(
        "gpt-oss", "harmony (openai)", "reasoning_effort low|medium|high", None, "temperature 1.0, top_p 1.0")),
    (re.compile(r"llama[-_ ]?3|llama[-_ ]?4", re.I), FamilyProfile(
        "llama", "llama3_json / pythonic", "", None, "temperature 0.6, top_p 0.9")),
    (re.compile(r"deepseek", re.I), FamilyProfile(
        "deepseek", "deepseek_v3", "chat_template_kwargs.thinking", None, "temperature 0.6, top_p 0.95")),
)

#: Below this share of well-formed find-and-replace edits, whole-file writes are preferred
#: for files of up to `WHOLE_FILE_LINES` lines (Aider: whole 100% vs diff 92-95% well formed).
WELL_FORMED_EDITS = 0.95
WHOLE_FILE_LINES = 300


#: Tools models call by names they learned elsewhere, as data (Initiative M.5): the
#: offered tool each one means, and how its argument names map. Measured across the
#: stored runs: `edit_file` with `path`, `context` and `replacement` was refused
#: 209 times in four runs, every time as "not a valid tool". A name here is only
#: taken when the tool it means is offered and every argument that tool requires
#: is given; otherwise the refusal stands.
TOOL_ALIASES: dict[str, tuple[str, dict[str, str]]] = {
    "edit_file": ("edit_artifact", {"path": "relative_path", "file_path": "relative_path",
                                    "context": "find", "old_string": "find", "old_str": "find",
                                    "replacement": "replace", "new_string": "replace", "new_str": "replace"}),
    "str_replace": ("edit_artifact", {"path": "relative_path", "file_path": "relative_path",
                                      "old_str": "find", "old_string": "find", "new_str": "replace", "new_string": "replace"}),
    "create_file": ("write_artifact", {"path": "relative_path", "file_path": "relative_path",
                                       "file_text": "content", "contents": "content"}),
}


def profile_for(model_name: str) -> FamilyProfile:
    """The family profile for a served model's name; the generic one when no family matches."""
    for pattern, profile in FAMILIES:
        if pattern.search(str(model_name or "")):
            return profile
    return GENERIC


def _slug(model_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(model_name or "unknown")).strip("_")[:120] or "unknown"


def fitness_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or "data") / "model-fitness"


def merge_into_fitness(model_name: str, measured: dict) -> Path:
    """Keep `measured` in the model's fitness file beside what else was measured of it; the path written.

    One file a model, more than one measurement in it: the edit rates and the
    reply salvage (`reply_salvage`). Each kept its own by rewriting the file,
    so measuring one would have forgotten the other.
    """
    path = fitness_dir() / f"{_slug(model_name)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        found = {}
    found = found if isinstance(found, dict) else {}
    path.write_text(json.dumps({**found, "model": model_name, **measured}, indent=1, sort_keys=True), encoding="utf-8")
    return path


def fold_into_served(served: str, configured: str) -> None:
    """What was kept under a model's configured name, moved into its file under the server's name. Never raises.

    One model, two names: the server's file name, which runs and the
    diagnosis keep their measurements under, and the configured name, which
    the settings page used when its process had not read the server. The
    owner's capability settings went to one file and the runs read the other.
    What the served file already holds wins; the configured file is removed.
    """
    if not served or not configured or _slug(served) == _slug(configured):
        return
    old = fitness_dir() / f"{_slug(configured)}.json"
    if not old.is_file():
        return
    try:
        stray = json.loads(old.read_text(encoding="utf-8"))
        path = fitness_dir() / f"{_slug(served)}.json"
        try:
            kept = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            kept = {}
        merged = {**stray, **kept}
        for key, value in stray.items():
            if isinstance(value, dict) and isinstance(kept.get(key), dict):
                merged[key] = {**value, **kept[key]}
        merged["model"] = served
        path.write_text(json.dumps(merged, indent=1, sort_keys=True), encoding="utf-8")
        old.unlink()
        logger.info("Kept what was saved under %s with the served model %s", configured, served)
    except Exception:  # noqa: BLE001
        logger.debug("Could not fold %s into %s", configured, served, exc_info=True)


def record_edit_rates(model_name: str, rates: dict[str, float]) -> Path:
    """Keep a model's measured well-formed rates; the path written."""
    return merge_into_fitness(model_name, rates)


def measured_edit_rates(model_name: str) -> dict[str, float]:
    """The model's measured well-formed rates (`whole`, `edit`), or {} when it was never measured."""
    try:
        found = json.loads((fitness_dir() / f"{_slug(model_name)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: float(v) for k, v in found.items() if k in ("whole", "edit") and isinstance(v, (int, float))}


def edit_preference(model_name: str) -> str:
    """"whole" when the model's edits are measured under the bar, "edit" when at or over it, "" unmeasured."""
    rates = measured_edit_rates(model_name)
    if "edit" not in rates:
        return ""
    return "whole" if rates["edit"] < WELL_FORMED_EDITS else "edit"


def describe(model_name: str) -> str:
    """One line for `loop.sh ready`."""
    profile = profile_for(model_name)
    rates = measured_edit_rates(model_name)
    budget = {True: "honoured", False: "ignored (measured)", None: "unmeasured"}[profile.budget_per_request]
    edits = (f"edits well formed {rates.get('edit', 0):.0%}, whole files {rates.get('whole', 0):.0%} -> prefer "
             f"{'whole files' if edit_preference(model_name) == 'whole' else 'edits'}"
             if rates else "edit preference unmeasured (`loop.sh fitness --edits` between runs)")
    try:
        from app.models import reply_salvage

        salvage = reply_salvage.describe(reply_salvage.recorded(model_name))
    except Exception:  # noqa: BLE001
        salvage = "unmeasured"
    return (f"family {profile.family}; server parser {profile.parser}; thinking switch "
            f"{profile.thinking_switch or 'none known'}; per-request reasoning budget {budget}; {edits}; "
            f"reply salvage {salvage}; recommended sampling (advice, never sent): {profile.sampling}")


__all__ = ["TOOL_ALIASES", "FAMILIES", "FamilyProfile", "GENERIC", "WELL_FORMED_EDITS", "describe", "edit_preference",
           "fold_into_served", "measured_edit_rates", "merge_into_fitness", "profile_for", "record_edit_rates"]
