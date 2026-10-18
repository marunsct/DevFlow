"""Every service and full-stack pack's acceptance run gets a fresh data directory (plan item AO.6).

A product that stores data must start every suite run empty, or one test's
records are the next one's. The plan feared only one pack's configuration did
this; reading them shows the shared Playwright configuration and the Python
packs' conftest both do. This pins it for every pack, so a new pack that
forgets fails here, and the seeded PostgreSQL guidance agrees with the
embedded-by-default rule.
"""
from __future__ import annotations

import re

from app.plugins.seed import SEED_INSTRUCTIONS
from app.stacks.packs import ALL_PACKS

SERVICES = [pack for pack in ALL_PACKS if pack.kind in ("http_api", "fullstack")]
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_there_are_service_packs_to_check():
    assert len(SERVICES) >= 15


def test_every_one_gives_the_service_a_data_dir_of_its_own_per_run():
    for pack in SERVICES:
        runner = {path: text for path, text in pack.files.items() if path in ("playwright.config.js", "acceptance/conftest.py")}
        assert runner, f"{pack.name} has no acceptance runner file"
        assert any("DATA_DIR" in text for text in runner.values()), pack.name
        # Fresh: named for the run, or a temporary directory made for it.
        assert any(
            "acceptance-data-" in text or "data_dir" in text or "mkdtemp" in text or "tmp_path" in text
            for text in runner.values()
        ), f"{pack.name}'s DATA_DIR is not made fresh for each run"


def test_the_postgres_guidance_says_embedded_by_default():
    text = SEED_INSTRUCTIONS["postgres"]

    assert "embedded file database under `DATA_DIR`" in text and "only when the brief names it" in text
    assert not BANNED.search(text)
