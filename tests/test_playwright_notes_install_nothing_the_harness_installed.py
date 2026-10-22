"""The Playwright notes do not tell a stage to install a browser the harness installed.

Before a curated note existed, a generated one told every stage "After
installation, run `npx playwright install` to download the supported browser
binaries (Chromium, Firefox, WebKit)". The harness's image already has the
browser its pinned Playwright needs, and `--with-deps` is refused; QA ran it in
every run, one run twice before writing a test. A curated seed replaces a
generated row when the store is seeded.
"""

from __future__ import annotations

import re

from app.plugins.seed import SEED_INSTRUCTIONS


def test_there_is_a_curated_note() -> None:
    assert "playwright" in SEED_INSTRUCTIONS


def test_it_says_to_install_nothing_where_the_harness_set_up() -> None:
    note = " ".join(SEED_INSTRUCTIONS["playwright"].split())
    assert "install nothing" in note
    assert "refused" in note
    assert not re.search(r"\brun `npx playwright install", note)
    assert "Firefox" not in note and "WebKit" not in note
