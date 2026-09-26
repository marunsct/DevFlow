"""Read a finding's category in the vocabulary the schema asks for.

The exact shape `app.agents.severity` was written for, one field along.
`severity` is forgiven when a model writes a word from a neighbouring
vocabulary; `category` is a bare `Literal` and is not, so one unrecognised
word throws away the whole review.

Measured live on run-cac07d52 at 05:36, on a model swapped in mid-run:

    Stage milestone_reviewer sent an answer that does not satisfy its
    schema (findings.4.category); returning the validation errors

It cost that review three and a half minutes and a full re-generation. Across
the same run the model wrote `code_quality` 24 times and `test` for `testing`
four times - both perfectly clear, neither in the list.

Refusing an out-of-vocabulary category has never caught a model that did not
know what kind of problem it had found. It only throws away the sentence that
says so, which is the lesson `severity.py` and `ReportedDefect` both already
record.

`other` exists so an unrecognised category is preserved rather than guessed
at. It also composes with the scope gate: no brief ever says "other", so
`app.analysis.scope_attestation` caps such a finding to minor. An unfamiliar
finding is therefore kept, reported and unable to hold a sprint, which is the
right answer for something the harness could not classify.
"""

from __future__ import annotations

from typing import Any

#: Words models actually write, mapped onto a category. Keys are compared
#: lowercased with separators stripped, so `code_quality`, `code-quality` and
#: `Code Quality` are one key.
_SYNONYMS: dict[str, str] = {
    # testing
    "test": "testing", "tests": "testing", "qa": "testing",
    "coverage": "testing", "testcoverage": "testing", "verification": "testing",
    # correctness
    "bug": "correctness", "defect": "correctness", "logic": "correctness",
    "functionality": "correctness", "behaviour": "correctness", "behavior": "correctness",
    # security
    "vulnerability": "security", "dataleakage": "security", "isolation": "security",
    "retention": "security", "secrets": "security", "privacy": "security",
    "authentication": "authorization", "authn": "authorization", "authz": "authorization",
    "permissions": "authorization", "access": "authorization",
    # documentation
    "docs": "documentation", "readme": "documentation", "comments": "documentation",
    # accessibility
    "a11y": "accessibility", "usability": "accessibility",
    # contracts
    "api": "contracts", "interface": "contracts", "schema": "contracts",
    # migrations
    "migration": "migrations", "database": "migrations",
    # regression
    "regressions": "regression", "breakage": "regression",
    # code quality, which has its own bucket because it is none of the above
    "quality": "code_quality", "codequality": "code_quality",
    "maintainability": "code_quality", "style": "code_quality",
    "lint": "code_quality", "linting": "code_quality", "refactor": "code_quality",
    "cleanliness": "code_quality", "readability": "code_quality",
    "performance": "code_quality", "duplication": "code_quality",
}


def _key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def normalise(value: Any, allowed: tuple[str, ...]) -> Any:
    """`value` as one of `allowed`, or `other` when nothing matches.

    Returns the value untouched when it is already allowed, so a schema that
    does not offer `other` is never handed one.
    """
    text = str(value or "").strip()
    if text in allowed:
        return text
    key = _key(text)
    for candidate in allowed:
        if key == _key(candidate):
            return candidate
    mapped = _SYNONYMS.get(key)
    if mapped and mapped in allowed:
        return mapped
    # A word that contains one of the schema's own, e.g. "testing strategy".
    for candidate in allowed:
        if _key(candidate) and _key(candidate) in key:
            return candidate
    return "other" if "other" in allowed else value


def validator_for(*allowed: str) -> Any:
    """A `mode="before"` validator that normalises onto `allowed`.

    Used as::

        _category = field_validator("category", mode="before")(
            validator_for("correctness", "testing", ..., "other")
        )
    """

    def _normalise(cls: Any, value: Any) -> Any:
        return normalise(value, allowed)

    return classmethod(_normalise)


__all__ = ["normalise", "validator_for"]
