"""Every service pack tells its builders that writes arrive at the same moment and how a store keeps them all.

Measured across the language sweep: products in several families lost one of two records created at once - a hidden
quality test each time - and on one Java run three fix rounds never found the read-change-write race that the
concurrent-write probe had named.
"""

from __future__ import annotations

import re

import pytest

from app.stacks.packs import ALL_PACKS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PACKS = {pack.name: pack for pack in ALL_PACKS}
SERVICES = sorted(name for name, pack in PACKS.items() if pack.kind == "http_api" and "DATA_DIR" in (pack.data_store or ""))


def test_there_are_service_packs_to_tell():
    assert len(SERVICES) >= 5


@pytest.mark.parametrize("name", SERVICES)
def test_the_data_guide_says_one_lock_for_the_read_the_change_and_the_write(name):
    said = " ".join(PACKS[name].data_store.split())
    assert "Requests arrive at once: read, change and write the store under one lock" in said
    assert "take a new record's id inside it" in said
    assert not BANNED.search(said)
