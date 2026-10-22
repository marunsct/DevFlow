"""QA is told, and its reviewer checks, that a test never starts the product itself.

One run's acceptance test ran `bash start.sh` - which starts the service and
never returns - and the suite hung to its command's limit with no result for
any test; the writer, with no result to read, then spent forty calls trying to
start the service and to build the product. The suite's own setup starts it.
"""
from __future__ import annotations

import re

from app.acceptance.criteria import Criterion
from app.acceptance.requests import build_author_request

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _rule(text: str) -> str:
    for opening in ("Never start a product that keeps running", "A test must never start a product that keeps running"):
        if opening in text:
            start = text.index(opening)
            return text[start:start + 620]
    raise AssertionError("no rule")


def test_the_writer_is_told(tmp_path):
    request = build_author_request(tmp_path, [Criterion("AC-1", "The service starts with start.sh", "brief")])
    rule = _rule(request["messages"][-1]["content"])

    assert "the suite's own setup starts it" in rule and "A program that runs and exits is run by its tests" in rule
    assert not BANNED.search(rule)


def test_the_reviewer_checks_it():
    from app.agents import acceptance_reviewer

    prompt = next(value for name, value in vars(acceptance_reviewer).items()
                  if isinstance(value, str) and "A test must never start a product that keeps running" in value)
    rule = _rule(prompt)

    assert "Name every test that does" in rule and "A program that runs and exits is run by its tests" in rule
    assert not BANNED.search(rule)
