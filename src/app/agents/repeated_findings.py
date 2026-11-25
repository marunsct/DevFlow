"""Whether a review's finding is one the sprint has already recorded (PA.17).

Measured on one run's security reviews (the 2026-11-25 per-agent audit, role 18): the second review of the same sprint
raised three of the first review's findings again, and the milestone review repeated two of them as suggestions. Each
repeat is a line a fixer or the reader goes through again for nothing.

Two findings are the same when their words are: most of the shorter one's words are in the longer one, or the two
share most of their words between them. A rephrasing that keeps the code it names ("`TaskModel` is never used" against
"the unused `TaskModel` class") matches; two findings about different code do not. A false match costs one finding
that does not hold the sprint, since only those are ever dropped as repeats (`not_raised_again`), never one that gates.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

#: Words too common in a finding to say which one it is.
_COMMON = frozenset({
    "the", "this", "that", "these", "those", "with", "from", "into", "when", "where", "which", "there", "their", "have",
    "been", "will", "would", "should", "could", "does", "file", "code", "line", "lines", "used", "uses", "using",
    "missing", "found", "also", "only", "than", "then", "they", "them", "what", "make", "made", "same", "such",
})
_WORD = re.compile(r"[a-z0-9_]+")
#: How much of the shorter finding's words must be in the longer one.
CONTAINED = 0.8
#: How much of the two findings' words they must share.
SHARED = 0.6


def _words(text: str) -> frozenset[str]:
    return frozenset(word for word in _WORD.findall(str(text or "").lower())
                     if len(word) >= 3 and word not in _COMMON)


def same_finding(one: str, other: str) -> bool:
    """Whether two findings' descriptions say the same thing."""
    a, b = _words(one), _words(other)
    if len(a) < 3 or len(b) < 3:
        return " ".join(str(one).lower().split()) == " ".join(str(other).lower().split())
    shared = len(a & b)
    return shared / min(len(a), len(b)) >= CONTAINED or shared / len(a | b) >= SHARED


def recorded_by(findings: Iterable[Mapping[str, Any]] | None, sources: Sequence[str] | None = None,
                *, other_than: str = "") -> list[str]:
    """The descriptions of the Sprint Record's findings (`sprint.record.findings_of`): those `sources` raised (every
    source when None), less those `other_than` raised."""
    return [str(finding.get("description") or "") for finding in findings or ()
            if isinstance(finding, Mapping) and str(finding.get("description") or "").strip()
            and (sources is None or str(finding.get("source") or "") in sources)
            and str(finding.get("source") or "") != other_than]


def already_recorded(description: str, recorded: Sequence[str]) -> bool:
    """Whether `description` repeats one of the `recorded` findings."""
    return any(same_finding(description, earlier) for earlier in recorded)


__all__ = ["CONTAINED", "SHARED", "already_recorded", "recorded_by", "same_finding"]
