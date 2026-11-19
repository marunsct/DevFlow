"""The service packs' acceptance guide says how the `request` fixture sends a body that is not valid JSON.

Measured on one Ruby run: the acceptance author, writing "invalid JSON is refused with 400", spent ten of its 31 calls
over twelve minutes searching the installed Playwright source for how a raw body is sent; its documentation lookup
returned the package's README, which does not say. A string `data` is sent as written, with the content type named.
"""
from __future__ import annotations

import re

from app.stacks.packs import _service

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_guide_shows_a_raw_body_with_its_content_type():
    guide = _service.ACCEPTANCE_GUIDE

    assert "not valid JSON" in guide and "'Content-Type': 'application/json'" in guide
    assert "a string\n`data` goes out exactly as written" in guide or "a string `data` goes out exactly as written" in guide.replace("\n", " ")
    assert not BANNED.search(guide)
