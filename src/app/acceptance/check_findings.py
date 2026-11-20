"""Every finding a harness check raises against the acceptance suite, recorded with the check that raised it.

Harness review Q1: the suite's mechanical checks (about fifty) send it back to its writers, and nobody measured how
often each one was right - false findings held runs for hours (an unawaited-call check, a whole-page lookup check,
a shared-count check). Each finding is written here as the review raises it; `scripts/loop/check_precision.py`
reads every run's file and reports, per check, how often its finding was acted on and gone the next round (the
writers changed the test and the check agreed) and how often it came back unchanged or was overruled by a dispute.
`noted` and `filtered` only record. `withheld` names the findings that came back unchanged after a repair, which
the review then gives the QA lead instead of the writers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FILE = ".harness/check-findings.jsonl"
#: Test names a finding cites, so the report can tell whether the writers changed the test it was about.
_A_TEST_NAME = re.compile(r"`?(test_[A-Za-z0-9_]+|[A-Za-z0-9_./-]+\.(?:spec|test)\.[jt]sx?)`?")


def _fingerprint(text: str) -> str:
    """The finding with its numbers and quoted values taken out: the same finding again reads the same."""
    plain = re.sub(r"`[^`]*`|\"[^\"]*\"|\d+", "_", str(text))
    return hashlib.sha1(" ".join(plain.split()).encode("utf-8")).hexdigest()[:12]


def noted(root: str | Path, review_round: int, check: str, findings: Sequence[Any] | None) -> list[Any]:
    """`findings` unchanged, each one recorded under `check`. Never raises."""
    found = list(findings or [])
    if not found or not root:
        return found
    try:
        path = Path(root) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            for text in found:
                text = str(text)
                out.write(json.dumps({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    "round": int(review_round or 0),
                    "check": check,
                    "fingerprint": _fingerprint(text),
                    "tests": sorted(set(_A_TEST_NAME.findall(text)))[:12],
                    "text": text[:600],
                }) + "\n")
    except Exception:  # noqa: BLE001 - a finding is sent back whether or not it is recorded
        logger.debug("Could not record a check's finding", exc_info=True)
    return found


def _finding_text(finding: Any) -> str:
    return " ".join(str(getattr(finding, "description", finding) or "").split())


def filtered(root: str | Path, review_round: int, check: str, before: Any, after: Any) -> Any:
    """`after` unchanged; each finding `check` dropped from `before` or moved to another severity recorded (HR2.G.1).

    A review filter that relabels a verdict or a finding only logged it, so how often each was right was unmeasured
    (6 of 21 send-backs over 40 runs were relabelled accepted). Each line has `kind: "filtered"`, the severity before
    and after (`dropped` when the finding is gone), and the verdict before and after. Never raises.
    """
    if not root or before is None or after is None:
        return after
    try:
        # A filter may say why in the finding's own words (a prefix before the description), so a finding is still
        # there when a finding after the filter holds its whole text.
        kept = [(_finding_text(f), str(getattr(f, "severity", ""))) for f in list(getattr(after, "findings", None) or [])]
        rows = []
        verdict = (str(getattr(before, "status", "")), str(getattr(after, "status", "")))
        for finding in list(getattr(before, "findings", None) or []):
            text, severity = _finding_text(finding), str(getattr(finding, "severity", ""))
            now = next((sev for t, sev in kept if t == text), None) or next(
                (sev for t, sev in kept if text and text in t), "dropped")
            if now != severity:
                rows.append((text, severity, now))
        if not rows and verdict[0] == verdict[1]:
            return after
        path = Path(root) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            for text, severity, now in rows or [("(the verdict only)", "", "")]:
                out.write(json.dumps({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    "round": int(review_round or 0),
                    "kind": "filtered",
                    "check": check,
                    "fingerprint": _fingerprint(text),
                    "severity_before": severity,
                    "severity_after": now,
                    "verdict_before": verdict[0],
                    "verdict_after": verdict[1],
                    "text": text[:600],
                }) + "\n")
    except Exception:  # noqa: BLE001 - the review goes on whether or not the filter's work is recorded
        logger.debug("Could not record a review filter's work", exc_info=True)
    return after


#: The findings the last review raised, the suite they were raised on, and those it held back (see `withheld`).
LAST_REVIEW_FILE = ".harness/check-findings-last-review.json"
#: The ledger event for a finding held back from the writers as a suspected false positive.
SUSPECTED_FALSE = "suspected false finding"
#: What the QA lead is told about the findings held back from the writers.
SUSPECTED_HEADING = "--- Harness findings suspected false ---"
SUSPECTED_SAID = (
    "Each finding below came back word for word after the writers repaired the suite, so the harness's check may be "
    "wrong about it. Read the test each one names. Where a finding holds, include it among your findings; where it "
    "does not, leave it out."
)


#: Checks whose finding is what running the test's own code did, not a reading of it: never held back as suspected
#: false. Measured on a C# run: the dry run's "cannot access '__filename' before initialization" was true, was held
#: back after one repair, and came back the next round regardless.
RAN_THE_CODE = frozenset({"spec_dry_run"})


def _key(check: str, text: str) -> str:
    """One finding across rounds: its check, its wording without the values that vary, and the tests it names."""
    return "|".join((check, _fingerprint(text), ",".join(sorted(set(_A_TEST_NAME.findall(str(text)))))))


def _the_suite_s_digest(root: str | Path) -> str:
    from app.acceptance.suite import suite_files

    digest = hashlib.sha1()
    try:
        for path in sorted(suite_files(root)):
            digest.update(Path(path).relative_to(Path(root)).as_posix().encode("utf-8"))
            digest.update(Path(path).read_bytes())
    except Exception:  # noqa: BLE001 - an unreadable suite is a suite that changed
        return ""
    return digest.hexdigest()[:16]


def withheld(root: str | Path, review_round: int, raised: Sequence[tuple[str, Any]]) -> list[str]:
    """The texts of `raised` ((check, finding) pairs) not to send back to the writers: those the review before raised
    the same - same check, same wording, same tests - with a repair of the suite between the two. Never raises.

    Per-role audit 2026-11-20: 187 findings came back unchanged three or more times, one false one seven rounds
    running, each round a repair the writers could not make. A finding that survived one repair unchanged goes to the
    QA lead as a suspected false positive instead, and is recorded in the ledger and beside the findings, so each
    check's repeats are measured. A review run again on the same suite (no repair between) holds back what it held.
    """
    if not root:
        return []
    try:
        path = Path(root) / LAST_REVIEW_FILE
        try:
            last = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            last = {}
        last = last if isinstance(last, dict) else {}
        digest = _the_suite_s_digest(root)
        repaired = bool(last) and (not digest or last.get("suite") != digest)
        before = set(last.get("raised") or []) if repaired else set(last.get("withheld") or [])
        keys = [(check, str(text), _key(check, str(text))) for check, text in raised]
        held = [(check, text, key) for check, text, key in keys if key in before and check not in RAN_THE_CODE]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"suite": digest, "raised": sorted({key for _, _, key in keys}),
                                    "withheld": sorted({key for _, _, key in held})}), encoding="utf-8")
        fresh = [(check, text, key) for check, text, key in held if key not in set(last.get("withheld") or [])]
        if fresh:
            from app.observability import defect_ledger

            with (Path(root) / FILE).open("a", encoding="utf-8") as out:
                for check, text, _ in fresh:
                    out.write(json.dumps({
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                        "round": int(review_round or 0),
                        "kind": "withheld",
                        "check": check,
                        "fingerprint": _fingerprint(text),
                        "tests": sorted(set(_A_TEST_NAME.findall(text)))[:12],
                        "text": text[:600],
                    }) + "\n")
            for check, text, _ in fresh:
                defect_ledger.note(SUSPECTED_FALSE, "acceptance_review", round_=int(review_round or 0),
                                   detail=f"{check}: {text}")
        return [text for _, text, _ in held]
    except Exception:  # noqa: BLE001 - a finding that cannot be compared is sent back as before
        logger.debug("Could not compare the findings with the last review's", exc_info=True)
        return []


def forgotten(root: str | Path) -> None:
    """At the lock: the next review compares with nothing, so a reopened suite's findings go to its writers first."""
    try:
        (Path(root) / LAST_REVIEW_FILE).unlink(missing_ok=True)
    except OSError:
        pass


def for_the_qa_lead(texts: Sequence[str]) -> str:
    """The findings held back from the writers, as the QA lead reads them; "" when none."""
    if not texts:
        return ""
    return "\n".join([SUSPECTED_HEADING, SUSPECTED_SAID, *(f"- {' '.join(str(t).split())[:1200]}" for t in texts)]) + "\n"


def read(root: str | Path) -> list[dict[str, Any]]:
    """Every finding recorded in this workspace, oldest first; [] when none."""
    try:
        lines = (Path(root) / FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


__all__ = ["RAN_THE_CODE", "FILE", "LAST_REVIEW_FILE", "SUSPECTED_FALSE", "filtered", "for_the_qa_lead", "forgotten", "noted", "read",
           "withheld"]
