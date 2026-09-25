"""Read a specialist role the model wrote, as the slug the workflow routes on.

`SpecialistRole` is a `Literal` of six slugs - `ui_ux`, `database`, `backend`,
`testing`, `documentation`, `security_reliability` - and every prompt in this
harness names them that way. Models answer with the role's *name* anyway:
"Testing Specialist", "Backend", "QA Engineer", "UI/UX". That is the same
information, spelled for a reader.

Refusing it is expensive out of all proportion. `ReportedDefect.owner` is a
required field, so an unreadable spelling loses the entire defect - and with it
the description, the reproduction steps and the routing the model was trying to
provide. 

What the strict type protects is that a defect is *routable*: the gate refuses
a sprint whose defects are owned by "the team" or "backend service". That still
holds. Anything this cannot place is returned untouched for the schema to
reject, so an owner nobody can act on is still refused - it is only the six
real roles, written differently, that are now recognised.
"""

from __future__ import annotations

import re
from typing import Any

#: Words that identify a role, longest first so `security_reliability` is
#: tested before `security` and `ui_ux` before `ui`.
_ALIASES: tuple[tuple[str, str], ...] = (
    ("security_reliability", "security_reliability"),
    ("securityreliability", "security_reliability"),
    ("security and reliability", "security_reliability"),
    ("reliability", "security_reliability"),
    ("security", "security_reliability"),
    ("appsec", "security_reliability"),
    ("sre", "security_reliability"),
    ("documentation", "documentation"),
    ("technical writer", "documentation"),
    ("tech writer", "documentation"),
    ("docs", "documentation"),
    ("doc", "documentation"),
    ("ui_ux", "ui_ux"),
    ("ui ux", "ui_ux"),
    ("uiux", "ui_ux"),
    ("ux", "ui_ux"),
    ("ui", "ui_ux"),
    ("frontend", "ui_ux"),
    ("front end", "ui_ux"),
    ("client", "ui_ux"),
    ("design", "ui_ux"),
    ("database", "database"),
    ("data layer", "database"),
    ("persistence", "database"),
    ("schema", "database"),
    ("dba", "database"),
    ("db", "database"),
    ("backend", "backend"),
    ("back end", "backend"),
    ("server", "backend"),
    ("api", "backend"),
    ("testing", "testing"),
    ("quality engineering", "testing"),
    ("quality", "testing"),
    ("test", "testing"),
    ("qa", "testing"),
)

_SEPARATORS = re.compile(r"[\s\-/]+")

#: Words that say nothing about which role this is, so they must not stop a
#: match. "Testing Specialist" is the testing role; "Specialist" alone is not
#: a role at all, which is why they are stripped rather than mapped.
_NOISE = re.compile(
    r"\b(specialist|engineer|engineering|developer|dev|team|role|agent|lead|"
    r"owner|the|a|an)\b"
)


def role_slug(value: Any) -> Any:
    """`value` as one of the six role slugs, or `value` untouched.

    Untouched rather than guessed, so an owner that names nobody real - "the
    team", "whoever wrote it" - still fails validation and still gets reported
    back to the model by name.
    """
    if not isinstance(value, str):
        return value
    word = _SEPARATORS.sub(" ", value.strip().lower())
    word = _NOISE.sub(" ", word)
    word = " ".join(word.split())
    if not word:
        return value
    for alias, slug in _ALIASES:
        spaced = _SEPARATORS.sub(" ", alias.replace("_", " "))
        if word == spaced or re.search(rf"\b{re.escape(spaced)}\b", word):
            return slug
    return value


__all__ = ["role_slug"]
