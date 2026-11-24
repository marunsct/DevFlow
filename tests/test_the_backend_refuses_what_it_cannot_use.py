"""The backend builder is told a request it cannot use is refused with a 4xx before anything is read or stored.

Measured on the language sweep: in three of six runs the harness's probes found a server answering 500 to a request it
should refuse - a write with no body (Java), an id that is not a number (PHP), JSON that cannot be parsed (Ruby) - and
each cost fix rounds, one a re-plan. The backend role's prompt said nothing of such requests.
"""
from __future__ import annotations

import re

from app.agents import specialists

BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_backend_role_is_told():
    prompt = specialists._ROLE_DESCRIPTIONS["backend"]
    rule = specialists.REFUSE_WHAT_IT_CANNOT_USE
    assert rule in prompt
    assert "4xx" in rule and "no body" in rule and "not JSON" in rule and "never" in rule
    assert not BANNED.search(rule)


def test_the_backend_role_is_told_a_field_the_brief_does_not_refuse_empty_is_kept_when_empty():
    """LF.1273: on five runs of five stacks the brief refused only an empty title, the specification gave the body as
    "string (required)", and every product refused an empty body too; a hidden test writing one failed."""
    prompt = specialists._ROLE_DESCRIPTIONS["backend"]
    rule = specialists.REFUSE_WHAT_IT_CANNOT_USE

    assert rule in prompt
    assert "kept when empty" in rule and "never refused" in rule and '"required" means the field is present' in rule
    assert not BANNED.search(rule)


def test_the_backend_role_is_told_a_length_limit_the_brief_does_not_set_is_not_added():
    """LF.1298: a hidden test writing a 26,000-character body failed in 17 of 95 scored runs; on one the specification
    alone added "body max 10000 characters" and the product refused the long body with 400."""
    prompt = specialists._ROLE_DESCRIPTIONS["backend"]
    rule = specialists.REFUSE_WHAT_IT_CANNOT_USE

    assert rule in prompt
    assert "length limit the brief does not set is not added" in rule and "never refused" in rule
    assert not BANNED.search(rule)
