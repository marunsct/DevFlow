"""A JavaScript project's JUnit report comes from the runner's own reporter, not one the setup writes.

Measured on one run (a Hono service tested with Vitest): the setup looked up `@vitest/junit-reporter` and
`vitest-junit-reporter`, found neither, wrote a reporter class of its own, and under that Vitest version it wrote no
report file, so the harness could not prove the setup and left the project's tests to the agents - about forty
minutes. Vitest has the reporter built in.
"""
from __future__ import annotations

import re

from app.plugins.seed import SEED_INSTRUCTIONS, SETUP

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _bullet(text: str) -> str:
    return text.split("- A JUNIT XML REPORT COMES FROM THE RUNNER'S OWN REPORTER")[1].split("\n#:")[0]


def test_every_javascript_setup_is_told_each_runner_has_its_own_reporter():
    for key in ("javascript", "typescript", "node"):
        text = _bullet(SEED_INSTRUCTIONS[key + SETUP])
        assert "reporters: ['default', 'junit']" in text and "jest-junit" in text
        assert "--test-reporter=junit" in text and "never write a" in text


def test_the_guidance_uses_none_of_the_banned_words():
    assert not BANNED.search(_bullet(SEED_INSTRUCTIONS["typescript" + SETUP]))
