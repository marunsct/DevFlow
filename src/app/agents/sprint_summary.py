"""One document per sprint, carrying every attempt made at it.

A sprint summary used to say four things: the goal, a status, how many test
rounds ran, and how many defects were found. None of those answer the question
a reader opens the file to ask - did this sprint deliver what it promised, and
how much of the suite proves it.

Two faults made it thinner than it looked. A sprint that failed and was
re-planned wrote its summary to the same path, so the second attempt erased the
first and the failure that caused the re-run left no trace at all. And a
re-planned sprint reads, from outside, as another sprint: a plan with three
sprints that re-ran one of them looked like four sprints' worth of work, which
is where "there are more sprints than were planned" comes from. There were not.
One sprint was attempted twice and nothing said so.

So the document is keyed by sprint rather than by attempt, and each attempt
appends to it. The heading states the sprint's place in the plan - "Sprint 2 of
3" - so the planned count can be read off any single file without adding them
up, and the attempt history below it accounts for the difference between the
number of sprints and the number of milestones a run worked through.

Case counts come from the run's own execution ledger, which records `tests`,
`passed` and `failed` for every command whose runner reported them, rather than
from what an agent said about its own tests. A count here is therefore the
suite's measured size at the end of that attempt, or absent - never a number
nobody measured. Which runners are understood is `sandbox._RUNNER_TOTALS`'s
business, not this module's: nothing here names a language or a framework, and
a sprint that built in one the ledger cannot parse gets a summary without
counts instead of a wrong one.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

#: The ledger fields a runner's own summary line fills in. An entry carrying all
#: three is a test run; an entry carrying none is any other command.
_COUNT_FIELDS = ("tests", "passed", "failed")


def _is_a_test_run(entry: Mapping[str, Any]) -> bool:
    return all(isinstance(entry.get(field), int) for field in _COUNT_FIELDS)


def count_test_cases(
    entries: Iterable[Mapping[str, Any]], *, since: str | None = None
) -> dict[str, int] | None:
    """The suite's size and result at the end of a window of ledger entries.

    The *last* test run in the window, not the sum of them. A sprint runs its
    suite once per round and a sum would count the same cases three times over,
    reporting 93 cases for a 31-case suite. What a reader wants from "number of
    test cases, passed, failed" is the state the sprint ended in.

    `since` is an ISO timestamp, compared as text because the ledger writes
    every `at` with `datetime.now(timezone.utc).isoformat()` and those sort
    lexically. An entry without one is kept: a missing timestamp is not
    evidence that the entry belongs to an earlier attempt, and dropping it
    would silently lose the only test run of a sprint.
    """
    latest: Mapping[str, Any] | None = None
    for entry in entries or ():
        if not _is_a_test_run(entry):
            continue
        at = entry.get("at")
        if since and isinstance(at, str) and at < since:
            continue
        latest = entry
    if latest is None:
        return None
    return {field: int(latest[field]) for field in _COUNT_FIELDS}


def _defect_tally(defects: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    fixed = sum(1 for defect in defects if str(defect.get("status", "")).lower() == "fixed")
    return {"found": len(defects), "fixed": fixed, "open": len(defects) - fixed}


def _cases_phrase(cases: Mapping[str, int] | None) -> str:
    """"31 (28 passed, 3 failed)", or why there is no number."""
    if not cases:
        return "not reported by the test runner"
    return f"{cases['tests']} ({cases['passed']} passed, {cases['failed']} failed)"


def _bullets(items: Sequence[str], *, empty: str) -> str:
    kept = [str(item).strip() for item in items or () if str(item).strip()]
    return "\n".join(f"- {item}" for item in kept) if kept else f"- {empty}"


#: How long one feature line may be before it is cut at a sentence end.
LONGEST_FEATURE_LINE = 160


def _one_line(text: str) -> str:
    """The first thing a delegated task says, as one line.

    `features` is each delegated task's `task_description`, which the technical
    lead writes as an instruction to a specialist: several paragraphs, usually
    ending in an "Acceptance criteria:" list of its own. Rendered as a bullet,
    one of those is not a feature line, it is the whole task.

    Measured on run-df4dc6f5's `sprint_1_summary.md`, live. Two delegated tasks
    produced a "Features Implemented" section of 18 lines in which the second
    task began inside the first one's criteria list, because that list is
    written with `-` and Markdown had no reason to think otherwise. Nothing was
    wrong with the data; a reader simply could not see two features in it.

    The full text is not lost - it is what `docs/milestone_plan.md` is for. This
    document answers "what did this sprint do", and that is a list.
    """
    first = ""
    for line in str(text).splitlines():
        stripped = line.strip()
        if stripped:
            first = " ".join(stripped.split())
            break
    if len(first) <= LONGEST_FEATURE_LINE:
        return first
    # At a sentence end if there is one in range, so the line is a whole
    # thought rather than a word count.
    window = first[: LONGEST_FEATURE_LINE + 1]
    cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
    if cut > LONGEST_FEATURE_LINE // 3:
        return first[: cut + 1]
    # No sentence end in range: cut on a word boundary if there is one, and mark
    # the cut either way. A truncation with no marker reads as the whole text.
    if " " in window:
        window = window[: window.rfind(" ")]
    return window.rstrip(" ,;:") + "\u2026"


def render_sprint_summary(
    *,
    sprint_number: int,
    total_sprints: int,
    goal: str,
    planned: Sequence[str],
    attempts: Sequence[Mapping[str, Any]],
) -> str:
    """The whole document for one sprint, from every attempt recorded at it.

    Regenerated from the attempt list rather than appended to on disk, so the
    headline figures always describe the sprint as it now stands and cannot
    drift from the history under them. The attempt list is the state; this is a
    rendering of it.

    Each attempt is a mapping with `number`, `status`, `reason`, `cases`
    (`count_test_cases`'s shape or None), `rounds`, `features` and `defects`.
    An unknown key is ignored and a missing one reads as absent, because this
    runs at the end of a sprint that has already been decided and must not be
    the thing that fails it.
    """
    attempts = list(attempts or ())
    latest: Mapping[str, Any] = attempts[-1] if attempts else {}
    tally = _defect_tally(latest.get("defects") or ())
    cases = latest.get("cases")

    of_plan = f" of {total_sprints}" if total_sprints else ""
    lines = [f"# Sprint {sprint_number}{of_plan} Summary", ""]
    lines.append(f"**Goal:** {goal or 'Unknown goal'}")
    lines.append(f"**Status:** {latest.get('status', 'Unknown')}")

    # Why the run worked through more milestones than the plan has sprints.
    # Stated on every sprint, including the ones that took a single attempt, so
    # its absence never has to be interpreted.
    attempt_count = len(attempts) or 1
    if attempt_count > 1:
        failures = sum(1 for attempt in attempts if attempt.get("status") != "Completed")
        lines.append(
            f"**Attempts:** {attempt_count} (re-run after {failures} failed "
            f"attempt{'s' if failures != 1 else ''} at this same sprint)"
        )
    else:
        lines.append("**Attempts:** 1 (no re-run)")

    if latest.get("reason"):
        lines.append(f"**Failure Reason:** {latest['reason']}")

    lines.append(f"**Test Cases:** {cases['tests'] if cases else 'not reported'}")
    lines.append(f"- **Passed:** {cases['passed'] if cases else 0}")
    lines.append(f"- **Failed:** {cases['failed'] if cases else 0}")

    lines += ["", "## Planned for This Sprint", _bullets(planned, empty="Nothing recorded from the sprint plan.")]
    lines += ["", "## Features Implemented"]
    # These are the tasks the milestone delegated, which is what the state
    # carries; nothing records per-task completion. On a sprint that passed its
    # review that reads correctly enough. On one that failed it does not, and
    # this is the document a reader opens to find out what happened.
    #
    # Measured on run-e980310b, which failed its first sprint with
    # `index.html references style.css which does not exist` as a blocking
    # finding, while this section read "Create style.css with basic responsive
    # CSS rules". The heading is the one the dashboards parse, so the
    # qualification goes in the body rather than the heading, and not as a
    # bullet - the UI keeps only the lines that start with one.
    if str(latest.get("status", "")).strip().lower() != "completed":
        lines.append(
            "These are the tasks this sprint delegated, not a record of what "
            "passed: the sprint did not pass its review, so read them as what "
            "was attempted."
        )
    lines.append(
        _bullets(
            [_one_line(feature) for feature in (latest.get("features") or ())],
            empty="No delegated work recorded.",
        )
    )

    lines += ["", "## Test Cycles",
              f"- **Rounds Completed:** {latest.get('rounds', 0)}",
              f"- **Total Bugs Found:** {tally['found']}",
              f"- **Bugs Fixed:** {tally['fixed']}",
              f"- **Bugs Open:** {tally['open']}"]

    defects = latest.get("defects") or ()
    if defects:
        lines += ["", "### Defect Summary"]
        for defect in defects:
            status = str(defect.get("status", "open")).upper()
            lines.append(
                f"- [{status}] {defect.get('description', '')} "
                f"(Owner: {defect.get('owner', 'unassigned')})"
            )

    if attempt_count > 1:
        lines += ["", "## Attempt History",
                  "Every attempt at *this* sprint, oldest first. A re-run is a "
                  "second attempt at one sprint, not an extra sprint."]
        for attempt in attempts:
            label = "re-run" if attempt.get("number", 1) > 1 else "first attempt"
            reason = f": {attempt['reason']}" if attempt.get("reason") else ""
            lines.append(
                f"- **Attempt {attempt.get('number', '?')}** ({label}) - "
                f"{attempt.get('status', 'Unknown')}{reason}. "
                f"Test cases: {_cases_phrase(attempt.get('cases'))} over "
                f"{attempt.get('rounds', 0)} round(s). "
                f"Defects: {_defect_tally(attempt.get('defects') or ())['found']} found, "
                f"{_defect_tally(attempt.get('defects') or ())['fixed']} fixed."
            )

    return "\n".join(lines) + "\n"


__all__ = ["count_test_cases", "render_sprint_summary"]
