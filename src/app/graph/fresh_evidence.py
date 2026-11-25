"""What a fixer is shown of its defect comes from the latest measurement of the product as it is (LF.1270, review 2.6).

Measured on a medium run (27 fix stages): six fixers were shown a server log from a measurement up to ten hours old,
and a revert story about a start fault that was already fixed. A defect keeps the actual behaviour of the round that
raised it; one the next rounds do not raise again - past a round's cap for one source, or carried over - keeps it for
hours, and each fixer read it as what the product does now.

Each time a defect is shown to a fixer (`as_shown`), its actual behaviour is read against the latest measurement:

- what the server logged is the latest measurement's; the older log is dropped, not kept beside it;
- the line a failing criterion's defect opens with - its failed tests, each with its first line - is the latest
  measurement's;
- a revert note about a start that failed is dropped once the latest measurement finds the product starting.

The latest measurement counts only while it is of the product as it is now (its fingerprint, `unstable.fingerprint`):
after a reverted fix it describes a product that is gone, and the stored text stands as it was. The defect itself
keeps what it stored: the revert tallies and the disputes read it. Never raises.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: A failing criterion's own defect, as the round raises it (`acceptance_nodes.failing_due_defects`).
_A_CRITERION_S_DEFECT = re.compile(r"^\[((?:AC|CR)-[\w.-]+)\] .*? - the acceptance suite says this does not work yet\.",
                                   re.S)
#: A revert note's line, alone or in a batch, and what it names.
_A_REVERT_LINE = re.compile(
    r"\n?^(?:A fix was tried and reverted, because it broke what passed before it: (.+?)\."
    r"|A batch of fixes including this one was reverted, because together they broke what passed before them: (.+?)\."
    r" It is fixed on its own next\.)[ \t]*$", re.M)
#: How a revert names a start that failed (`engineering.after_a_fix`).
START_FAILURES = (
    "the product no longer builds or starts", "the product did not start before this fix either",
    "the product no longer starts the way its user starts it",
)


def _plain(value: Any) -> str:
    return str(value or "")


def latest(root: str | Path | None) -> dict[str, Any] | None:
    """The latest saved measurement of the acceptance suite when it is of the product as it is now; else None."""
    if not root:
        return None
    try:
        from app.acceptance import suite

        saved = suite.last_result(root)
        if not saved:
            return None
        recorded = str(saved.get("fingerprint") or "")
        if recorded:
            from app.acceptance.unstable import fingerprint

            now = fingerprint(root)
            if now and now != recorded:
                return None
        return saved
    except Exception:  # noqa: BLE001 - the stored text stands
        logger.debug("Could not read the latest measurement", exc_info=True)
        return None


def _the_log_in(saved: dict[str, Any]) -> str:
    from app.acceptance.suite import what_the_server_logged

    return _plain(saved.get("server_log")) or what_the_server_logged(_plain(saved.get("output")))


def _ends_of_a_log_block() -> tuple[str, ...]:
    """What a failing criterion's defect may carry after its server log, each where the log ends."""
    from app.graph import acceptance_nodes
    from app.stacks.known_errors import KNOWN_CAUSE

    return ("\n" + acceptance_nodes.THE_PAGE_REPORTED_WHILE_LOADING, acceptance_nodes.WHAT_THE_PRODUCT_SHOWS,
            # As a defect raised before LF.1458 stored it, at the end of a line.
            " " + acceptance_nodes.PRODUCT_SHOWS_LABEL,
            "\nA fix was tried and reverted", "\nA batch of fixes including this one", "\nFixes of this defect reverted",
            "\nIf the behaviour this sprint delivers", "\nThe product before this fix passed", "\n" + KNOWN_CAUSE,
            acceptance_nodes.THE_SERVER_HID_THE_CAUSE[:60])


def with_the_log_now(text: str, root: str | Path, logged: str, *, add: bool = False) -> str:
    """`text` with the server log it carries replaced by `logged`'s block, or dropped when `logged` is empty; with
    `add`, a text that carries none gets `logged`'s block before what follows a log."""
    from app.graph import acceptance_nodes

    heading = "\n" + acceptance_nodes.SERVER_LOG_HEADING + "\n"
    block = acceptance_nodes.server_log_block(root, logged)
    at = text.find(heading)
    ends = _ends_of_a_log_block()
    if at < 0:
        if not (add and block):
            return text
        found = [i for i in (text.find(end) for end in ends) if i >= 0]
        cut = min(found) if found else len(text)
        return text[:cut] + block + text[cut:]
    after = at + len(heading)
    found = [i for i in (text.find(end, after) for end in ends) if i >= 0]
    end = min(found) if found else len(text)
    return text[:at] + block + text[end:]


def without_a_hidden_cause_since_logged(text: str, logged: str) -> str:
    """`text` less the note that the server hid a 5xx's cause, once the latest measurement's log states one (LF.1410);
    `text` as it is while the log states none."""
    from app.acceptance.what_went_wrong import states_a_cause
    from app.graph import acceptance_nodes

    if acceptance_nodes.THE_SERVER_HID_THE_CAUSE not in text or not states_a_cause(logged):
        return text
    return re.sub(re.escape(acceptance_nodes.THE_SERVER_HID_THE_CAUSE) + r"(?: It is answered here[^\n]*)?", "", text)


def _the_product_starts_now(root: str | Path) -> bool:
    """Whether the latest measurement the fix guard keeps found the product starting."""
    try:
        from app import ci

        latest_snapshot = ci.load(root, "latest")
        return latest_snapshot is not None and bool(latest_snapshot.acceptance_ran) and not latest_snapshot.problem
    except Exception:  # noqa: BLE001 - the note stands
        return False


def without_a_start_fault_since_gone(text: str, root: str | Path) -> str:
    """`text` less the revert notes for a start that failed (every test after it broke only because none ran), when
    the product starts now."""
    def only_the_start(match: re.Match[str]) -> bool:
        # A start that failed is named first, and every test after it broke only because none could run.
        return (match.group(1) or match.group(2) or "").strip().startswith(START_FAILURES)

    if not any(only_the_start(m) for m in _A_REVERT_LINE.finditer(text)) or not _the_product_starts_now(root):
        return text
    return _A_REVERT_LINE.sub(lambda m: "" if only_the_start(m) else m.group(0), text)


def _stopped_at_a_shared_step(others: Iterable[Any]) -> set[str]:
    """The tests an open defect for one step many tests stop at holds as its evidence."""
    from app.graph.acceptance_nodes import ONE_CAUSE_MARK

    return {
        _plain(item.get("test")) for other in others or ()
        if getattr(other, "status", "open") == "open" and ONE_CAUSE_MARK in _plain(getattr(other, "description", ""))
        for item in getattr(other, "evidence", None) or [] if isinstance(item, dict) and item.get("test")
    }


def with_the_tests_now(text: str, defect: Any, saved: dict[str, Any], others: Iterable[Any] = ()) -> str:
    """A failing criterion's defect's opening line, its failed tests and their first lines, as the latest measurement
    found them; `text` as it is for any other defect, or when that measurement found none of its tests failing."""
    found = _A_CRITERION_S_DEFECT.match(_plain(getattr(defect, "description", "")))
    if not found:
        return text
    tag = found.group(1)
    entry = (saved.get("criteria") or {}).get(tag) or (saved.get("change_requests") or {}).get(tag) or {}
    tests = [t for t in entry.get("tests") or [] if isinstance(t, dict)]
    failed = [t for t in tests if t.get("outcome") == "failed"]
    if not failed:
        return text
    first, newline, rest = text.partition("\n")
    from app.graph.acceptance_nodes import PRODUCT_SHOWS_LABEL, the_failed_tests_line

    # Only the failed-tests sentence is replaced (LF.1458): a label stored at the end of that line - the page at load,
    # before any test - is kept, or the tree after it reads as the page the test failed on.
    labelled = first.find(" " + PRODUCT_SHOWS_LABEL)
    first, kept = (first[:labelled], first[labelled:]) if labelled >= 0 else (first, "")
    names = {_plain(t.get("name")) for t in tests}
    if not (first == "no test carrying this id ran" or any(first.startswith(f"{name}: ") for name in names if name)):
        return text
    stopped = _stopped_at_a_shared_step(others)
    failed = [t for t in failed if _plain(t.get("name")) not in stopped] or failed

    return the_failed_tests_line(failed) + ("\n" + kept.lstrip() if kept else "") + newline + rest


def actual_behavior_now(root: str | Path | None, defect: Any, others: Iterable[Any] = ()) -> str:
    """The defect's actual behaviour as a fixer is shown it: read against the latest measurement. Never raises."""
    text = _plain(getattr(defect, "actual_behavior", ""))
    if not root:
        return text
    try:
        text = without_a_start_fault_since_gone(text, root)
        saved = latest(root)
        if saved is None:
            return text
        text = with_the_tests_now(text, defect, saved, others)
        criterion = bool(_A_CRITERION_S_DEFECT.match(_plain(getattr(defect, "description", ""))))
        logged = _the_log_in(saved)
        return without_a_hidden_cause_since_logged(with_the_log_now(text, root, logged, add=criterion), logged)
    except Exception:  # noqa: BLE001 - the stored text stands
        logger.debug("Could not read a defect against the latest measurement", exc_info=True)
        return _plain(getattr(defect, "actual_behavior", ""))


def as_shown(root: str | Path | None, defect: Any, others: Iterable[Any] = ()) -> Any:
    """`defect` as a fixer is shown it (`actual_behavior_now`); the defect itself when nothing changed."""
    now = actual_behavior_now(root, defect, others)
    if now == _plain(getattr(defect, "actual_behavior", "")):
        return defect
    try:
        return defect.model_copy(update={"actual_behavior": now})
    except Exception:  # noqa: BLE001 - not a model: shown as it is
        return defect


def what_its_tests_printed_now(root: str | Path | None, defect: Any) -> dict[str, str] | None:
    """For a defect whose evidence names failing tests and whose description names no criterion - one raised for a
    step many tests stop at - those tests as the latest measurement found them, with what each printed; else None.

    Measured on a medium run: such a defect names no criterion, so its fixer was shown the last failing command, which
    may be another stage's, from another measurement.
    """
    try:
        from app.acceptance.junit import tags_in

        if [t for t in tags_in(_plain(getattr(defect, "description", ""))) if t.startswith(("AC-", "CR-"))]:
            return None
        wanted = [_plain(item.get("test")) for item in getattr(defect, "evidence", None) or []
                  if isinstance(item, dict) and item.get("test")]
        if not wanted:
            return None
        saved = latest(root)
        if saved is None:
            return None
        by_name: dict[str, dict] = {}
        for group in ("criteria", "change_requests"):
            for entry in (saved.get(group) or {}).values():
                for test in (entry or {}).get("tests") or []:
                    if isinstance(test, dict) and test.get("outcome") == "failed":
                        by_name.setdefault(_plain(test.get("name")), test)
        failing = [by_name[name] for name in dict.fromkeys(wanted) if name in by_name]
        if not failing:
            return None
        from app.acceptance.suite import MOST_UNIT_FAILURES_SHOWN

        shown = failing[:MOST_UNIT_FAILURES_SHOWN]
        output = "\n\n".join(f"{t.get('name')}:\n{t.get('message') or '(no message)'}" for t in shown)
        more = len(failing) - len(shown)
        if more:
            output += f"\n\n... and {more} more of its tests fail the same way."
        return {"command": "the acceptance suite's last run: " + ", ".join(_plain(t.get("name")) for t in shown),
                "output": output, "title": "What its failing tests printed"}
    except Exception:  # noqa: BLE001 - the last failing command stands in, as before
        logger.debug("Could not read a defect's tests in the latest measurement", exc_info=True)
        return None


__all__ = [
    "START_FAILURES", "actual_behavior_now", "as_shown", "latest", "what_its_tests_printed_now",
    "with_the_log_now", "with_the_tests_now", "without_a_hidden_cause_since_logged", "without_a_start_fault_since_gone",
]
