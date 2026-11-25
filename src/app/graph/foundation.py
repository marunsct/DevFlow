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
    *, already_deferred: list[str] = (), did_not_start: str = "", passed_unbuilt: set[str] = frozenset(),
) -> list[str]:
    """Why later sprints need the criteria `deferring` of sprint `index` (0-based); [] when nothing later does.

    `saved` is the last acceptance result (`suite.last_result`), `due` the criteria due now, `did_not_start` the
    reason the product did not start for the suite ("" when it started), `passed_unbuilt` the tests that passed before
    anything was built, which prove nothing of the sprint and are not counted as its passes (LF.1446).
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
    passing = [test for test in own_tests if test.get("outcome") == "passed"]
    passed = sum(1 for test in passing if str(test.get("name")) not in passed_unbuilt)
    unbuilt = len(passing) - passed
    if dependents and own_tests and passed * 2 < len(own_tests):
        reasons.append(
            f"the plan has sprint {', '.join(str(n) for n in dependents)} depend on sprint {number}, which passes "
            f"{passed} of its {len(own_tests)} acceptance tests"
            + (f" ({unbuilt} more pass, but passed before anything was built)" if unbuilt else "")
        )
    return reasons


def what_later_work_needs(state: Any, failing: list[dict[str, Any]]) -> list[str]:
    """`later_work_needs` for the stuck sprint on `state`, deferring its failing criteria; [] on any doubt."""
    try:
        from app.acceptance import passed_unbuilt, suite
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
            passed_unbuilt=passed_unbuilt.names(root),
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
        "other work of this sprint; nothing later can pass while it fails. "
        + READING_NOT_MEASURED
    )


#: Said with every re-plan (LF.1441): the lead's account of a cause is its reading of the code, which the next stages
#: took as fact - measured, a guessed cause became a work order's title, a review's defect and two commit titles.
READING_NOT_MEASURED = (
    "What the harness measured is below. A cause you name from reading the code is your reading, not a measurement: "
    "write it in the work order as what to check first, with the measured failure it should explain, and do not name "
    "one the measurement contradicts."
)

#: The heading of the harness's own measurement in a re-plan request.
MEASURED_HEADING = "--- What the last measurement found failing (measured by the harness) ---"
#: Failing tests listed per criterion, and the characters the whole block may take.
TESTS_PER_CRITERION = 4
MOST_MEASUREMENT = 4_000


def the_last_measurement(state: Any, deferring: list[str]) -> str:
    """What the harness measured of the attempt that ended, for the lead planning its sprint again; "" with nothing.

    LF.1441: the re-plan request held one line ("passes 8 of its 21 acceptance tests") and none of the five defects the
    test round had raised one second earlier. The lead read files for 19 minutes, settled on a cause the harness had
    measured false (that the service could not start), and the tester's real finding never appeared again. Now it is
    told, from the saved results: what is known to hold (the product starts and answers; which tests pass, and which
    passed before anything was built), each failing criterion's failing tests with what each said and the server's
    stated error, the unit report's distinct causes, and the attempt's open defects with what each printed. Never
    raises.
    """
    try:
        return _the_last_measurement(state, deferring)
    except Exception as error:  # noqa: BLE001 - the re-plan goes on with its one line
        from app.observability.degraded import degraded

        degraded("foundation.the_last_measurement", error)
        return ""


def _the_last_measurement(state: Any, deferring: list[str]) -> str:
    import json
    from pathlib import Path

    from app import ci
    from app.acceptance import passed_unbuilt, suite
    from app.acceptance.failure_said import what_it_said

    root = state["repository"].root_path
    saved = suite.last_result(root) or {}
    lines: list[str] = []
    unbuilt = passed_unbuilt.names(root)
    entries = {**(saved.get("criteria") or {}), **(saved.get("change_requests") or {})}
    tests = [test for entry in entries.values() for test in (entry or {}).get("tests") or [] if isinstance(test, dict)]
    problem = str(saved.get("problem") or "")
    if saved.get("ran") and tests and not problem.startswith(suite.PRODUCT_DID_NOT_START):
        passing = [t for t in tests if t.get("outcome") == "passed"]
        early = [t for t in passing if str(t.get("name")) in unbuilt]
        lines.append(
            f"Known to hold: the product starts for the acceptance suite and answers it; {len(passing)} of "
            f"{len(tests)} locked tests pass"
            + (f", {len(early)} of them tests that passed before anything was built" if early else "") + ".")
    elif problem:
        lines.append(f"The product did not start for the acceptance suite: {' '.join(problem.split())[:300]}")
    for cid in deferring:
        failing = [t for t in (entries.get(cid) or {}).get("tests") or []
                   if isinstance(t, dict) and t.get("outcome") == "failed"]
        if not failing:
            continue
        lines.append(f"{cid}, failing:")
        for test in failing[:TESTS_PER_CRITERION]:
            said = what_it_said(test.get("message") or "")
            lines.append(f"  - {test.get('name')}" + (f": {said}" if said else ""))
        if len(failing) > TESTS_PER_CRITERION:
            lines.append(f"  - and {len(failing) - TESTS_PER_CRITERION} more")
    stated = _the_server_s_stated_errors(str(saved.get("server_log") or ""))
    if stated:
        lines.append("The server's log while they ran states: " + "; ".join(stated))
    try:
        unit = json.loads((Path(root) / ci.UNIT_RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        unit = {}
    causes = ci.the_distinct_causes(str((unit or {}).get("output") or "")) if isinstance(unit, dict) else ""
    if causes and not (unit or {}).get("passed"):
        lines.append("The unit tests fail. " + causes)
    cycle = state.get("remediation")
    still = [d for d in getattr(cycle, "defects", None) or [] if str(getattr(d, "status", "")) == "open"]
    if still:
        lines.append("Defects the attempt left open, which the new plan answers:")
        for defect in still:
            title = " ".join(str(getattr(defect, "description", "") or "").split())[:240]
            printed = " ".join(str(getattr(defect, "actual_behavior", "") or "").split())[:300]
            lines.append(f"  - [{getattr(defect, 'source', '') or 'defect'}] {title}"
                         + (f" - printed: {printed}" if printed else ""))
    if not lines:
        return ""
    return ("\n" + MEASURED_HEADING + "\n" + "\n".join(lines))[:MOST_MEASUREMENT]


#: A server log line that states an error, not one that only reports a request's status.
_ACCESS_LINE = re.compile(r'"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) [^"]*" \d{3}')
_STATES_AN_ERROR = re.compile(r"\b\w*(?:Error|Exception)\b|\bTraceback\b|\bpanic", re.I)


def _the_server_s_stated_errors(log: str) -> list[str]:
    """The distinct lines of a server log that state an error, access-log lines left out; at most three."""
    found: list[str] = []
    for line in log.splitlines():
        text = " ".join(line.split())
        if text and not _ACCESS_LINE.search(text) and _STATES_AN_ERROR.search(text) and text not in found:
            found.append(text[:240])
        if len(found) >= 3:
            break
    return found


__all__ = ["LEAST_SHARED", "MEASURED_HEADING", "NOT_BUILT_YET", "READING_NOT_MEASURED", "failure_step",
           "later_work_needs", "replan_guidance", "the_last_measurement", "what_later_work_needs"]
