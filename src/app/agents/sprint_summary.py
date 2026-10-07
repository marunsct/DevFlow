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


def last_test_run(
    entries: Iterable[Mapping[str, Any]], *, since: str | None = None
) -> Mapping[str, Any] | None:
    """The last ledger entry in the window whose runner reported counts.

    One selection rule, shared. `count_test_cases` returns only the three counts,
    which is all the summary prints - but a caller that has to decide whether the
    suite passed also needs the exit code, and two separate searches for "the
    last test run" is how a gate and a report start disagreeing about which run
    they are talking about.
    """
    latest: Mapping[str, Any] | None = None
    for entry in entries or ():
        if not _is_a_test_run(entry):
            continue
        at = entry.get("at")
        if since and isinstance(at, str) and at < since:
            continue
        latest = entry
    return latest


def a_suite_that_did_not_pass(entry: Mapping[str, Any] | None) -> bool:
    """Whether a recorded test run failed, by the only evidence that cannot lie.

    `failed > 0` is not the whole question. A composite test command runs more
    than one runner - `npm test` chaining `node --test` and `playwright test` is
    the shape this harness sees most - and `_RUNNER_TOTALS` parses the summary
    line it recognises, which is the first runner's. If a later runner fails, the
    counts say the suite is green and the exit code says the command failed.

    Measured on one run, which completed. Its ledger holds six entries with
    counts and a non-zero exit code, five of them reading

        npm test   tests=27  passed=27  failed=0  returncode=1

    A gate that reads `failed` alone is silent on all five, which is the false
    green it exists to prevent reached by another route.

    An entry with no exit code recorded is not evidence of failure: older entries
    predate the field, and a run nobody measured must not be failed for it.
    """
    if not entry:
        return False
    if int(entry.get("failed") or 0) > 0:
        return True
    code = entry.get("returncode")
    return isinstance(code, int) and code != 0


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
    latest = last_test_run(entries, since=since)
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

    Measured on one run's `sprint_1_summary.md`, live. Two delegated tasks
    produced a "Features Implemented" section of 18 lines in which the second
    task began inside the first one's criteria list, because that list is
    written with `-` and Markdown had no reason to think otherwise. Nothing was
    wrong with the data; a reader simply could not see two features in it.

    The full text is not lost - it is what `docs/milestone_plan.md` is for. This
    document answers "what did this sprint do", and that is a list.
    """
    meaningful = [
        " ".join(stripped.split())
        for line in str(text).splitlines()
        if (stripped := line.strip())
    ]
    first = meaningful[0] if meaningful else ""
    # A line ending in a colon announces a list instead of naming anything, so
    # on its own it is not a feature. Carry on into what it introduces.
    #
    # Measured on one run's `sprint_1_summary.md`, live: two of its three
    # "Features Implemented" bullets read "Create the following changes in two
    # files:" and "Create changes to two files:". Both were the first non-blank
    # line of a task, and neither said which files or what changed.
    #
    # Appended rather than skipped, because a colon does not always mean an
    # empty preamble - "Wire filter buttons in init():" names the thing it is
    # about. Joining keeps that one whole and repairs the other, and the length
    # rules below then apply to the result exactly as before.
    if first.endswith(":") and len(meaningful) > 1:
        first = f"{first} {meaningful[1]}"
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
    attempt_count = len(attempts) or 1

    # Why the run worked through more milestones than the plan has sprints.
    # Stated on every sprint, including the ones that took a single attempt, so
    # its absence never has to be interpreted.
    if attempt_count > 1:
        # The attempts *before* this one. `latest` is `attempts[-1]`, so counting
        # every non-Completed attempt counted the current one among the failures
        # that preceded it - and "re-run after N failed attempts" means N came
        # first. Wrong exactly when this attempt also failed, which is the case a
        # reader most needs right: one run's second and final attempt read
        # "Attempts: 2 (re-run after 2 failed attempts at this same sprint)" with
        # one attempt behind it.
        failures = sum(1 for attempt in attempts[:-1] if attempt.get("status") != "Completed")
        attempts_line = (
            f"{attempt_count} (re-run after {failures} failed "
            f"attempt{'s' if failures != 1 else ''} at this same sprint)"
        )
    else:
        attempts_line = "1 (no re-run)"
    # Revised after a milestone review is not re-run, and not nothing either:
    # one run's sprint was sent back once and its summary read "no re-run" alone.
    revisions = int(latest.get("revisions") or 0)
    if revisions:
        attempts_line = (
            f"{attempts_line[:-1]}; revised {revisions} time{'s' if revisions != 1 else ''} "
            "after the milestone review)"
        )

    history: list[str] = []
    if attempt_count > 1:
        for attempt in attempts:
            label = "re-run" if attempt.get("number", 1) > 1 else "first attempt"
            reason = f": {attempt['reason']}" if attempt.get("reason") else ""
            if attempt.get("accepted_at_escalation"):
                reason += f" at escalation ({attempt['accepted_at_escalation']})"
            tally = _defect_tally(attempt.get("defects") or ())
            history.append(
                f"**Attempt {attempt.get('number', '?')}** ({label}) - "
                f"{attempt.get('status', 'Unknown')}{reason}. "
                f"Test cases: {_cases_phrase(attempt.get('cases'))} over "
                f"{attempt.get('rounds', 0)} round(s). "
                f"Defects: {tally['found']} found, {tally['fixed']} fixed."
            )

    from app.doc_templates import render_document

    # The layout is the template's (`app/doc_templates/templates/sprint_summary.md.j2`).
    # The "Features Implemented" qualification for a sprint that did not pass
    # goes in the body rather than the heading, and not as a bullet - the panel
    # keeps only the lines that start with one. Measured on one run, which
    # failed its first sprint with `index.html references style.css which does
    # not exist` while this section read "Create style.css with basic
    # responsive CSS rules".
    return render_document(
        "sprint_summary",
        number=sprint_number,
        of_plan=f" of {total_sprints}" if total_sprints else "",
        goal=goal,
        status=latest.get("status", "Unknown"),
        deferred=list(latest.get("deferred") or ()),
        completed=str(latest.get("status", "")).strip().lower() == "completed",
        attempts_line=attempts_line,
        reason=latest.get("reason") or "",
        accepted_at_escalation=latest.get("accepted_at_escalation") or "",
        cases=latest.get("cases"),
        planned=[str(item).strip() for item in planned or () if str(item).strip()],
        features=[_one_line(feature) for feature in (latest.get("features") or ())],
        rounds=latest.get("rounds", 0),
        tally=_defect_tally(latest.get("defects") or ()),
        defects=list(latest.get("defects") or ()),
        history=history,
        work_orders=list(latest.get("work_orders") or ()),
        defect_log=list(latest.get("defect_log") or ()),
        findings=list(latest.get("findings") or ()),
        carried_forward=list(latest.get("carried_forward") or ()),
        lessons=list(latest.get("lessons") or ()),
    )


__all__ = [
    "a_suite_that_did_not_pass",
    "count_test_cases",
    "last_test_run",
    "render_sprint_summary",
]
