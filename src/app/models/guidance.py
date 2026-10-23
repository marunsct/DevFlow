"""General guidance for any model, each item its own switch, chosen per model by measurement (owner, 2026-10-23).

A larger model does as a stage asks; a smaller one does part of it, and which
part differs from model to model - one answers plans as near misses of their
schema, another chains shell commands, another reads `/workspace/...` for a
path it was given. So guidance is not written per model. It is one catalogue
(`GUIDES`), each item a line of instruction for one kind of failure, its own
switch, and the checks of the deep diagnosis (`deep_diagnosis.CHECKS`) that
show whether a model needs it. The lines live in the plugin-instruction table
as `guide:<id>` rows, so they can be edited once for every model.

What is kept per model is its steering profile: how well it did (`tier`),
which items its diagnosis chose, any item the owner turned on or off for it on
the settings page, and the settings that go with it. How much steering a model
gets follows its tier, as the measurement says, not its size on paper:

- strong - no item unless measured to help it;
- standard - the items for the areas it fell short in that were measured to help;
- weak - every item for an area it fell short in, helped or not, and a short
  reminder of them at the end of every request, where a weaker model still
  reads it (Aider's reminder for models that do not keep to the system prompt).

An item is active when its switch is on and the model's override - or, with
none, its diagnosis - says so.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: The table key prefix of a guide's line.
PREFIX = "guide:"
#: Where a model's steering profile is kept in its fitness file.
RECORD_KEY = "steering"
#: Tiers, by the share of the deep diagnosis's tries a model passed with no guidance.
STRONG_FROM = 0.9
STANDARD_FROM = 0.65


@dataclass(frozen=True)
class Guide:
    id: str
    title: str
    area: str
    line: str
    #: The deep diagnosis's checks that show whether a model needs it.
    checks: tuple[str, ...]

    @property
    def switch(self) -> str:
        return "GUIDE_" + self.id.upper()


GUIDES: tuple[Guide, ...] = (
    Guide("answer_in_schema", "Answers in their schema", "answers",
          "Give your answer as one call of your answer tool, never as text. Give every field the type its schema "
          "names: a list as a list of separate items, one line as one string, a number as a number.",
          ("a plan answered in its schema", "the answer as a call, not as text")),
    Guide("stop_when_done", "Stops when its checks pass", "focus",
          "When the checks you were asked to make pass, stop and give your answer straight away; do not look further.",
          ("stopping when its tests pass",)),
    Guide("no_repetition", "Never repeats itself", "output",
          "Never write the same line, item or phrase twice. If you notice you are repeating yourself, stop writing "
          "it and finish your answer.",
          ("a long list without repeating itself",)),
    Guide("keep_to_role", "Keeps to its role", "role",
          "Change only what your request names as yours. A fault in another part is reported in your answer, not "
          "fixed, and a part another role builds is left for it: never write or change another part's files, by a "
          "file tool or by a command.",
          ("a role kept", "a role kept while building")),
    Guide("exact_arguments", "Uses each tool's own argument names", "tools",
          "Call a tool with exactly the argument names its definition gives, no others, and every one it requires.",
          ("exact argument names",)),
    Guide("one_program_a_command", "One program a command", "commands",
          "There is no shell: a command is one program and its arguments, each argument its own item. Never join "
          "commands with `&&`, `;` or `|`, and never put a program and its arguments in one string.",
          ("one program a command",)),
    Guide("paths_as_given", "Paths as it was given them", "files",
          "Write every path as it was given to you, relative to the workspace, such as the project's folder and "
          "the file in it. Never start a path with `/` or a folder you were not given.",
          ("paths as given",)),
    Guide("heed_refusals", "Changes course when refused", "tools",
          "When a call is refused, read why and do what the refusal says instead. Never send the refused call "
          "again, the same or slightly changed.",
          ("a refusal heeded",)),
)
BY_ID = {guide.id: guide for guide in GUIDES}
#: The check that decides the end-of-request reminder.
REMINDER_CHECK = "a rule kept after a long request"


def switch_on(guide: Guide) -> bool:
    """Off unless set, as every switch is; compose turns each on (owner, 2026-10-23)."""
    return is_on(guide.switch, False)


@dataclass
class Profile:
    """How one model is steered, as measured and as the owner set it."""

    model: str
    tier: str = ""
    score: float | None = None
    chosen: dict[str, bool] = field(default_factory=dict)
    overrides: dict[str, bool] = field(default_factory=dict)
    tail_reminder: bool = False
    measured_at: str = ""

    def active(self, guide: Guide) -> bool:
        wanted = self.overrides.get(guide.id, self.chosen.get(guide.id, False))
        return bool(wanted) and switch_on(guide)


def tier_of(score: float | None) -> str:
    if score is None:
        return ""
    return "strong" if score >= STRONG_FROM else "standard" if score >= STANDARD_FROM else "weak"


def chosen_by(diagnosis: Any) -> Profile:
    """The profile a deep diagnosis calls for (`deep_diagnosis.Diagnosis`)."""
    baseline = {r.check: r for r in diagnosis.baseline}
    tries = sum(r.tries for r in diagnosis.baseline)
    score = round(sum(r.passed for r in diagnosis.baseline) / tries, 3) if tries else None
    tier = tier_of(score)
    chosen: dict[str, bool] = {}
    for guide in GUIDES:
        short = [c for c in guide.checks if c in baseline and baseline[c].passed < baseline[c].tries]
        helped = guide.id in (diagnosis.helped or ())
        chosen[guide.id] = bool(short) and (helped or tier == "weak")
    reminder = baseline.get(REMINDER_CHECK)
    tail = tier == "weak" or bool(reminder and reminder.passed < reminder.tries and diagnosis.reminder_helped)
    return Profile(model=diagnosis.model, tier=tier, score=score, chosen=chosen, tail_reminder=tail,
                   measured_at=diagnosis.measured_at)


def keep(profile: Profile) -> None:
    from app.models.registry import merge_into_fitness

    merge_into_fitness(profile.model, {RECORD_KEY: asdict(profile)})


def recorded(model: str) -> Profile | None:
    from app.models.registry import _slug, fitness_dir

    try:
        found = json.loads((fitness_dir() / f"{_slug(model)}.json").read_text(encoding="utf-8")).get(RECORD_KEY)
        return Profile(**{k: v for k, v in found.items() if k in Profile.__dataclass_fields__})
    except Exception:  # noqa: BLE001 - never profiled
        return None


def set_override(model: str, guide_id: str, value: bool | None) -> Profile:
    """The owner's choice for one item on this model: on, off, or None to follow the diagnosis."""
    if guide_id not in BY_ID:
        raise KeyError(guide_id)
    profile = recorded(model) or Profile(model=model)
    if value is None:
        profile.overrides.pop(guide_id, None)
    else:
        profile.overrides[guide_id] = bool(value)
    keep(profile)
    return profile


def ensure_rows() -> None:
    """Each guide's line as its `guide:<id>` row, written only where there is none, so an edit is kept."""
    try:
        from app.server.plugin_store import PluginStore

        store = PluginStore.shared()
        for guide in GUIDES:
            if not store.get_instructions(PREFIX + guide.id):
                store.update_instructions(PREFIX + guide.id, guide.line)
    except Exception:  # noqa: BLE001 - the catalogue's own lines still apply
        logger.debug("Could not seed the guidance rows", exc_info=True)


def active_keys(model: str) -> list[str]:
    """The table keys of the items active for `model`, in catalogue order."""
    profile = recorded(model)
    if profile is None:
        return []
    return [PREFIX + guide.id for guide in GUIDES if profile.active(guide)]


def reminder(model: str) -> str:
    """The end-of-request reminder for a model that needs one; "" otherwise."""
    profile = recorded(model)
    if profile is None or not profile.tail_reminder:
        return ""
    lines = []
    try:
        from app.server.plugin_store import PluginStore

        store = PluginStore.shared()
        lines = [store.get_instructions(PREFIX + guide.id) or guide.line for guide in GUIDES if profile.active(guide)]
    except Exception:  # noqa: BLE001
        lines = [guide.line for guide in GUIDES if profile.active(guide)]
    return ("Before you reply, keep to these:\n" + "\n".join(f"- {line}" for line in lines)) if lines else ""


class _Switch:
    """One guide's switch, for `provenance.SWITCHES`."""

    def __init__(self, guide: Guide) -> None:
        self.guide = guide
        self.ON_BY_DEFAULT = False

    def enabled(self) -> bool:
        return switch_on(self.guide)


SWITCHES = {guide.switch: _Switch(guide) for guide in GUIDES}
#: One attribute a guide, `<id>_switch`, which `provenance.SWITCHES` names.
for _guide in GUIDES:
    globals()[f"{_guide.id}_switch"] = SWITCHES[_guide.switch]

__all__ = ["BY_ID", "GUIDES", "Guide", "PREFIX", "Profile", "RECORD_KEY", "REMINDER_CHECK", "SWITCHES", "active_keys",
           "chosen_by", "ensure_rows", "keep", "recorded", "reminder", "set_override", "switch_on", "tier_of"]
