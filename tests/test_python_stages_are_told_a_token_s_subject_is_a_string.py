"""Python stages are told PyJWT 2.10+ refuses a token whose `sub` claim is not a string.

Measured on a gate run: an integer id in `sub` made every signed-in request
answer 401 and blocked eight criteria for about an hour of fix stages.
"""
from __future__ import annotations

import re

from app.plugins.seed import SEED_INSTRUCTIONS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_python_guidance_names_the_subject_claim_rule():
    text = SEED_INSTRUCTIONS["python"]
    line = next(l for l in text.splitlines() if "Signed tokens" in l)
    assert "`sub`" in line and "PyJWT 2.10" in line and "str(" in line
    assert not BANNED.search(line)
