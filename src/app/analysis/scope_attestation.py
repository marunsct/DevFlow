"""Which finding categories this product's own documents ever raised.

`SCOPE_DISCIPLINE` states the rule at every stage that can inflate scope:
"Something the intake does not ask for is not a requirement, however standard
the practice is... never as a blocking or major finding." It is stated, and it
is ignored.

Measured across all 50 stored transcripts, milestone review raised 174
findings, of which 87 blocked:

    testing         59 blocking   24 advisory
    documentation    0 blocking   36 advisory
    accessibility   13 blocking   11 advisory
    security        11 blocking    8 advisory
    correctness      1 blocking    1 advisory

No brief in this repository - low, medium or high - contains the words
"accessibility", "aria", "wcag", "screen reader" or "contrast". Neither does
any specification: `accessibility` appears in **zero** of one run's
documents, and in one of one run's, which is the review that raised it.
Thirteen sprints were held up for a requirement nobody stated, and seven runs
in the last sixty failures ended with "the milestone review still required
changes after N revisions".

Only 2 of the 174 findings were about correctness.

So the rule becomes a check, which is root-cause class A: a rule stated in a
prompt does not change behaviour, and one enforced where the finding is used
does. A finding in a category the product's own documents never raise is
capped to `minor`. It is still reported - the reviewer's judgement is not
discarded - it simply cannot hold a sprint, which is what the prompt already
says should happen.

Deliberately reads the documents the run produced *before* the review, never
the review documents themselves. A reviewer's own output would otherwise
attest its own category and the check would pass on everything.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

#: Documents that say what this product is for. The intake is the boundary;
#: the specification and the plans are what the workflow derived from it, and
#: a category any of them raises is legitimately in scope.
_SCOPE_DOCUMENTS = (
    "product_intake.md",
    "technical_specification.md",
    "technology_stack.md",
    "tools_and_models.md",
    "sprint_plan.md",
    "milestone_plan.md",
)

#: Never read: the workflow renders these FROM a review, so a finding's own
#: category would attest itself.
_REVIEW_DOCUMENTS = ("milestone_review.md", "architecture_review.md", "security_review.md")

#: Words that attest a category beyond the category's own name. A brief that
#: says "screen reader" has asked for accessibility without using the word.
#:
#: Matched on whole words. The first version used substrings and
#: `accessib` matched "files are accessible via HTTPS" in one run's
#: tools-and-models document - a sentence about file access attesting
#: accessibility, which would have let the very findings this check exists to
#: cap go on blocking. `auth` would likewise have matched "author" in every
#: document that has one.
_ALSO_ATTESTS: dict[str, tuple[str, ...]] = {
    "accessibility": (
        "accessibility", "accessible to", "aria", "wcag", "a11y",
        "screen reader", "contrast ratio", "keyboard navigation",
    ),
    "testing": ("test", "tests", "testing", "spec", "specs", "coverage", "assertion"),
    "security": (
        "security", "secure", "authentication", "authorisation", "authorization",
        "secret", "secrets", "xss", "csrf", "injection", "sanitise", "sanitize",
    ),
    "documentation": ("documentation", "document", "documents", "readme", "docstring"),
    "performance": ("performance", "latency", "throughput", "benchmark"),
    "migrations": ("migration", "migrations", "alembic"),
    "contracts": ("contract", "contracts", "openapi", "interface", "interfaces"),
    "correctness": ("correct", "correctly", "behaviour", "behavior", "acceptance"),
    # Added with the category vocabulary. `code_quality` is attested by a
    # brief that asks for it; `other` never is, by design - an unrecognised
    # finding is kept and reported and cannot hold a sprint.
    "code_quality": ("quality", "lint", "linting", "maintainability", "refactor", "style"),
    "authorization": ("authorisation", "authorization", "permission", "permissions", "role", "roles"),
    "regression": ("regression", "regressions"),
    "other": (),
}


def categories_in_scope(repo_root: str | Path) -> frozenset[str]:
    """Finding categories this product's own documents raise. Never raises.

    An unreadable workspace returns every category, so a missing document can
    only ever be permissive - failing closed here would cap legitimate
    findings on a run whose docs have not been written yet.
    """
    try:
        docs = Path(repo_root) / "docs"
        if not docs.is_dir():
            return frozenset(_ALSO_ATTESTS)
        text = []
        for name in _SCOPE_DOCUMENTS:
            path = docs / name
            if path.name in _REVIEW_DOCUMENTS:
                continue
            try:
                text.append(path.read_text(encoding="utf-8", errors="replace").lower())
            except OSError:
                continue
        if not text:
            return frozenset(_ALSO_ATTESTS)
        blob = "\n".join(text)
    except Exception:  # noqa: BLE001 - a scope check must never fail a review
        logger.debug("Could not read the scope documents", exc_info=True)
        return frozenset(_ALSO_ATTESTS)

    found = set()
    for category, markers in _ALSO_ATTESTS.items():
        for marker in (category, *markers):
            if re.search(rf"(?<![\w-]){re.escape(marker)}(?![\w-])", blob):
                found.add(category)
                break
    return frozenset(found)


def _normalised(value: str) -> str:
    """A category reduced to letters, for comparing against the table.

    Both sides, or neither. Stripping only the incoming value left
    `code_quality` as `codequality`, which matches no key in `_ALSO_ATTESTS`,
    so every `code_quality` finding was treated as a category this module
    does not know and allowed to block - silently, and in exactly the
    category the model reaches for most after testing and security.
    """
    return re.sub(r"[^a-z]", "", (value or "").lower())


def out_of_scope_reason(category: str, in_scope: frozenset[str]) -> str:
    """Why this category cannot hold a sprint, or "" if it can."""
    key = _normalised(category)
    known = {_normalised(name): name for name in _ALSO_ATTESTS}
    attested = {_normalised(name) for name in in_scope}
    if not key or key not in known or key in attested:
        return ""
    return (
        f"'{category}' is not something this product's brief, specification or "
        "plans ever raise, so a finding about it cannot hold the sprint. It is "
        "kept as a minor finding and recorded. If it genuinely belongs in this "
        "product, it belongs in the intake first."
    )


__all__ = ["categories_in_scope", "out_of_scope_reason"]
