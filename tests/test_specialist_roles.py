"""The six role slugs, written the way models actually write them.

run-0deeb8bf's Testing specialist named itself "Testing Specialist" as the
`owner` of a defect it had described correctly. `owner` is required, so the
spelling lost the description, the reproduction steps and the routing.
"""

from __future__ import annotations

import pytest

from app.agents.specialist_roles import role_slug


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("testing", "testing"),
        ("Testing Specialist", "testing"),
        ("QA", "testing"),
        ("QA Engineer", "testing"),
        ("Quality Engineering", "testing"),
        ("backend", "backend"),
        ("Backend", "backend"),
        ("Backend Engineer", "backend"),
        ("server", "backend"),
        ("API", "backend"),
        ("ui_ux", "ui_ux"),
        ("UI/UX", "ui_ux"),
        ("UX", "ui_ux"),
        ("Frontend Developer", "ui_ux"),
        ("database", "database"),
        ("DB", "database"),
        ("DBA", "database"),
        ("documentation", "documentation"),
        ("Docs", "documentation"),
        ("Technical Writer", "documentation"),
        ("security_reliability", "security_reliability"),
        ("Security and Reliability", "security_reliability"),
        ("Security", "security_reliability"),
        ("SRE", "security_reliability"),
    ],
)
def test_a_role_is_recognised_however_it_is_spelled(written: str, expected: str) -> None:
    assert role_slug(written) == expected


@pytest.mark.parametrize(
    "written", ["the team", "whoever wrote it", "", "Specialist", "everyone"]
)
def test_an_owner_nobody_can_act_on_is_still_refused(written: str) -> None:
    """The gate this field protects is that a defect is routable.

    Anything that does not name one of the six is returned untouched, so the
    schema rejects it and the model is told which field is wrong - which is
    what "no unowned defects" has always meant.
    """
    assert role_slug(written) not in {
        "ui_ux", "database", "backend", "testing", "documentation", "security_reliability",
    }


def test_a_role_named_as_a_component_still_routes() -> None:
    """"backend service" is unroutable as a free string and perfectly routable
    as a role: it names the backend specialist. Placing it is what the routing
    gate wanted - what it forbids is an owner that names nobody."""
    assert role_slug("backend service") == "backend"
    assert role_slug("the database layer") == "database"


def test_a_longer_name_wins_over_the_word_inside_it() -> None:
    assert role_slug("security_reliability") == "security_reliability"
    assert role_slug("ui_ux") == "ui_ux"


def test_a_non_string_is_left_alone() -> None:
    assert role_slug(None) is None
    assert role_slug(7) == 7
