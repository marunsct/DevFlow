"""The service packs' data guide says the data directory may not exist yet and must be created before the first write.

Measured on one run: the suite handed the service a fresh `DATA_DIR` path; every first write failed `ENOENT`, each
request answered 500, and four fixes in a row were reverted.
"""
from __future__ import annotations

import re

from app.stacks import pack_named
from app.stacks.packs import _service

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_guide_says_create_it_and_read_a_missing_file_as_empty():
    guide = _service.DATA_GUIDE
    assert "may not exist yet" in guide and "create it, with its parents" in guide and "missing data file reads as empty" in guide
    assert not BANNED.search(guide)


def test_the_service_packs_show_it():
    assert "may not exist yet" in pack_named("node-hono-native-api").guide + pack_named("node-hono-native-api").acceptance_guide \
        or "may not exist yet" in str(vars(pack_named("node-hono-native-api")))
