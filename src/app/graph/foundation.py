"""Whether later sprints build on what a stuck sprint would defer (LF.1264).

The escalation's automatic answer to a stuck sprint is to defer what still fails and start the next sprint. That is
right when nothing later needs the deferred work, and wrong when it is the foundation. Measured on one run: sprint 1
of three (sign-up and sign-in) ended with 5 of its 18 acceptance tests passing; "defer and continue" started sprint 2,
whose plan said "Dependencies: Sprint 1" and every one of whose tests began by signing up through the suite's helper;
fifteen hours and about 60M tokens followed with the pass count unchanged.

Evidence the harness already has, each enough on its own:

- the product does not start for the acceptance suite: nothing later can run on it;
- the locked suite: most tests of the criteria later sprints own already fail at the same step as the tests of the
  criteria being deferred (the same wrong answer, or the same message a shared helper throws). A later test that
  fails because its own work is not built yet is answered "not found", which is not counted;
- the sprint plan: a later sprint names this one as a dependency, and this sprint passes fewer than half of its own
  criteria's tests - what the later sprint builds on is mostly not there.

A deferral nothing later needs keeps the escalation's old answer.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

#: The answers a request gets from work not built yet: a later sprint's test failing with one says nothing about
#: the foundation it runs on.
NOT_BUILT_YET = frozenset({"404", "405", "501"})

#: Messages that are what an absent page, element or route gives, for the same reason.
_NOT_BUILT_WORDS = re.compile(r"\b(?:timed?\s*out|timeout|not found|no such|cannot find|could not find)\b|\b404\b", re.I)

#: A dependency naming the sprint before it without its number.
_THE_ONE_BEFORE = re.compile(r"\b(?:previous|prior|earlier|preceding)\s+sprints?\b", re.I)

#: Fewest later tests failing at the deferred step before they count as evidence.
LEAST_SHARED = 3


def failure_step(message: str) -> str:
    """Where a failed test stopped, as a key two tests share when they stopped at the same step; "" when unknown.

    The wrong status it was answered (`assert 429 == 201`), else the first line of its message (what a shared helper
    throws: "Login rate limited"). "" for an answer that work not built yet gives.
    """
    from app.graph.acceptance_nodes import _the_wrong_answer

    text = str(message or "")
    status = _the_wrong_answer(text)
    if status:
        return "" if status in NOT_BUILT_YET else f"answered {status}"
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first or _NOT_BUILT_WORDS.search(first):
        return ""
    return " ".join(first.split())[:160]


def _tests_of(entries: dict[str, Any], ids: list[str]) -> list[dict[str, Any]]:
    return [test for item in ids for test in ((entries.get(item) or {}).get("tests") or []) if isinstance(test, dict)]


def _names_this_sprint(dependency: str, number: int, later: int) -> bool:
    from app.agents.scrum_master import _NAMES_A_SPRINT

    named = [int(n) for n in _NAMES_A_SPRINT.findall(str(dependency))]
    return number in named or (later == number + 1 and bool(_THE_ONE_BEFORE.search(str(dependency))))


def later_work_needs(
    sprints: list[Any], index: int, saved: dict[str, Any], deferring: list[str], due: list[str],
    *, already_deferred: list[str] = (), did_not_start: str = "",
) -> list[str]:
    """Why later sprints need the criteria `deferring` of sprint `index` (0-based); [] when nothing later does.

    `saved` is the last acceptance result (`suite.last_result`), `due` the criteria due now, `did_not_start` the
    reason the product did not start for the suite ("" when it started).
    """
    later_sprints = list(sprints)[index + 1:]
    if not deferring or not later_sprints:
        return []
    reasons: list[str] = []
    if did_not_start:
        reasons.append(f"the product does not start for the acceptance suite ({did_not_start.splitlines()[0][:200]})")

    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    steps = {step for test in _tests_of(entries, deferring) if test.get("outcome") == "failed"
             if (step := failure_step(test.get("message") or ""))}
    later_ids = [item for sprint in later_sprints for item in (getattr(sprint, "criteria", None) or [])
                 if item not in due and item not in already_deferred and item not in deferring]
    later_tests = _tests_of(entries, list(dict.fromkeys(later_ids)))
    shared = [test for test in later_tests
              if test.get("outcome") == "failed" and failure_step(test.get("message") or "") in steps]
    if steps and len(shared) >= LEAST_SHARED and len(shared) * 2 >= len(later_tests):
        common = sorted({failure_step(test.get("message") or "") for test in shared})
        reasons.append(
            f"{len(shared)} of the {len(later_tests)} tests of later sprints' criteria already fail at the same step "
            f"as the tests of {', '.join(deferring)}: {'; '.join(common)[:300]}"
        )

    number = index + 1
    dependents = [later for later, sprint in enumerate(later_sprints, start=number + 1)
                  if any(_names_this_sprint(d, number, later) for d in getattr(sprint, "dependencies", None) or [])]
    own = [item for item in (getattr(list(sprints)[index], "criteria", None) or []) if item in entries] or list(deferring)
    own_tests = _tests_of(entries, own)
    passed = sum(1 for test in own_tests if test.get("outcome") == "passed")
    if dependents and own_tests and passed * 2 < len(own_tests):
        reasons.append(
            f"the plan has sprint {', '.join(str(n) for n in dependents)} depend on sprint {number}, which passes "
            f"{passed} of its {len(own_tests)} acceptance tests"
        )
    return reasons


def what_later_work_needs(state: Any, failing: list[dict[str, Any]]) -> list[str]:
    """`later_work_needs` for the stuck sprint on `state`, deferring its failing criteria; [] on any doubt."""
    try:
        from app.acceptance import suite
        from app.graph.acceptance_nodes import criteria_due

        root = state["repository"].root_path
        sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
        deferring = [str(e.get("id")) for e in failing if str(e.get("id", "")).startswith("AC-")]
        saved = suite.last_result(root) or {}
        problem = str(saved.get("problem") or "")
        return later_work_needs(
            sprints, int(state.get("current_sprint_index") or 0), saved, deferring, list(criteria_due(state) or []),
            already_deferred=list(suite.deferred(root)),
            did_not_start=problem if problem.startswith(suite.PRODUCT_DID_NOT_START) else "",
        )
    except Exception:  # noqa: BLE001 - the escalation's own answer stands
        logger.debug("Could not tell whether later sprints need the deferred criteria", exc_info=True)
        return []


def replan_guidance(number: int, goal: str, deferring: list[str], reasons: list[str]) -> str:
    """What the technical lead is told when a foundation sprint is planned again."""
    return (
        f"Plan sprint {number} ({goal.strip() or 'the current sprint'}) again: later sprints build on it, so its "
        f"failing criteria ({', '.join(deferring)}) cannot be deferred. Evidence: {'; '.join(reasons)}. "
        "Find the one cause behind these failures first - the step they all stop at - and make it pass before any "
        "other work of this sprint; nothing later can pass while it fails."
    )


__all__ = ["LEAST_SHARED", "NOT_BUILT_YET", "failure_step", "later_work_needs", "replan_guidance",
           "what_later_work_needs"]
