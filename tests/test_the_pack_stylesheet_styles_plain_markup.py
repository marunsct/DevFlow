"""The web packs' stylesheet styles plain markup on its design tokens, and hides nothing (plan PQ.7).

Read in eight stored products: pages built on the tokens alone were correct but plain - a bare heading, stacked fields
and a ruled list, no surface, no states beyond opacity. The stylesheet every web pack starts with now styles unclassed
markup too: the page header and surface, fields with hover, focus, disabled and invalid states, a primary and a quiet
control, a list row, a message area and an empty-state block, elevation and one transition. The small packs' hidden
tests count list items, find fields by label and forbid sideways scrolling at 375px, so it must hide nothing and fit a
phone.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis import product_quality
from app.stacks import pack_named

ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT = ROOT / "scripts" / "ui" / "node_modules" / "playwright-core"
CHROMES = sorted(Path(os.path.expanduser("~/.cache/ms-playwright")).glob(
    "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))

#: Every web pack and where its stylesheet is.
SHEETS = [
    ("browser-javascript", "styles.css"),
    ("browser-react", "src/styles.css"),
    ("browser-svelte", "src/styles.css"),
    ("browser-angular", "src/styles.css"),
    ("fullstack-node", "public/styles.css"),
    ("fullstack-react-express", "src/styles.css"),
    ("fullstack-django", "{{package}}/static/{{package}}/styles.css"),
]


def _sheet(pack: str, path: str) -> str:
    return pack_named(pack).files[path]


@pytest.mark.parametrize("pack, path", SHEETS)
def test_each_part_of_a_page_is_styled_on_the_tokens(pack, path):
    rules = product_quality.css_rules(_sheet(pack, path))
    selectors = " ".join(rule.selector for rule in rules)

    for wanted in ("body > header", "input:hover", "input:focus-visible", "input:disabled", "input:user-invalid",
                   "[aria-invalid=true]", "[type=submit]", "[aria-pressed=true]", "main li + li", "[role=alert]",
                   "[role=status]", "main > form"):
        assert wanted in selectors, wanted
    declared = {name for rule in rules for name, _, _ in rule.declarations}
    assert {"box-shadow", "transition"} <= declared
    assert any("prefers-reduced-motion" in rule.media for rule in rules)


@pytest.mark.parametrize("pack, path", SHEETS)
def test_it_uses_no_raw_colour_and_every_pair_it_declares_reads(pack, path):
    rules = product_quality.css_rules(_sheet(pack, path))
    raw = [(rule.selector, name, value) for rule in rules for name, value, _ in rule.declarations
           if not name.startswith("--") and "var(" not in value and product_quality.parse_colour(value)
           and name in ("color", "background", "background-color", "border-color", "outline-color")]

    assert raw == []
    assert product_quality.contrast_failures(rules) == []


@pytest.mark.parametrize("pack, path", SHEETS)
def test_nothing_in_it_hides_content_or_fixes_a_width(pack, path):
    text = _sheet(pack, path)

    assert not re.search(r"display\s*:\s*none|visibility\s*:\s*hidden|overflow\s*:\s*hidden|list-style\s*:\s*none", text)
    assert not re.search(r"(?<![-\w])(?:min-)?width\s*:\s*\d{3,}px", text)


#: A page of plain markup, as a small brief's builder writes it.
PAGE = """<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>%s</style></head><body>
<header><h1>Notes</h1></header>
<main>
<form><label for="title">Title</label> <input id="title" required>
<label for="body">Description</label> <textarea id="body"></textarea>
<button type="submit">Add note</button></form>
<div role="group"><button type="button" aria-pressed="true">All</button>
<button type="button" aria-pressed="false">Active</button></div>
<p role="status">No notes yet</p>
<p role="alert">Could not save the note. Try again.</p>
<ul><li><label><input type="checkbox"> Done</label> A note with a rather long title that wraps on a phone
<button type="button">Delete</button></li><li>Second note</li></ul>
</main></body></html>"""


@pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROMES and shutil.which("node")),
                    reason="needs node, playwright-core and a headless Chromium")
@pytest.mark.parametrize("pack, path", [SHEETS[0], SHEETS[1]])
def test_plain_markup_fits_a_phone_and_reads_in_both_schemes(tmp_path, pack, path):
    from app.stacks.packs._javascript import PAGE_FACTS

    (tmp_path / "page.html").write_text(PAGE % _sheet(pack, path))
    runner = tmp_path / "measure.mjs"
    runner.write_text(
        f"import {{ chromium }} from {json.dumps(str(PLAYWRIGHT / 'index.mjs'))};\n"
        f"const browser = await chromium.launch({{ executablePath: {json.dumps(str(CHROMES[-1]))} }});\n"
        "const out = {};\n"
        "for (const scheme of ['light', 'dark']) {\n"
        "  const page = await browser.newPage({ viewport: { width: 375, height: 740 }, colorScheme: scheme });\n"
        f"  await page.goto('file://' + {json.dumps(str(tmp_path / 'page.html'))});\n"
        f"  out[scheme] = await page.evaluate({PAGE_FACTS});\n"
        "  out[scheme].items = await page.getByRole('listitem').count();\n"
        "  out[scheme].named = await page.getByLabel('Title', { exact: true }).count();\n"
        "  await page.close();\n"
        "}\n"
        "console.log(JSON.stringify(out));\nawait browser.close();\n"
    )
    done = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=90)
    found = json.loads(done.stdout.strip().splitlines()[-1])

    for scheme in ("light", "dark"):
        assert found[scheme]["pageWider"] == 0, found[scheme]["overflowing"]
        assert [pair for pair in found[scheme]["colours"] if pair["below"]] == [], scheme
        assert found[scheme]["items"] == 2 and found[scheme]["named"] == 1
        assert "--color-text" in found[scheme]["declared"]
