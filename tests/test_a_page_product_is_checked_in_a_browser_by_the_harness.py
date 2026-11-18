"""A page product is checked in a browser by the harness's own spec: markup typed is shown as text, no console error
while an item is added, it fits a 360px screen, and what the brief says persists outlives a reload.

Deep review 2026-11-18, item B5: page products had none of these checks; the pack's page check only loads the page.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import interface_contract as ic
from app.acceptance import page_probe
from app.agents.specialists import SpecialistOutput
from app.graph import workflow
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The browser driver `scripts/ui` installs (`npm ci` there); the test is skipped where it is not installed.
CORE = Path(os.environ.get("PLAYWRIGHT_CORE_ENTRY") or Path(__file__).resolve().parents[1] / "scripts" / "ui"
            / "node_modules" / "playwright-core" / "index.mjs")

UNSAFE = """<!doctype html><html><head><meta name="viewport" content="width=device-width"></head><body>
<form id="f"><input id="t" type="text" aria-label="Title"><button type="submit">Add</button></form>
<div style="width:600px">a wide banner</div><ul id="l"></ul>
<script>
document.getElementById('f').addEventListener('submit', (e) => {
  e.preventDefault();
  const li = document.createElement('li');
  li.innerHTML = document.getElementById('t').value;
  document.getElementById('l').appendChild(li);
  console.error('could not save');
});
</script></body></html>"""

SAFE = """<!doctype html><html><head><meta name="viewport" content="width=device-width"></head><body>
<form id="f"><input id="t" type="text" aria-label="Title"><button type="submit">Add</button></form><ul id="l"></ul>
<script>
const shown = () => { const l = document.getElementById('l'); l.textContent = '';
  for (const text of JSON.parse(localStorage.getItem('items') || '[]')) {
    const li = document.createElement('li'); li.textContent = text; l.appendChild(li); } };
document.getElementById('f').addEventListener('submit', (e) => {
  e.preventDefault();
  const items = JSON.parse(localStorage.getItem('items') || '[]');
  items.push(document.getElementById('t').value);
  localStorage.setItem('items', JSON.stringify(items));
  shown();
});
shown();
</script></body></html>"""

SHIM = """class Skip extends Error {}
export const test = (title, fn) => { globalThis.__tests.push({ title, fn }); };
test.skip = (condition, reason) => { if (condition) throw new Skip(reason); };
export const expect = () => { throw new Error('not used by the page checks'); };
"""

RUN = """globalThis.__tests = [];
const { chromium } = await import(process.argv[2]);
await import('./spec.mjs');
let browser;
try {
  browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {});
} catch (error) {
  console.log('NO BROWSER');
  process.exit(0);
}
const results = [];
for (const t of globalThis.__tests) {
  const context = await browser.newContext({ baseURL: process.argv[3] });
  const page = await context.newPage();
  try { await t.fn({ page }); results.push({ name: t.title, outcome: 'passed' }); }
  catch (e) { results.push({ name: t.title, outcome: e.constructor.name === 'Skip' ? 'skipped' : 'failed', message: String(e.message) }); }
  await context.close();
}
await browser.close();
console.log(JSON.stringify(results));
"""


def _serve(html: str):
    class Page(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D401 - quiet
            pass

        def do_GET(self):  # noqa: N802
            raw = html.encode() if self.path in ("/", "/index.html") else b"not here"
            self.send_response(200 if self.path in ("/", "/index.html") else 404)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _checked(tmp_path: Path, html: str, persists: bool, small_screens: bool = True) -> list[SimpleNamespace]:
    (tmp_path / "node_modules" / "@playwright" / "test").mkdir(parents=True)
    (tmp_path / "node_modules" / "@playwright" / "test" / "package.json").write_text(
        json.dumps({"name": "@playwright/test", "type": "module", "main": "index.mjs"}))
    (tmp_path / "node_modules" / "@playwright" / "test" / "index.mjs").write_text(SHIM)
    (tmp_path / "spec.mjs").write_text(page_probe.playwright_page_checks([None], persists=persists, small_screens=small_screens))
    (tmp_path / "run.mjs").write_text(RUN)
    server = _serve(html)
    try:
        done = subprocess.run(["node", "run.mjs", CORE.as_uri(), f"http://127.0.0.1:{server.server_port}"],
                              cwd=tmp_path, capture_output=True, text=True, timeout=180)
    finally:
        server.shutdown()
    assert done.returncode == 0, done.stderr
    if done.stdout.strip().endswith("NO BROWSER"):
        pytest.skip("no browser build for this driver here")
    return [SimpleNamespace(**r) for r in json.loads(done.stdout.strip().splitlines()[-1])]


@pytest.mark.skipif(shutil.which("node") is None or not CORE.is_file(), reason="no browser driver here")
def test_a_page_failing_each_check_is_found_and_one_keeping_them_passes(tmp_path):
    (tmp_path / "unsafe").mkdir()
    (tmp_path / "safe").mkdir()

    unsafe = _checked(tmp_path / "unsafe", UNSAFE, persists=True)

    kinds = {f["kind"] for t in unsafe if (f := page_probe.what_the_test_found(t)) is not None}
    assert kinds == {"markup_ran", "errors", "overflow", "not_kept"}, unsafe

    safe = _checked(tmp_path / "safe", SAFE, persists=True)

    assert [t.outcome for t in safe] == ["passed"] * 4, safe


@pytest.mark.skipif(shutil.which("node") is None or not CORE.is_file(), reason="no browser driver here")
def test_a_brief_that_never_asks_for_a_phone_is_not_held_to_its_width(tmp_path):
    found = _checked(tmp_path, UNSAFE, persists=True, small_screens=False)

    kinds = {f["kind"] for t in found if (f := page_probe.what_the_test_found(t)) is not None}
    assert "overflow" not in kinds and "markup_ran" in kinds, found


def test_the_phone_width_is_asked_only_when_the_brief_asks_for_small_screens(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGE_PROBE", "on")
    asked = []
    monkeypatch.setattr(page_probe, "playwright_page_checks", lambda web, **kw: asked.append(kw) or "")
    _a_page_project(tmp_path, monkeypatch)
    from app.acceptance import interface_contract as ic
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(False))

    page_probe.page_errors(tmp_path, "A list of notes kept on the page.", runner=lambda *a, **k: {})
    page_probe.page_errors(tmp_path, "A list of notes that works on a phone screen.", runner=lambda *a, **k: {})

    assert [kw["small_screens"] for kw in asked] == [False, True]


def test_the_brief_decides_whether_a_reload_is_asked():
    assert page_probe.the_brief_says_data_persists("Notes persist across page reloads.")
    assert page_probe.the_brief_says_data_persists("Items are saved in localStorage.")
    assert not page_probe.the_brief_says_data_persists("A calculator that adds two numbers.")


def _a_page_project(tmp_path, monkeypatch):
    pack = SimpleNamespace(probe_runner="playwright", runtime_report="test-results/page-load.json")
    monkeypatch.setattr(contract, "the_pack", lambda root: (pack, {"project": "app"}))
    (tmp_path / "app").mkdir()


def _reporting(failed: bool):
    def report(project, name, probe, web, run, compiled_by="checks", bodies=None):
        probe[compiled_by](web)
        found = json.dumps({"kind": "markup_ran"})
        test = SimpleNamespace(name="page check 1: markup typed into a text field is shown as text",
                               outcome="failed" if failed else "passed",
                               message=f"Error: {page_probe.MARKER} {found}" if failed else "")
        return SimpleNamespace(found=True, tests=[test])
    return report


def test_a_green_round_raises_what_the_page_checks_find_behind_the_switch_and_they_settle_it(tmp_path, monkeypatch):
    _a_page_project(tmp_path, monkeypatch)
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(failed=True))  # the spec's run in the sandbox
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)),
             "document": SimpleNamespace(text="Notes persist across reloads.")}
    green = SpecialistOutput(changed_files=[], defects=[], decisions=[])
    milestone = SimpleNamespace(delegated_tasks=[], milestone_scope=[])

    monkeypatch.setenv("PAGE_PROBE", "off")
    assert workflow._with_a_page_check_defect(state, green, milestone).defects == []
    monkeypatch.setenv("PAGE_PROBE", "on")
    raised = workflow._with_a_page_check_defect(state, green, milestone).defects

    assert len(raised) == 1 and raised[0].description.startswith(page_probe.PAGE_CHECK_FAILED)
    assert "markup typed into a text field and sent was run as code" in raised[0].description
    assert not BANNED.search(" ".join([raised[0].description, raised[0].reproduction_steps,
                                       raised[0].expected_behavior, raised[0].actual_behavior]))
    assert ic.still_raised(tmp_path, raised[0].description, runner=lambda *a: {}) is True
    monkeypatch.setattr(ic, "_the_probe_s_report", _reporting(failed=False))
    assert ic.still_raised(tmp_path, raised[0].description, runner=lambda *a: {}) is False


def test_a_product_without_a_page_is_not_probed(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGE_PROBE", "on")
    service = SimpleNamespace(probe_runner="playwright", runtime_report="")
    monkeypatch.setattr(contract, "the_pack", lambda root: (service, {"project": "app"}))

    assert page_probe.page_errors(tmp_path, "brief", runner=lambda *a: {}) is None
