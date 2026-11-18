"""What a defect is about, as the measurement that raised it says: its kind, its evidence and its cause key.

Deep review 2026-11-18, item 1.1: a defect was a sentence. Whether two of them were one problem was decided three
different ways - overlapping words between descriptions (`sprint.recurrence_of`), a hash of the scrubbed wording
(`observability.defect_ledger.defect_id`), and the first sentence with its source (`_refreshed_by_the_round`) - and
none of them read what the harness had measured. Two criteria raised from one template ("[AC-3] ... - the
acceptance suite says this does not work yet" and "[AC-4] ...") share nearly every word, so a criterion raised after
another was fixed counted as that one coming back.

A defect raised from a measurement now carries what was measured: its `kind`, a few small `evidence` records (a
failing test, a compiler's error, a probe's request, a start's error line) and a `cause_key` made from them
deterministically. Two defects with a key are one problem exactly when their keys are equal; a defect without one
(a model's own report, a review finding) is compared as before.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath
from typing import Any

FAILING_TEST = "failing_test"
COMPILE_ERROR = "compile_error"
START_FAILURE = "start_failure"
PROBE_FINDING = "probe_finding"
REVIEW_FINDING = "review_finding"
OTHER = "other"
KINDS = (FAILING_TEST, COMPILE_ERROR, START_FAILURE, PROBE_FINDING, REVIEW_FINDING, OTHER)

#: Values that change from one measurement of one problem to the next: numbers, quoted values, places in a file.
_VARYING = re.compile(r"\"[^\"]*\"|'[^']*'|:\d+(?::\d+)?|\(\d+(?:,\d+)?\)|\d+")
#: A line of a failed start or build that says what went wrong, in the words runtimes and compilers of every language use.
_STATES_AN_ERROR = re.compile(r"\b\w*(?:Error|Exception)\b|\berror\b|\bfailed\b|panicked|cannot find|not found|"
                              r"unresolved|is not defined|\bundefined:", re.I)
#: An error line that names which error: an exception's type, a compiler's code, a panic.
_NAMES_WHICH_ERROR = re.compile(r"\b[A-Z]\w*(?:Error|Exception)\b|\berror\s?\[?[A-Z]{1,4}\d{3,5}\]?|panicked at")
#: A line a runner or build tool prints around the error, not the error: it says that something failed, not what.
_ONLY_SAYS_IT_FAILED = re.compile(r"webServer|was not able to start|could not compile|previous errors?\b|"
                                  r"exit(?:ed)?(?: with)? (?:code|status)|\bBuild failed\b|npm ERR!|did not start", re.I)
#: The most evidence records one defect keeps.
MOST_EVIDENCE = 24


def _plain(value: Any, most: int = 200) -> str:
    return " ".join(str(value or "").split())[:most]


def scrubbed(text: Any, most: int = 160) -> str:
    """`text` without what varies between two measurements of one problem, lower-cased."""
    return " ".join(_VARYING.sub("#", " ".join(str(text or "").split())).split()).lower()[:most]


def a_failing_test(name: Any, file: Any = "", criterion: Any = "") -> dict[str, str]:
    """The evidence of one failing test: its name, its file when known, the criterion it carries when known."""
    record = {"test": _plain(name, 300)}
    if str(file or "").strip():
        record["file"] = _plain(file)
    if str(criterion or "").strip():
        record["criterion"] = _plain(criterion, 40)
    return record


def a_compiler_error(file: Any, line: Any = None, code: Any = "", message: Any = "", symbol: Any = "") -> dict[str, Any]:
    """The evidence of one error a compiler or language service reports: where, its code, what it names."""
    record: dict[str, Any] = {"file": _plain(file)}
    if line not in (None, ""):
        record["line"] = line
    if str(code or "").strip():
        record["code"] = _plain(code, 40)
    if str(message or "").strip():
        record["message"] = _plain(message, 240)
    if str(symbol or "").strip():
        record["symbol"] = _plain(symbol, 120)
    return record


def a_probe_request(probe: Any, request: Any) -> dict[str, str]:
    """The evidence of one probe's finding: which probe, and the request it made."""
    return {"probe": _plain(probe, 60), "request": _plain(request, 300)}


def an_error_line(text: Any) -> dict[str, str]:
    """The evidence of a failed start or build: the error its output names, {} when it states none.

    The last line that names which error (an exception's type, a compiler's code) - a traceback ends on what was
    raised - else the last line that states an error and is not a runner's own "it did not start".
    """
    lines = [" ".join(line.split()) for line in str(text or "").splitlines()]
    stated = [line for line in lines if line and _STATES_AN_ERROR.search(line) and not _ONLY_SAYS_IT_FAILED.search(line)]
    named = [line for line in stated if _NAMES_WHICH_ERROR.search(line)]
    if not (named or stated):
        return {}
    return {"error": _plain((named or stated)[-1], 300)}


def kind_by_source(source: Any) -> str:
    """The kind of a defect that carries none, from the check that raised it: a review's or a model's finding."""
    said = str(source or "").lower()
    if "review" in said:
        return REVIEW_FINDING
    if said in {"language service"}:
        return COMPILE_ERROR
    return OTHER


def _the_id_of(record: dict[str, Any]) -> str:
    """One evidence record as a stable string: what it names, never where in a file or a number that moves."""
    if record.get("test"):
        file = PurePosixPath(str(record.get("file") or "")).name.lower()
        return f"test:{file + '::' if file else ''}{' '.join(str(record['test']).split()).lower()}"
    if record.get("probe"):
        return f"probe:{str(record['probe']).lower()}:{scrubbed(record.get('request'), 200)}"
    if record.get("file"):
        file = str(record["file"]).strip().removeprefix("./").lower()
        what = str(record.get("symbol") or record.get("code") or "").strip().lower() or scrubbed(record.get("message"), 120)
        return f"compile:{file}:{what}"
    if record.get("error"):
        return f"error:{scrubbed(record['error'])}"
    return ""


def cause_key(kind: Any, evidence: Any) -> str:
    """The stable key of a defect's cause, from its kind and evidence; "" when it has no evidence to key by.

    Deterministic and independent of order: the same evidence gives the same key in any round, any attempt and
    after any re-plan.
    """
    ids = sorted({_the_id_of(record) for record in evidence or () if isinstance(record, dict)} - {""})
    if not ids:
        return ""
    return f"{str(kind or OTHER)}:" + "|".join(ids)


def key_of(defect: Any) -> str:
    """A defect's cause key: the one it carries, else the one its kind and evidence give; "" when neither."""
    return str(getattr(defect, "cause_key", "") or "") or cause_key(getattr(defect, "kind", ""), getattr(defect, "evidence", None))


def same_cause(one: Any, other: Any) -> bool | None:
    """Whether two defects are one problem by their keys; None when either has none, for the caller's own rule."""
    mine, theirs = key_of(one), key_of(other)
    if not mine or not theirs:
        return None
    return mine == theirs


def merged_evidence(defects: Iterable[Any]) -> list[dict[str, Any]]:
    """The evidence of every defect in `defects`, each record once, in order, at most `MOST_EVIDENCE`."""
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for defect in defects:
        for record in getattr(defect, "evidence", None) or ():
            if not isinstance(record, dict):
                continue
            key = _the_id_of(record) or repr(sorted(record.items()))
            if key in seen:
                continue
            seen.add(key)
            kept.append(dict(record))
    return kept[:MOST_EVIDENCE]


def as_merged(lead: Any, others: Sequence[Any]) -> dict[str, Any]:
    """The `kind` and `evidence` a merge of `others` into `lead` carries: the lead's kind, every member's evidence."""
    if not any(getattr(member, "evidence", None) for member in (lead, *others)):
        return {}
    return {"kind": str(getattr(lead, "kind", "") or ""), "evidence": merged_evidence((lead, *others))}


__all__ = [
    "COMPILE_ERROR", "FAILING_TEST", "KINDS", "MOST_EVIDENCE", "OTHER", "PROBE_FINDING", "REVIEW_FINDING",
    "START_FAILURE", "a_compiler_error", "a_failing_test", "a_probe_request", "an_error_line", "as_merged",
    "cause_key", "key_of", "kind_by_source", "merged_evidence", "same_cause", "scrubbed",
]
