"""Three smaller prompts, each behind its own switch and off until measured (per-role audit 2026-11-20, items 4, 7, 8).

- `QA_PROMPT_TRIMMED`: the acceptance suite's writer and its reviewer (the QA lead) are given only the parts of the
  stack's guidance that are about tests, no lesson written for every role (the lessons on record are all a fixer's:
  `app.plugins.lesson_distiller` proposes them from defect records), and the writer no beginner documentation
  section. Measured: 13.2k-16.6k characters of system prompt, with "wrap async route handlers" and fixer lessons in
  it; 84% of the C# writer's output was reasoning. *Measure:* author model minutes, reasoning share, write refusals.
- `REVIEWER_SHAPED_PLUGIN_CONTENT`: a role that reviews and writes nothing (`REVIEWERS`) is given the stack guidance
  without its how-to (what to install, how to set up and run), no stack setup notes, no command guide - it has no
  command tool - and no lesson written for every role. Measured: 2.9k-9.7k characters of writer guidance in them.
  *Measure:* input characters per review call, finding precision.
- `LEAD_REPLAN_REQUEST_SMALLER`: a re-plan of a sprint names the files its last attempt planned and changed
  (`app.agents.technical_lead`), and the lead's memory holds those whole, the rest of the product named with what it
  defines, and each long document as its outline and the sections the request points at
  (`app.agents.project_memory`). Measured: 96k-234k characters a call, 134k of them project memory. *Measure:* lead
  cut-offs, lead model minutes per plan, plan readiness rate.

A server's prompt cache reuses only a byte-identical prefix, so each switch is read once per run (`for_this_run`):
set on the admin page while a run is going, it takes effect from the next run, and two calls of one run never differ
by it. Outside a run it is read each time, as every switch is.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False
#: Runs whose choices are remembered at once in one process: a ceiling, not a working limit.
MOST_RUNS_REMEMBERED = 256

_LOCK = threading.Lock()
_CHOSEN: OrderedDict[str, dict[str, bool]] = OrderedDict()
_NOTED: set[tuple[str, str, str]] = set()


def _the_run() -> str:
    try:
        from app.models.model_pin import current_run_id

        return current_run_id()
    except Exception:  # noqa: BLE001 - outside a run
        return ""


def for_this_run(name: str, default: bool = ON_BY_DEFAULT) -> bool:
    """Switch `name` as this run first read it; read afresh outside a run."""
    run = _the_run()
    if not run:
        return is_on(name, default)
    with _LOCK:
        chosen = _CHOSEN.setdefault(run, {})
        _CHOSEN.move_to_end(run)
        while len(_CHOSEN) > MOST_RUNS_REMEMBERED:
            gone, _ = _CHOSEN.popitem(last=False)
            _NOTED.difference_update({key for key in _NOTED if key[0] == gone})
        if name not in chosen:
            chosen[name] = is_on(name, default)
        return chosen[name]


class _Switch:
    """One of the three as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT

    def __init__(self, name: str, explanation: str) -> None:
        self.name = name
        #: What the admin page says this switch does.
        self.explanation = explanation

    def enabled(self) -> bool:
        return for_this_run(self.name, self.ON_BY_DEFAULT)


qa_prompt_trimmed_switch = _Switch(
    "QA_PROMPT_TRIMMED",
    "The acceptance suite's writer and the QA lead are given only the stack guidance about tests, no lesson learned "
    "from fixes, and the writer no beginner documentation section. Read once per run.",
)
reviewer_shaped_switch = _Switch(
    "REVIEWER_SHAPED_PLUGIN_CONTENT",
    "A review role is given the stack guidance without what to install and how to set up and run, no setup notes, "
    "no command guide and no lesson learned from fixes. Read once per run.",
)
lead_replan_smaller_switch = _Switch(
    "LEAD_REPLAN_REQUEST_SMALLER",
    "A re-plan of a sprint holds whole only the files its last attempt planned and changed; the rest of the product "
    "is named with what it defines and long documents are held as their outline. Read once per run.",
)

#: The roles that review and write nothing, by the name their agent is built with (`*_advice_reviewer` as well).
REVIEWERS = frozenset({
    "acceptance_reviewer", "senior_architect_reviewer", "security_reviewer", "milestone_reviewer", "code_reviewer",
    "suite_dispute",
})
#: The QA lead's agent: it reviews the suite, so it is the suite writer's peer for `QA_PROMPT_TRIMMED`.
QA_LEAD = "acceptance_reviewer"

#: What the harness records once per run and role when a switch shaped a prompt; the switch-firing check reads it.
RECORD_KIND = "prompt_shaped"
SAID = {
    qa_prompt_trimmed_switch.name: "Stack guidance kept to its parts about tests for",
    reviewer_shaped_switch.name: "Stack guidance kept to its review lines for",
}


def a_reviewer(role: str) -> bool:
    return role in REVIEWERS or str(role or "").endswith("_advice_reviewer")


def plugin_shape(role: str, writing_the_suite: bool = False) -> dict[str, bool]:
    """How `role`'s stack guidance is cut (`app.plugins.registry.get_plugin_instructions`); {} for as it is."""
    shape: dict[str, bool] = {}
    if (writing_the_suite or role == QA_LEAD) and qa_prompt_trimmed_switch.enabled():
        shape["tests_only"] = True
    if a_reviewer(role) and reviewer_shaped_switch.enabled():
        shape["review_lines_only"] = True
    return shape


def _switches_of(shape: dict[str, bool]) -> list[str]:
    return [name for name, key in ((qa_prompt_trimmed_switch.name, "tests_only"),
                                   (reviewer_shaped_switch.name, "review_lines_only")) if shape.get(key)]


def unnoted(shape: dict[str, bool], role: str) -> bool:
    """Whether this run has not yet recorded a switch of `shape` shaping `role`'s prompt (so `note_shaped` will)."""
    run = _the_run()
    with _LOCK:
        return bool(run) and any((run, name, role) not in _NOTED for name in _switches_of(shape))


def note_shaped(shape: dict[str, bool], role: str, stage: str, left_out: int) -> None:
    """Record, once per run and role, that a switch shaped this role's prompt and how much it left out. Never raises."""
    run = _the_run()
    if not run:
        return
    for name in _switches_of(shape):
        with _LOCK:
            if (run, name, role) in _NOTED:
                continue
            _NOTED.add((run, name, role))
        try:
            from app.observability.transcript import record

            record(run, stage, RECORD_KIND, switch=name, role=role, left_out_characters=left_out,
                   message=f"{SAID[name]} {role}: {left_out:,} characters left out")
        except Exception:  # noqa: BLE001 - a record never fails a call
            logger.debug("Could not record a shaped prompt", exc_info=True)


#: Heads the list of files a re-plan's sprint planned and changed, in the lead's request (`LEAD_REPLAN_REQUEST_SMALLER`).
SPRINT_FILES_HEADING = "--- The files this sprint's last attempt planned and changed ---"
#: What the lead's smaller memory says of itself; the switch-firing check reads it.
REPLAN_SAID = ("Held whole: the files this sprint's last attempt planned and changed; the rest of the product is named "
               "below with what it defines, and each long document is held as its outline and the sections this "
               "request points at.")


def sprint_files_section(files: list[str]) -> str:
    """The section of a re-plan's request naming the sprint's own files, or "" for none."""
    named = [str(f).strip() for f in files if str(f).strip()]
    if not named:
        return ""
    return (SPRINT_FILES_HEADING + "\n" + "\n".join(f"- {f}" for f in named)
            + "\nThe project memory holds these whole; read any other file when the plan needs its body.\n\n")


def sprint_files_in(request: str) -> list[str]:
    """The files a re-plan's request names under `SPRINT_FILES_HEADING`; [] when it has none."""
    text = str(request or "")
    at = text.find(SPRINT_FILES_HEADING)
    if at < 0:
        return []
    files: list[str] = []
    for line in text[at + len(SPRINT_FILES_HEADING):].lstrip("\n").splitlines():
        if not line.startswith("- "):
            break
        files.append(line[2:].strip())
    return [f for f in files if f]


__all__ = [
    "REPLAN_SAID", "SPRINT_FILES_HEADING", "sprint_files_in", "sprint_files_section",
    "MOST_RUNS_REMEMBERED", "ON_BY_DEFAULT", "QA_LEAD", "RECORD_KIND", "REVIEWERS", "SAID", "a_reviewer",
    "for_this_run", "lead_replan_smaller_switch", "note_shaped", "plugin_shape", "qa_prompt_trimmed_switch", "unnoted",
    "reviewer_shaped_switch",
]
