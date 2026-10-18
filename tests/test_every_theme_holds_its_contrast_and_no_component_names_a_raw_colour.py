"""Every theme and accent keeps its contrast, and no component hard-codes a colour (plan Part 15.2).

The interface was dark-only because components named white, slate and hex
values. Colour is now a token, so a theme changes it everywhere; this keeps it
that way: the contrast script checks every declared pair in every theme and
accent, and no component may go back to a raw colour.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "langchain-ui"


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_every_declared_pair_holds_in_every_theme():
    done = subprocess.run(["node", str(ROOT / "scripts/ui/theme_contrast.mjs")], capture_output=True, text=True)

    assert done.returncode == 0, done.stdout
    assert "every pair holds" in done.stdout


def test_the_three_themes_and_the_options_are_declared():
    css = (UI / "src/index.css").read_text()

    for theme in ("graphite", "paper", "contrast", "system"):
        assert f'data-theme="{theme}"' in css
    for accent in ("violet", "teal", "amber", "rose", "neutral"):
        assert f'data-accent="{accent}"' in css
    assert 'data-density="compact"' in css
    assert "fonts.googleapis.com" not in css and "/fonts/ibm-plex-sans-latin-400-normal.woff2" in css


def test_the_theme_is_set_before_first_paint():
    html = (UI / "index.html").read_text()

    assert "devflow.appearance" in html and "data-theme" in html
    assert "fonts.googleapis.com" not in html


RAW = re.compile(
    r"(?<![\w-])(?:text|bg|border|ring|from|to|via)-(?:white|black|slate-\d+|gray-\d+|zinc-\d+|indigo-\d+|violet-\d+|red-\d+)\b"
    r"|(?:bg|text|border)-\[#[0-9a-fA-F]{3,8}\]"
)


def test_no_component_names_a_raw_colour():
    offenders = []
    for path in (UI / "src").rglob("*.tsx"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if RAW.search(line):
                offenders.append(f"{path.relative_to(UI)}:{number}: {line.strip()[:100]}")

    assert offenders == []
