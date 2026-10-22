"""The packs, the image and the benchmark scorer use one Playwright release.

A Playwright release finds only its own browser build. The image installed
whichever release was newest on the day it was built - after the source was
copied, so every deploy did it again - while the packs pinned an older one.
From one deploy on, the image held Chromium 1248 (Playwright 1.64) and the
packs looked for 1243 (1.63): three of four runs had their scaffold "left to
the agents" over an acceptance smoke test that could not start a browser, and
the scorer had been moved to 1.64 by hand to keep scoring.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.stacks.packs import _javascript as js

ROOT = Path(__file__).resolve().parent.parent


def test_the_image_installs_the_browser_of_the_packs_release() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert f"ARG PLAYWRIGHT_VERSION={js.PLAYWRIGHT}" in dockerfile
    assert "npx --yes playwright@${PLAYWRIGHT_VERSION} install chromium" in dockerfile


def test_the_scorer_runs_the_same_release() -> None:
    scorer = (ROOT / "scripts" / "bench" / "score.py").read_text()

    assert re.search(rf'^PLAYWRIGHT = "{re.escape(js.PLAYWRIGHT)}"$', scorer, re.M)


def test_the_browser_is_installed_before_anything_a_deploy_changes() -> None:
    """Before the source and the virtual environment built from it: a deploy keeps the browser."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    runtime = dockerfile[dockerfile.index("AS runtime"):]

    install = runtime.index("playwright@${PLAYWRIGHT_VERSION} install")
    assert install < runtime.index("COPY --from=python-builder /opt/venv")
    assert install < runtime.index("src/ ./src/")
