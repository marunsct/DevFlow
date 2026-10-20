"""The security review asks for secrets that leave the product able to start as the tests start it.

Measured on one run: the review asked for `SECRET_KEY` to be moved to the
environment, the work order made the product refuse to start without it, and
every acceptance test failed - the suite sets only `PORT` and `DATA_DIR`.
"""
from __future__ import annotations

import re

from app.agents import security_reviewer

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_review_is_told_how_a_secret_works_here():
    prompt = security_reviewer._SYSTEM_PROMPT

    assert security_reviewer.SECRETS_HERE in prompt
    assert "`PORT` and `DATA_DIR`" in security_reviewer.SECRETS_HERE
    assert "development" in security_reviewer.SECRETS_HERE and "unset" in security_reviewer.SECRETS_HERE
    assert not BANNED.search(security_reviewer.SECRETS_HERE)
