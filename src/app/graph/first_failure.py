"""A fixer is shown what its criterion's tests do now, run apart from the rest of the suite, and what they do after each
change it keeps; a server error nothing logged is the first thing it fixes; a test no fix of this sprint can make pass
goes to the QA lead first (plan FX.1, FX.7, FX.11; LF.1410, LF.1411, LF.1413).

Measured on a medium run, where two fixers spent 46 minutes on one criterion and changed nothing:

- **Stale evidence (FX.7).** A criterion's brief said three of its tests received 429 and 404. Run on their own they
  received 500 and 404: the 429s came from a sign-up limit that the whole suite's earlier tests had used up, not from
  the code under test. Before a fixer is shown a criterion, the harness runs the files holding that criterion's tests
  on their own (`per_file`, the run the dispatch-time re-measure already made of this same product, so usually no run
  at all) and shows the first failure and the server's error from that run. After each write the fixer keeps, the
  check that already runs the defect's tests (`verify_after_write`) returns the first failure and any server error in
  at most `MOST_SHOWN` characters, in place of "they still fail".
- **No logged cause (FX.1).** Every registration answered 500 and the server's log held only access lines: the product
  caught its own exceptions and answered without logging them. No fixer was shown the exception, none reproduced it,
  and the lookup for a stuck defect had no error to search. When a failing test received a server error (5xx), or lost
  its connection, and neither the run on its own nor the suite's last run logged an error, the fixer is told so and
  asked for one thing first: make the code that answers the error log the exception with its trace, then run the
  failing test. The check after each kept write reads the server's log again and shows the trace it finds.
- **Tests no fixer can close (FX.11).** Three of the criterion's tests call a route that only a later sprint's
  criteria name (the product answered 404), and two met the specification's own sign-up limit. Before a fixer is sent,
  such a test - one that, run on its own, received 404 or 405 at a route only later criteria name, or 429 under a limit
  the specification sets - is held as a dispute for the QA lead (the existing dispute path, once per attempt); the
  fixer that follows is told those tests are not its to make pass.

Nothing here names a language, a framework or a runner: the files are run as the suite's own command runs them, the
status is read from what the test printed, and the server's log is what the run already captures. Never raises.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: Characters of the result a fixer is shown, before it starts and after each kept write.
MOST_SHOWN = 1_500
#: Characters of the first failure's own message within that.
MOST_MESSAGE = 700
#: How the run on its own is headed in a fix request.
HEADING = "--- Its tests, run on their own just now, on the product as it is ---"
#: How a server error with no logged cause is headed in a fix request.
UNLOGGED_HEADING = "--- The server error behind this failure is not logged ---"
#: The status a test received, as runners print it: `Received: 500`, `got 404`, `status 429`, `assert 500 == 201`,
#: `500 Internal Server Error`.
_RECEIVED = re.compile(
    r"(?:\b(?:Received|received|got|returned|actual)\b[^\d\n]{0,20}?|\bstatus(?:[ _]code)?\b[^\d\n]{0,12}?"
    r"|\bassert\s+)([1-5]\d\d)\b(?!\.\d)"
    r"|\b([1-5]\d\d)\s+(?:Internal Server Error|Not Found|Method Not Allowed|Too Many Requests|Bad Gateway"
    r"|Service Unavailable|Gateway Timeout)\b")
#: A test that lost its connection to the product: the process died under it.
_CONNECTION_LOST = re.compile(r"ECONNREFUSED|ECONNRESET|socket hang up|[Cc]onnection (?:refused|reset|aborted)"
                              r"|RemoteDisconnected|[Ss]erver disconnected")
#: Statuses that say the product does not serve a route at all.
_NOT_SERVED = (404, 405)
#: The status that says a limit stopped the request.
_LIMITED = 429
#: A limit a specification sets on requests: a rate, a count per period, or the status that enforces it.
_A_LIMIT = re.compile(r"\b429\b|\brate[- ]?limit|\btoo many requests\b|\brequests? per\b|\bper (?:minute|hour|second)\b",
                      re.I)


def received(message: str) -> int | None:
    """The status a failing test received, read from what it printed; None when it states none."""
    found = _RECEIVED.search(str(message or ""))
    return int(found.group(1) or found.group(2)) if found else None


def _its_criteria(defect: Any) -> set[str]:
    """The criterion and change-request ids a failing criterion's defect is about; none for a unit-test defect."""
    from app.acceptance.junit import tags_in
    from app.graph.workflow import UNIT_TESTS_FAIL

    description = str(getattr(defect, "description", "") or "")
    if description.startswith(UNIT_TESTS_FAIL):
        return set()
    return {t for t in tags_in(description) if t.startswith(("AC-", "CR-"))}


def run_alone(root: str | Path | None, defect: Any) -> list[dict[str, Any]] | None:
    """Each file holding the defect's criterion's tests, run on its own as the suite runs it, with its tests and what
    the server logged; None for a defect about no criterion, or when nothing could run. A file of this same product
    already run - at dispatch, or by the check after a write - is read from that run, not run again."""
    criteria = _its_criteria(defect)
    if not root or not criteria:
        return None
    try:
        from app.acceptance import per_file
        from app.stacks import contract
        from app.stacks.scaffold import sandbox_runner

        # What the suite's own run does first, as the check after a write does: the harness's files put back.
        contract.enforce(root)
        runs = per_file.each_file(root, contract.read(root) or {}, sandbox_runner(root), naming=criteria,
                                  with_tests=True)
        return runs or None
    except Exception:  # noqa: BLE001 - the fixer is shown what was measured before
        logger.debug("Could not run a criterion's tests on their own", exc_info=True)
        return None


def _failing(runs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for run in runs for t in run.get("tests") or [] if t.get("outcome") == "failed"]


def _tests(runs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for run in runs for t in run.get("tests") or []]


def _the_server_error(runs: Sequence[dict[str, Any]], logged_before: str = "") -> str:
    """The error the server printed in these runs, else in the suite's last run; "" for none."""
    from app.acceptance.what_went_wrong import what_the_server_printed

    for log in [*(str(run.get("server_log") or "") for run in runs), str(logged_before or "")]:
        said = what_the_server_printed(log)
        if said:
            return said
    return ""


def _a_server_error_received(test: dict[str, Any]) -> str:
    """How `test` met a server error - "received 500", "lost its connection" - or ""."""
    message = str(test.get("message") or "")
    status = received(message)
    if status is not None and 500 <= status <= 599:
        return f"received {status}"
    if _CONNECTION_LOST.search(message):
        return "lost its connection to the product"
    return ""


def unlogged(runs: Sequence[dict[str, Any]] | None, logged_before: str = "") -> tuple[str, str] | None:
    """(the test's name, how it met the error) for the first failing test that met a server error no log explains;
    None when none did, or the server logged an error in these runs or in the suite's last run (`logged_before`).

    An access line - a request answered 500 - states no cause (`what_went_wrong.states_a_cause`): measured on a medium
    run, five of them were the whole saved log, and read as "the server logged something" they silenced this."""
    from app.acceptance.what_went_wrong import states_a_cause

    for test in _failing(runs or ()):
        how = _a_server_error_received(test)
        if how:
            logs = [*(str(run.get("server_log") or "") for run in runs or ()), str(logged_before or "")]
            return None if any(states_a_cause(log) for log in logs) else (str(test.get("name") or ""), how)
    return None


def unlogged_section(name: str, how: str, where: Sequence[tuple[str, int]] = ()) -> str:
    """What a fixer is told first when a server error has no logged cause; `where`, the product's lines that answer a
    server error from a handler that logs nothing (`acceptance_nodes.where_errors_become_5xx`)."""
    named = (" It is answered here, from a handler that logs nothing: "
             + "; ".join(f"`{path}` line {line}" for path, line in where) + ".") if where else ""
    return (
        f"\n{UNLOGGED_HEADING}\n"
        f"`{name}` {how}, and the product's server log states no error for it: the code that answers this error does "
        "not log its cause, so neither you nor the harness can see why it fails. Do this first: where the product "
        "catches the exception and answers with the server error, log the exception with its full trace, in the "
        "product's own logging. Then run the failing test and read the trace the server prints; that error, not a "
        "guess, is what you fix. After each change you keep, the harness reads the server's log again and shows you "
        f"the error it finds.{named}\n"
    )


def _shown(text: str, most: int) -> str:
    from app.acceptance.what_went_wrong import shown

    return "\n".join(line for line in shown(text, most).splitlines() if line.strip()) or "(it printed nothing)"


def _in_a_line(message: str) -> str:
    from app.acceptance.failure_said import what_it_said

    return " ".join((what_it_said(message) or "failed").split())[:200]


def result(runs: Sequence[dict[str, Any]] | None, logged_before: str = "", *, most: int = MOST_SHOWN) -> str:
    """The first failure of these runs with its message, the server's error, and each other failure in a line, within
    `most` characters; "" when no test of the criterion ran."""
    tests = _tests(runs or ())
    if not tests:
        return ""
    failing = _failing(runs or ())
    if not failing:
        return f"All {len(tests)} of its tests pass."
    first, others = failing[0], failing[1:]
    lines = [f"{len(failing)} of its {len(tests)} tests fail. The first: `{first.get('name')}`",
             _shown(str(first.get("message") or ""), MOST_MESSAGE)]
    error = _the_server_error(runs or (), logged_before)
    if error:
        lines.append(f"The server printed: {error}")
    text = "\n".join(lines)
    for shown, test in enumerate(others):
        line = f"\n- `{test.get('name')}`: {_in_a_line(str(test.get('message') or ''))}"
        if len(text) + len(line) > most - 40:
            text += f"\n- and {len(others) - shown} more."
            break
        text += line
    return text[:most]


# --- FX.11: tests no fix in this sprint can make pass ------------------------------------------------------------------


def _a_later_route(root: str | Path, body: str) -> str:
    """The resource `body` calls that only criteria a later sprint delivers name - none due now - or ""."""
    from app.acceptance import sprint_scope, suite
    from app.graph.fixer_request_shape import _words_of, routes_called

    later = set(sprint_scope.not_yet_due(root))
    if not later:
        return ""
    texts = {c.id: str(c.text or "").lower() for c in suite.criteria(root)}
    for resource in sorted(routes_called([body])):
        words = _words_of([resource])
        if not words:
            continue

        def names(text: str) -> bool:
            return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text) for w in words)

        if any(names(text) for tag, text in texts.items() if tag in later) and not any(
                names(text) for tag, text in texts.items() if tag not in later):
            return resource
    return ""


def held_for_the_lead(root: str | Path | None, runs: Sequence[dict[str, Any]] | None,
                      specification: str = "") -> list[tuple[str, str]]:
    """(test, why) for each failing test of these runs - its criterion's tests run on their own - that no fix in this
    sprint can make pass: one that received 404 or 405 at a route only a later sprint's criteria name, or 429 under a
    limit the specification sets. [] when none, or when nothing ran on its own."""
    if not root or not runs:
        return []
    held: list[tuple[str, str]] = []
    try:
        from app.acceptance.sprint_scope import _declared_with_bodies

        bodies = {title: body for _, title, body in _declared_with_bodies(root)}
        limited = bool(_A_LIMIT.search(str(specification or "")))
        for test in _failing(runs):
            name = str(test.get("name") or "")
            status = received(str(test.get("message") or ""))
            if status in _NOT_SERVED:
                body = bodies.get(name) or next((b for t, b in bodies.items() if t and t in name), "")
                route = _a_later_route(root, body)
                if route:
                    held.append((name, f"it calls `{route}`, which only criteria a later sprint delivers name, and "
                                       f"the product does not serve it yet (it answered {status})"))
                    continue
            if status == _LIMITED and limited:
                held.append((name, "run on its own it still received 429: a limit the specification sets stops it, "
                                   "whatever the code under test does"))
    except Exception:  # noqa: BLE001 - every test goes to the fixer, as before
        logger.debug("Could not tell which failing tests no fix can make pass", exc_info=True)
        return []
    return held


def dispute_reason(defect: Any, held: Sequence[tuple[str, str]]) -> str:
    """Why the QA lead is asked before this defect's fixer is sent."""
    criteria = ", ".join(sorted(_its_criteria(defect))) or "this criterion"
    return (f"Before a fixer was sent to {criteria}, the harness ran its tests on their own and found failing tests "
            "no fix in this sprint can make pass: "
            + "; ".join(f"`{name}`: {why}" for name, why in held)
            + ". Judge whether each can pass for a product that meets its criterion in this sprint.")


def _the_specification_text(state: Any) -> str:
    try:
        from app.agents.specification_rulings import _the_specification

        return "\n".join((_the_specification(state.get("technical_specification"), state["repository"].root_path),
                          getattr(state.get("document"), "text", "") or ""))
    except Exception:  # noqa: BLE001 - no limit is read
        return ""


def held_as_a_dispute(state: Any, cycle: Any, index: int) -> dict[str, Any] | None:
    """The update holding a dispute for the QA lead before defect `index`'s fixer is sent, when its criterion's tests,
    run on their own, include one no fix in this sprint can make pass and a dispute may be held now; else None.

    The defect is not passed over: after the dispute the round comes back to it, and its fixer is told which tests
    were held. Never raises."""
    try:
        if state.get("pending_inner_thread_id") or state.get("fix_batch"):
            return None
        defect = cycle.defects[index]
        if not _its_criteria(defect):
            return None
        from app.graph.workflow import _a_dispute_may_be_held_now, _handing_on

        if not _a_dispute_may_be_held_now(state):
            return None
        root = state["repository"].root_path
        held = held_for_the_lead(root, run_alone(root, defect), _the_specification_text(state))
        if not held:
            return None
        stage = f"defect_fix_{state.get('test_round', 0)}_{index}"
        from app.observability import defect_ledger

        defect_ledger.note("held for the lead", stage, defect=defect, round_=state.get("test_round", 0), index=index,
                           sprint=state.get("current_sprint_index", 0),
                           detail="; ".join(f"{name}: {why}" for name, why in held))
        logger.warning("Defect '%s': %d failing test(s) no fix in this sprint can make pass; the QA lead judges them "
                       "before its fixer is sent", str(defect.description)[:80], len(held))
        return _handing_on(stage="acceptance_dispute", dispute_returns_to="test_and_triage", fix_base_commit="",
                           dispute_reason=dispute_reason(defect, held))
    except Exception:  # noqa: BLE001 - the fixer is sent, as before
        logger.debug("Could not hold a dispute before a fixer", exc_info=True)
        return None


# --- what a fixer is shown ------------------------------------------------------------------------------------------


def for_a_fixer(state: Any, defect: Any) -> str:
    """The run on its own of the defect's criterion's tests, the server error nothing logged, and the tests held for
    the QA lead, as its fix request carries them; "" for a defect about no criterion, or when nothing ran."""
    try:
        root = state["repository"].root_path
        runs = run_alone(root, defect)
        said = result(runs, _the_latest_log(root))
        if not said:
            return ""
        text = (f"\n{HEADING}\n"
                "The harness ran the files holding this defect's tests apart from the rest of the suite. Where this "
                "differs from the suite's run above, this is how the product behaves now; the difference came from "
                f"the other tests of that run - their order or the state they shared.\n{said}\n")
        held = held_for_the_lead(root, runs, _the_specification_text(state))
        if held:
            text += ("Not yours to make pass in this sprint - held for the QA lead:\n"
                     + "\n".join(f"- `{name}`: {why}" for name, why in held) + "\n")
        found = unlogged(runs, _the_latest_log(root))
        if not found:
            return text
        from app.graph import acceptance_nodes, fresh_evidence

        # Said once: the defect's own account may say the handler hid the cause already, with the lines.
        if acceptance_nodes.THE_SERVER_HID_THE_CAUSE[:60] in fresh_evidence.actual_behavior_now(root, defect):
            return text
        return text + unlogged_section(*found, where=acceptance_nodes.where_errors_become_5xx(root))
    except Exception:  # noqa: BLE001 - the request goes without it
        logger.debug("Could not show a criterion's tests run on their own", exc_info=True)
        return ""


def _the_latest_log(root: str | Path) -> str:
    """What the server logged in the suite's latest measurement of this product; ""."""
    from app.graph import fresh_evidence

    saved = fresh_evidence.latest(root) or {}
    return str(saved.get("server_log") or "")


def after_a_write(root: str | Path, defect: Any) -> str:
    """After a kept write whose check found the defect's tests still failing: their first failure now and the server's
    error, within `MOST_SHOWN`, or that the server still logs none; "" for a defect about no criterion."""
    runs = run_alone(root, defect)
    said = result(runs, most=MOST_SHOWN - 200)
    if not said:
        return ""
    found = unlogged(runs)
    if found:
        said += f"\nThe server still logs no error for `{found[0]}`: log the exception where it is answered."
    return said[:MOST_SHOWN]


__all__ = [
    "HEADING", "MOST_SHOWN", "UNLOGGED_HEADING", "after_a_write", "dispute_reason", "for_a_fixer",
    "held_as_a_dispute", "held_for_the_lead", "received", "result", "run_alone", "unlogged", "unlogged_section",
]
