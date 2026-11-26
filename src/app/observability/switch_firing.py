"""Which switches acted in a run, read from what they leave in its transcript (plan item 22).

`switches_on` in a KPI row says a switch was deployed, not that it did anything: of 66 switches on in the last measured
run, a handful ever reach their condition. A switch that was on and never acted cannot have moved a KPI, so the gate
(`scripts/loop/switch_gate.py`) must tell "never acted" from "acted and changed nothing". Only a switch with text of
its own in a request or a tool's answer can be told apart; any other is reported as having no signal, never as idle.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

#: Switch -> text only that switch puts in a model request or a tool's answer.
SIGNALS: dict[str, str] = {
    "ONE_DESIGN_REVIEW": "revised once and not reviewed again",
    "DIAGNOSE_A_RECURRING_CAUSE": "A diagnosis made after the attempts above failed, before this attempt:",
    "SPRINT_TIME_BUDGET": "the sprint ran past its time budget",
    "CONCURRENT_WRITE_PROBE": "Writes made at the same moment are not each kept",
    "WRONG_SHAPE_BODY_PROBE": "sent a JSON body that is not an object",
    "EDGE_PROBE": "Requests at the edges of the interface contract are not handled",
    "PAGE_PROBE": "A check of the page in a browser finds:",
    "DRAFTING_IN_WAVES": "were drafted before it and are shown below as they are now",
    "STABLE_MEMORY_ORDER": "The documents that hold for every fix come first, the code after them",
    "LEAN_TOOL_LISTS": "so no file listing or search is offered",
    "SLICED_MEMORY": "the files this request names and the files they import",
    "INTAKE_ASKS_FIRST": "only those whose answer would change what the product does",
    "NEAR_GREEN_REPAIR_TO_ROUND": "the repaired suite is near green, so the sprint is measured again in a test round instead of planned again",
    "FIX_STAGES_THAT_CLOSE_NOTHING": "a fix round closed no defect and left the product unchanged, so the attempt ends instead of another round",
    "DESIGN_REVISION_CROSS_CHECKED": "Cross-checked against the sections left unchanged",
    "NEAR_GREEN_REPLANNED_ONCE": "a near-green suite is not planned again a second time",
    "LESSON_DISTILLER": "LESSONS FROM EARLIER RUNS",
    "ASSUMPTIONS_GATE": "Open questions, answered",
    "SHARED_FACTS": "The facts this work is built and judged under",
    "WHERE_THINGS_STAND": "Where things stand",
    "LOCALISE_FIRST": "You find where in a codebase a failure is caused",
    "VERIFY_AFTER_WRITE": "Your defect is fixed",
    "STABLE_TOOLS": "is withheld at this point of the stage",
    "AGENT_LOOP_FIX_LIMITS": "and no file has changed since the first",
    "MUTANT_CHECK_IN_THE_FIX_STAGE": "The harness made the deliberate change described above",
    "MUTATION_GAPS_BUNDLED": "The other changes no test notices in the same file, to settle in this same fix",
    "SPEC_DRY_RUN": "the dry run of the suite",
    "IDS_READ_WITHOUT_A_CREATE": "an id the test never created",
    "SETTLE_SPEC_CONTRADICTIONS": "The design review of this specification ended with these findings open",
    "BRIEF_OVER_SPEC_ADDITIONS": "What the specification adds beyond the brief",
    "TESTS_OF_ACTIONS_WITHIN_A_VIEW": "changes the state a current view depends on",
    "CONTESTED_TESTS_CONFIRMED": "The harness ran a copy of this test with",
    "WEB_TOOLS_AFTER_TWO_FAILED_FIXES": "Two fixes of this defect have failed, so `search_the_web` and `read_web_page`",
    "STUCK_LOOKUP_CONDENSED": "A note on this error, condensed from what others found",
    "DOCUMENTATION_EXCERPTS_BOUNDED": "the passages of its page that bear on the brief",
    "OPENING_ROOM_FOR_REVIEWS": "so the files it holds were cut to its budget",
    "INTERFACE_STATES_AS_CRITERIA": "name what a person sees in three states",
    "PRODUCT_RESEARCH": "Comparable products: suggestions the brief does not require",
    "API_CARDS_FOR_NEWER_RELEASES": "Libraries whose installed release line is newer than this model's training data",
    "FRAMEWORK_GUIDANCE_FOR_ADVISERS": "its own guidance, for the release this project uses",
    "LOOKUP_AT_FIRST_SIGHT": "Looked up when first seen: this error comes from the installed package",
    "USAGE_NOTES_FROM_THE_INSTALLED_PACKAGE": "How the installed libraries define the names this code calls",
    "SPECIALIST_DOMAIN_REVIEW": "Your own domain: defects in this sprint's changed files",
    "PULL_REQUEST_DELIVERY": "Delivered to the seeded repository",
    "CO_DEVELOPMENT": "The person who owns this run changed its files between stages",
    "DOMAIN_CRAFT_CHECKLISTS": "Craft checklist for your files",
    "ADVICE_SIZED_TO_THE_BRIEF": "Advice sized to the brief",
    "FAST_DESIGN_GATE_ON_PRODUCT_BREAKING": "held as product-breaking",
    # Recorded by the harness once per run and role (`app.agents.prompt_size`); the lead's in its memory's own words.
    "QA_PROMPT_TRIMMED": "Stack guidance kept to its parts about tests for",
    "REVIEWER_SHAPED_PLUGIN_CONTENT": "Stack guidance kept to its review lines for",
    "LEAD_REPLAN_REQUEST_SMALLER": "Held whole: the files this sprint's last attempt planned and changed",
    # Recorded by the harness once per fix round whose order it changed (`app.graph.order_of_fixes`).
    "FIX_ORDER_CRITERIA_FIRST": "Failing criteria and release findings fixed ahead of the other defects",
    # Recorded by the harness once per run and stage whose rewrite the later trigger kept off (`app.agents.summarise_later`).
    "SUMMARISE_LATER_WITH_HEADROOM": "A conversation kept whole past the usual trigger, the window having room",
    # Recorded by the harness once per run and stage (`app.agents.reply_room`).
    "REPLY_ROOM_SIZED_PER_ROLE": "The room kept for the reply was sized to the role",
    # Recorded by the harness once per stage visit whose memory it held to the budget (`app.agents.request_budget`).
    "REQUEST_BUDGET_FOR_EVERY_STAGE": "A stage's memory was held to its request's input budget",
    # In the answer to a whole read the request had no room for (`app.agents.room_for_reads`).
    "READS_SIZED_TO_THE_ROOM": "more than this request has room left for",
    # Recorded by the harness each time it switches thinking off for it (`app.agents.deliberated_reads`).
    "LONG_REASONING_BEFORE_A_READ": "Thinking switched off for the reply after one that reasoned at length and then only read",
    # Recorded by the harness each red thorough round it measures alone (`app.graph.measured_round`).
    "MEASURED_ROUND_WHEN_RED": "A red round measured by the harness alone in thorough delivery",
    # Recorded by the harness each time a fixer's memory is chosen again at a summary
    # (`app.agents.fixers_hold_what_they_read`).
    "FIXERS_HOLD_WHAT_THEY_READ": "A fixer's memory holds the files it was reading after a summary",
    # Recorded by the harness once per fix-stage visit whose old reads it kept as one-line notes
    # (`app.agents.old_reads_stubbed`).
    "FIX_STAGES_STUB_OLD_READS": "A fix stage's earlier reads kept as one-line notes",
    # Recorded by the harness once per request that carried its files' neighbours (`app.analysis.project_graph`, KG.1).
    "PROJECT_GRAPH_FIXES": "A fix request carried its files' neighbours from the code graph",
    "PROJECT_GRAPH_BUILDERS": "A work order's request carried its files' neighbours from the code graph",
    # Plan KG.5-KG.8: each in the text it puts in a request (the memory's block, a review's section) or a tool's
    # answer (a search, a read, a write).
    "DEFINITIONS_BEFORE_FILES": "held as the definitions this work reaches",
    "GRAPH_IN_SEARCH_ANSWERS": "The harness's code graph:",
    "USES_NAMED_AT_THE_WRITE": "Other files use what this write changed",
    "REVIEWS_HOLD_THE_CHANGE_AND_ITS_USES": "each with the signatures of what uses it",
    # Recorded by the harness once per run and role kind, and once per run it offers no web tool
    # (`app.agents.role_tool_lists`, `app.tools.research_tool`).
    "TOOL_LISTS_BY_ROLE_KIND": "tools held to its role's list",
    "WEB_TOOLS_BY_MEASURED_TIER": "No web tool offered to this model",
}
#: Transcript records the harness writes of what it did itself, with no model reading it: kind -> the field whose
#: text a switch's signal is looked for in.
HARNESS_RECORDS: dict[str, str] = {"repository_delivery": "message", "prompt_shaped": "message", "fix_order": "message",
                                   "summarised_later": "message",
                                   "reply_room": "message", "thinking_off_after_a_read": "message",
                                   "time_budget": "message", "request_budget": "message",
                                   "measured_round": "message", "fixer_memory_chosen_again": "message",
                                   "project_graph_reach": "message",
                                   # The tools the harness chose for a role or a model (`app.agents.role_tool_lists`).
                                   "tool_list_chosen": "message",
                                   # Each decision the run took, with its rationale (`app.decisions.record_decision`):
                                   # switches whose acts are decisions say so only there.
                                   "decision": "text"}


@dataclass(frozen=True)
class Chance:
    """When a switch should have acted: what held, and how the run's decision log shows that it did."""

    condition: str
    in_the_decisions: re.Pattern[str]


#: Switch -> its chance to act. A switch joins with one row here and its own text in `SIGNALS`.
CHANCES: dict[str, Chance] = {
    # Decided by the harness, with findings named: a person's approval asks for no ruling, by design.
    "SETTLE_SPEC_CONTRADICTIONS": Chance(
        "the design review ended with findings open",
        re.compile(r"\*\*Decision:\*\* build from the latest specification, recording the open points as known risks\n"
                   r"- \*\*Decided by:\*\* auto\b.*\n(?:- \*\*Options:\*\*.*\n)?- \*\*Why:\*\*[^\n]* Open: "),
    ),
}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str)


def fired(records: Iterable[Any], decisions: str = "") -> list[str]:
    """The switches in `SIGNALS` whose text appears in these transcript records, or in the run's decision log
    `decisions` (`docs/decision_log.md`), sorted.

    A switch whose act is a decision writes its words to the decision log, and a run recorded before decisions were
    kept in the transcript has them nowhere else: measured, `ONE_DESIGN_REVIEW` acted in 33 of 40 decision logs and
    this register counted it in none of 29 runs, so the switch gate read it as never acting.
    """
    seen: set[str] = {name for name, needle in SIGNALS.items() if needle in (decisions or "")}
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = record.get("kind")
        if kind == "model_request":
            text = _text(record.get("messages"))
        elif kind == "tool_result":
            text = _text(record.get("content") or record.get("result") or record.get("output"))
        elif kind in HARNESS_RECORDS:
            text = _text(record.get(HARNESS_RECORDS[kind]))
        else:
            continue
        seen.update(name for name, needle in SIGNALS.items() if name not in seen and needle in text)
    return sorted(seen)


def on_throughout(records: Iterable[Any]) -> list[str]:
    """The switches every provenance record of the run lists; [] with none. On for part of a run says nothing of the rest."""
    segments = [set(r.get("switches_on") or ()) for r in records if isinstance(r, dict) and r.get("kind") == "provenance"]
    return sorted(set.intersection(*segments)) if segments else []


def silent(on: Iterable[str], records: Iterable[Any], decisions: str) -> list[tuple[str, str]]:
    """(switch, condition) for each of `on` whose chance came in this run and that left no sign of acting."""
    acted = set(fired(records, decisions))
    return [(name, CHANCES[name].condition) for name in on
            if name in CHANCES and name not in acted and CHANCES[name].in_the_decisions.search(decisions or "")]


def chance_lines(records: Iterable[Any], decisions: str) -> list[str]:
    """One report line per switch in `CHANCES` that was on throughout: acted, never acted though it could, or no chance."""
    records = list(records)
    on = [name for name in on_throughout(records) if name in CHANCES]
    never = dict(silent(on, records, decisions))
    acted = set(fired(records, decisions))
    lines = []
    for name in on:
        if name in never:
            lines.append(f"    !!  {name}: NEVER ACTED, though it was on throughout and {never[name]}: look for a bug")
        elif name in acted:
            lines.append(f"  acted  {name}")
        else:
            lines.append(f"     -  {name}: on, its condition did not arise ({CHANCES[name].condition})")
    return lines


def without_a_signal(records: Iterable[Any]) -> list[str]:
    """The switches on throughout the run that have no firing signal here at all, sorted: whether they acted cannot be
    told from the run's records, so the switch gate can say nothing of them (90 of 125 when measured)."""
    return sorted(name for name in on_throughout(records) if name not in SIGNALS and name not in CHANCES)


def no_signal_line(records: Iterable[Any]) -> str:
    """The report line naming the switches on throughout with no firing signal; "" when there are none."""
    names = without_a_signal(records)
    if not names:
        return ""
    return (f"  {len(names):>4}  switches on throughout with no firing signal, so whether they acted cannot be told: "
            + " ".join(names))


__all__ = ["CHANCES", "Chance", "HARNESS_RECORDS", "SIGNALS", "chance_lines", "fired", "no_signal_line",
           "on_throughout", "silent", "without_a_signal"]
