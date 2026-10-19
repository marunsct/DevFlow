"""The page check measures controls drawn over each other and controls too small to tap (Initiative B).

A model sees the markup, never the rendered boxes. Runs spent model calls moving
CSS padding without knowing where things landed, and action controls wrapped
over each other at a phone's width until a test happened to look. The page check
the suite runs before any test now measures both at 375px and prints them where
the agents read the suite's output.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.acceptance import suite
from app.stacks.packs import _javascript

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "scripts" / "ui" / "node_modules" / "playwright-core"
CHROME = Path(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"))

PAGE = """<!doctype html><html><body style="margin:0">
<button style="position:absolute;left:10px;top:10px;width:120px;height:40px">Save</button>
<button style="position:absolute;left:30px;top:20px;width:120px;height:40px">Delete</button>
<button style="position:absolute;left:10px;top:100px;width:16px;height:16px" aria-label="Close"></button>
<p style="margin-top:200px">Read the <a href="#x">terms</a> first.</p>
</body></html>"""


def _the_measurement() -> str:
    script = _javascript.page_check("/")
    start = script.index("Object.assign(layout, await page.evaluate(") + len("Object.assign(layout, await page.evaluate(")
    end = script.index("}));", start) + 1
    return script[start:end]


def test_the_report_s_findings_are_read(tmp_path):
    report = tmp_path / "page.json"
    report.write_text(json.dumps({"layout": {"overlaps": ['button "Save" and button "Delete"'],
                                             "smallTargets": ['button "Close" is 16x16px']}}))

    assert suite._read_layout_findings(report) == (['button "Save" and button "Delete"'], ['button "Close" is 16x16px'])
    assert suite._read_layout_findings(None) == ([], [])


def test_the_page_check_prints_them_for_the_agents():
    script = _javascript.page_check("/")
    assert "drawn over each other" in script and "too small to tap (under 24x24px)" in script


@pytest.mark.skipif(not (UI.is_dir() and CHROME.is_file() and shutil.which("node")), reason="needs node, playwright-core and a headless Chromium")
def test_a_browser_measures_them(tmp_path):
    (tmp_path / "page.html").write_text(PAGE)
    runner = tmp_path / "measure.mjs"
    runner.write_text(
        f"import {{ chromium }} from {json.dumps(str(UI / 'index.mjs'))};\n"
        f"const browser = await chromium.launch({{ executablePath: {json.dumps(str(CHROME))} }});\n"
        "const page = await browser.newPage({ viewport: { width: 375, height: 740 } });\n"
        f"await page.goto('file://' + {json.dumps(str(tmp_path / 'page.html'))});\n"
        f"const found = await page.evaluate({_the_measurement()});\n"
        "console.log(JSON.stringify(found));\nawait browser.close();\n"
    )
    done = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=60)
    found = json.loads(done.stdout.strip().splitlines()[-1])

    assert found["overlaps"] == ['button "Save" and button "Delete"']
    assert found["smallTargets"] == ['button "Close" is 16x16px']


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_rendered_page_check_is_valid_javascript(tmp_path):
    """Its own browser test ran only the measurement; a message string broken
    by an escape was found by parsing the whole script."""
    script = tmp_path / "page-check.mjs"
    script.write_text(_javascript.page_check("/"))

    done = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True, timeout=60)

    assert done.returncode == 0, done.stderr[-600:]
