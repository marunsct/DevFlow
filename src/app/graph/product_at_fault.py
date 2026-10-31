"""A QA repair may end at once when it finds no fault in the test (behind `QA_SAYS_THE_PRODUCT_IS_AT_FAULT`).

Measured on one run: a dispute sent a fair test back, QA concluded in its own words that the crash was "likely a product
bug", had no way to say so, and spent about 90 minutes before locking the suite again. So a repair a dispute opened may
answer "the named test's own code is right; the failure is the product's". The test stays locked, the run goes on as it
would have with no repair, and the repair budget, the repaired list and the reclassification cap are put back.

A model's claim decides this, so the claim alone unlocks nothing. It stands only when the harness finds all of:

- the reopen was a dispute's: a test the harness's own checks named cannot be claimed, they measured its fault;
- every test sent for this repair is claimed, each for the first time in the run;
- the suite is byte for byte its last lock: a repair that changed anything is a repair, reviewed as one;
- the harness's checks at the review find nothing, and the suite ran;
- each claimed test fails in the review's own measurement;
- each claim quotes the standard (criterion, brief, contract or specification) and the measured failure word for word.

What this cannot see: a right quotation attached to a wrong test. That is why a test is claimed once: when a later dispute
names it again, the repair is a charged one, and QA must change the test.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.acceptance import suite

logger = logging.getLogger(__name__)

#: `QA_SAYS_THE_PRODUCT_IS_AT_FAULT` set to on or off overrides this; off until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = ("A repair a dispute opened may answer that the named test is right and the product is at fault, quoting the "
               "standard and the measured failure: the harness checks both and that the suite is unchanged, then the test "
               "stays locked with no repair charged, once per test.")

MARK = "PRODUCT_AT_FAULT"
#: What QA is told, beside the repair's own rule, when a dispute opens the repair.
RULE = (
    "Read each named test first. If its own code is right and what fails is the product, which is not yours to change, "
    "change nothing in the suite and put one line per named test in `blockers`, each quoting word for word: "
    f"`{MARK}: <the test's name>: the standard says \"<the sentence of the criterion, brief, contract or specification "
    "it checks>\"; the run shows \"<the failure as the suite reported it>\"`. "
    "The harness checks each quotation. This answer holds only when it covers every named test and no suite file "
    "changed; a test that is wrong is repaired, as above."
)
#: The least a quotation of the standard is, in words, and of the failure, in characters.
LEAST_STANDARD_WORDS = 3
LEAST_FAILURE_CHARS = 8

_OPENED = "product_at_fault_opened"
_CLAIMS = "product_at_fault_claims"
_UPHELD = "product_at_fault_upheld"
_QUOTE_OPEN = "[\"“'`]"
_QUOTE_CLOSE = "[\"”'`]"
_A_CLAIM = re.compile(
    rf"^\W*{MARK}\s*:?\s*(?P<test>.+?)[\s:;,`\"']*the standard says\s*{_QUOTE_OPEN}(?P<standard>.+?){_QUOTE_CLOSE}\s*[;,.]?\s*"
    rf"(?:and\s+)?the run shows\s*{_QUOTE_OPEN}(?P<failure>.+){_QUOTE_CLOSE}\W*$",
    re.S,
)
_TAGS = re.compile(r"^(?:\s*\[[^\]]+\])+\s*")


def enabled() -> bool:
    from app.switches import is_on

    return is_on("QA_SAYS_THE_PRODUCT_IS_AT_FAULT", ON_BY_DEFAULT)


def _plain(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def _the_same_test(one: str, other: str) -> bool:
    left, right = _plain(one), _plain(other)
    return left == right or _plain(_TAGS.sub("", str(one))) == _plain(_TAGS.sub("", str(other)))


def offered(state: Any, root: str, tests: list[str]) -> list[str]:
    """Open the answer for a dispute's repair of `tests`, with what the budget stood at: QA's added rule, or []. Never raises."""
    if not enabled():
        return []
    try:
        record = suite._state(root)  # noqa: SLF001 - the suite's own record
        record.pop(_CLAIMS, None)
        record.pop(_OPENED, None)
        already = record.get(_UPHELD) or []
        offer = bool(tests) and not any(_the_same_test(test, done) for test in tests for done in already)
        if offer:
            record[_OPENED] = {
                "tests": list(tests),
                "suite_repairs": int(state.get("suite_repairs") or 0),
                "suite_repaired_tests": list(state.get("suite_repaired_tests") or []),
                "suite_reclassified_tests": list(state.get("suite_reclassified_tests") or []),
            }
        suite._save_state(root, record)  # noqa: SLF001
        return [RULE] if offer else []
    except Exception:  # noqa: BLE001 - the repair goes on as a repair
        logger.debug("Could not offer QA the product-at-fault answer", exc_info=True)
        return []


def take_claims(root: str, blockers: Sequence[Any]) -> list[Any]:
    """`blockers` without the lines of this answer, which are kept for the review. Never raises."""
    claims = [str(line) for line in blockers or () if MARK in str(line)]
    if not claims:
        return list(blockers or ())
    rest = [line for line in blockers if MARK not in str(line)]
    try:
        record = suite._state(root)  # noqa: SLF001
        if enabled() and _OPENED in record:
            record[_CLAIMS] = claims
            suite._save_state(root, record)  # noqa: SLF001
    except Exception:  # noqa: BLE001 - no claim kept, and the review reads the suite as a repair
        logger.debug("Could not keep QA's product-at-fault answer", exc_info=True)
    return rest


def _the_suite_is_as_locked(root: str) -> bool:
    base = Path(root)
    locked = suite._the_files_of(base / suite.SNAPSHOT_DIR)  # noqa: SLF001
    now = {path.relative_to(base).as_posix(): path.read_text(encoding="utf-8", errors="replace")
           for path in suite.suite_files(root)}
    return bool(locked) and locked == now


def _why_refused(test: str, claim: dict[str, str], result: Any, standards: str) -> str:
    """What is wrong with the claim for `test`, or ""."""
    failures = [
        str(item.message or "") for item in result.report.tests
        if item.outcome == "failed" and _the_same_test(item.name.split(" › ")[-1], test)
    ]
    if not failures:
        return "it does not fail in the review's measurement"
    standard = _plain(claim["standard"])
    if len(standard.split()) < LEAST_STANDARD_WORDS or standard not in standards:
        return "its quotation of the standard is not word for word"
    failure = _plain(claim["failure"])
    measured = _plain(" ".join([*failures, str(getattr(result, "server_log", "") or "")]))
    if len(failure) < LEAST_FAILURE_CHARS or failure not in measured:
        return "its quotation of the failure is not what the suite reported"
    return ""


def evidence(root: str, result: Any, problems: Sequence[str], standards: Sequence[str]) -> list[str]:
    """One line per claimed test when the claim stands (see the module's list), else []. Never raises."""
    if not enabled():
        return []
    try:
        record = suite._state(root)  # noqa: SLF001
        opened = record.get(_OPENED) or {}
        tests = [str(test) for test in opened.get("tests") or []]
        claims = [str(line) for line in record.get(_CLAIMS) or []]
        if not tests or not claims:
            return []
        if problems or not result.ran:
            logger.warning("QA said the product is at fault, but the harness's checks still name the suite; repaired as usual")
            return []
        if not _the_suite_is_as_locked(root):
            logger.warning("QA said the product is at fault, but the suite changed; reviewed as a repair")
            return []
        parsed = [found.groupdict() for found in map(_A_CLAIM.match, claims) if found]
        known = _plain("\n".join(str(text) for text in standards))
        lines = []
        for test in tests:
            claim = next((item for item in parsed if _the_same_test(item["test"].strip(" `\"'"), test)), None)
            why = "it is not claimed" if claim is None else _why_refused(test, claim, result, known)
            if why:
                logger.warning("QA's claim about `%s` does not hold: %s; the repair stands", test, why)
                return []
            lines.append(f"`{test}`: the standard says \"{claim['standard']}\"; the run shows \"{claim['failure']}\"")
        return lines
    except Exception:  # noqa: BLE001 - unknown is no evidence
        logger.debug("Could not check QA's product-at-fault answer", exc_info=True)
        return []


def settled(root: str, lines: Sequence[str]) -> dict[str, Any]:
    """At the lock: forget this repair's answer; when it stood, what the budget goes back to. Never raises."""
    try:
        record = suite._state(root)  # noqa: SLF001
        opened = record.pop(_OPENED, None) or {}
        record.pop(_CLAIMS, None)
        if lines:
            record[_UPHELD] = sorted({*(record.get(_UPHELD) or []), *(str(test) for test in opened.get("tests") or [])})
        suite._save_state(root, record)  # noqa: SLF001
        if not lines:
            return {}
        return {
            "suite_repairs": int(opened.get("suite_repairs") or 0),
            "suite_repaired_tests": list(opened.get("suite_repaired_tests") or []),
            "suite_reclassified_tests": list(opened.get("suite_reclassified_tests") or []),
        }
    except Exception:  # noqa: BLE001 - the lock stands; the repair stays charged
        logger.debug("Could not settle QA's product-at-fault answer", exc_info=True)
        return {}


__all__ = ["MARK", "ON_BY_DEFAULT", "RULE", "enabled", "evidence", "explanation", "offered", "settled", "take_claims"]
