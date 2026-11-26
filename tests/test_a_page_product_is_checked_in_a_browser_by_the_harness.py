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


def _checked(tmp_path: Path, html: str, persists: bool, small_screens: bool = True, serve=_serve,
             controls=(("textbox", "Title"),)) -> list[SimpleNamespace]:
    (tmp_path / "node_modules" / "@playwright" / "test").mkdir(parents=True)
    (tmp_path / "node_modules" / "@playwright" / "test" / "package.json").write_text(
        json.dumps({"name": "@playwright/test", "type": "module", "main": "index.mjs"}))
    (tmp_path / "node_modules" / "@playwright" / "test" / "index.mjs").write_text(SHIM)
    (tmp_path / "spec.mjs").write_text(page_probe.playwright_page_checks([None], persists=persists, small_screens=small_screens,
                                                                    controls=controls))
    (tmp_path / "run.mjs").write_text(RUN)
    server = serve(html)
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

    assert [t.outcome for t in safe] == ["passed"] * 5, safe


@pytest.mark.skipif(shutil.which("node") is None or not CORE.is_file(), reason="no browser driver here")
def test_a_brief_that_never_asks_for_a_phone_is_not_held_to_its_width(tmp_path):
    found = _checked(tmp_path, UNSAFE, persists=True, small_screens=False)

    kinds = {f["kind"] for t in found if (f := page_probe.what_the_test_found(t)) is not None}
    assert "overflow" not in kinds and "markup_ran" in kinds, found


#: A form whose second field takes a web address and whose third an e-mail address (each told only by its name or
#: its label, typed as plain text), and a field outside the form that narrows the list to an exact tag.
A_FORM_WITH_AN_ADDRESS = """<!doctype html><html><head><meta name="viewport" content="width=device-width"></head><body>
<form id="f">
  <label for="t">Title</label><input id="t" type="text" name="title" required>
  <label for="u">URL</label><input id="u" type="text" name="url" required>
  <label for="c">Contact e-mail</label><input id="c" type="text">
  <label for="g">Tag</label><input id="g" type="text" name="tag">
  <button type="submit">Save</button>
</form>
<label for="narrow">Show only the tag</label><input id="narrow" type="text">
<p id="none"></p><ul id="l"></ul>
<script>
let items = [];
const shown = () => {
  const narrow = document.getElementById('narrow').value;
  const l = document.getElementById('l'); l.textContent = '';
  const kept = items.filter((item) => !narrow || item.tag === narrow);
  document.getElementById('none').textContent = kept.length ? '' : (narrow ? `nothing tagged "${narrow}"` : 'nothing yet');
  for (const item of kept) { const li = document.createElement('li'); li.textContent = item.title; l.appendChild(li); }
};
const load = async () => { items = await (await fetch('/api/items')).json(); shown(); };
document.getElementById('narrow').addEventListener('input', shown);
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = { title: document.getElementById('t').value, url: document.getElementById('u').value,
                 contact: document.getElementById('c').value, tag: document.getElementById('g').value };
  const answer = await fetch('/api/items', { method: 'POST', body: JSON.stringify(body) });
  if (answer.status !== 201) return;
  items.unshift(await answer.json());
  shown();
});
load();
</script></body></html>"""


def _serve_with_a_store(keeps: bool):
    """The page and its service: an item is refused (422) unless its address and e-mail look like ones; `keeps` False
    answers 201 but stores nothing, so the item is gone after a reload."""
    items: list[dict] = []

    def serve(html: str):
        class Service(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D401 - quiet
                pass

            def _answer(self, status: int, raw: bytes, kind: str = "application/json"):
                self.send_response(status)
                self.send_header("content-type", kind)
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):  # noqa: N802
                if self.path in ("/", "/index.html"):
                    self._answer(200, html.encode(), "text/html")
                elif self.path == "/api/items":
                    self._answer(200, json.dumps(items).encode())
                else:
                    self._answer(404, b"{}")

            def do_POST(self):  # noqa: N802
                item = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
                if not item.get("title") or not re.match(r"https?://", item.get("url", "")) or (
                        item.get("contact") and "@" not in item["contact"]):
                    self._answer(422, b'{"error": "invalid"}')
                    return
                if keeps:
                    items.insert(0, item)
                self._answer(201, json.dumps(item).encode())

        server = ThreadingHTTPServer(("127.0.0.1", 0), Service)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    return serve


def _the_reload_check(found: list[SimpleNamespace]) -> SimpleNamespace:
    return next(t for t in found if t.name.startswith("page check 4"))


@pytest.mark.skipif(shutil.which("node") is None or not CORE.is_file(), reason="no browser driver here")
def test_an_item_added_through_a_form_with_an_address_field_and_kept_passes_the_reload_check(tmp_path):
    """A kept item was reported lost: every text field on the page got the same words, so the address field held no
    address (the service refused the item) and a field outside the form narrowed the list."""
    found = _checked(tmp_path, A_FORM_WITH_AN_ADDRESS, persists=True, serve=_serve_with_a_store(keeps=True))

    assert _the_reload_check(found).outcome == "passed", found


@pytest.mark.skipif(shutil.which("node") is None or not CORE.is_file(), reason="no browser driver here")
def test_an_item_added_through_a_form_with_an_address_field_and_dropped_is_found_not_kept(tmp_path):
    found = _checked(tmp_path, A_FORM_WITH_AN_ADDRESS, persists=True, serve=_serve_with_a_store(keeps=False))

    assert (page_probe.what_the_test_found(_the_reload_check(found)) or {}).get("kind") == "not_kept", found


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


#: LF.1590. A page product as it was delivered: each item of its list showed a control the contract names, labelled
#: by the label element around it, and that label element was given `aria-label` with the same name. Its own suite
#: found the control by its role and passed; three hidden tests finding it by its label failed on two matches.
CAPTURED = Path(__file__).resolve().parent / "captured" / "page-a-label-also-given-its-control-s-name"
#: The product's interface contract, as its specification wrote it and the lock kept it.
CONTRACT_LINES = [
    'AC-6 page / textbox "Title"', 'AC-6 page / textbox "Description"', 'AC-6 page / button "Add task"',
    'AC-5 page / button "All"', 'AC-5 page / button "Active"', 'AC-5 page / button "Completed"',
    'AC-9 page / checkbox "Done"', 'AC-3 page / button "Edit"', 'AC-3 page / textbox "Edit title"',
    'AC-10 page / button "Save"', 'AC-4 page / button "Delete"',
]
#: The line of the captured page that gives the label element its control's name.
SECOND_LABEL = "doneLabel.setAttribute('aria-label', 'Done');"
#: Two records the page already holds when it opens, in its own storage, so the probe's item is the third.
TWO_STORED = (
    "<script>localStorage.setItem('simple-to-do-list.tasks', localStorage.getItem('simple-to-do-list.tasks') || "
    "JSON.stringify([{ id: 'a', title: 'First', description: '', completed: false },"
    " { id: 'b', title: 'Second', description: '', completed: true }]));</script>"
)


def _serve_the_captured_page(*, second_label: bool, stored: bool):
    """The captured page's own files; without `second_label` its one line giving the label element the name is gone."""
    script = (CAPTURED / "app.js").read_text(encoding="utf-8")
    assert SECOND_LABEL in script
    files = {
        "/": (CAPTURED / "index.html").read_text(encoding="utf-8").replace(
            '<script type="module"', (TWO_STORED if stored else "") + '<script type="module"'),
        "/app.js": script if second_label else script.replace(SECOND_LABEL, ""),
        "/storage.js": (CAPTURED / "storage.js").read_text(encoding="utf-8"),
        "/task-store.js": (CAPTURED / "task-store.js").read_text(encoding="utf-8"),
    }

    def serve(_html: str):
        class Page(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D401 - quiet
                pass

            def do_GET(self):  # noqa: N802
                path = "/" if self.path in ("/", "/index.html") else self.path
                raw = files.get(path, "not here").encode()
                self.send_response(200 if path in files else 404)
                self.send_header("content-type", "text/html" if path == "/" else "text/javascript")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    return serve


def _the_label_check(found: list[SimpleNamespace]) -> SimpleNamespace:
    return next(t for t in found if t.name.startswith("page check 5"))


def _the_contract_s_controls():
    return page_probe.controls_on_the_page(ic.parse(CONTRACT_LINES)[0])


@pytest.mark.skipif(shutil.which("node") is None or not CORE.is_file(), reason="no browser driver here")
@pytest.mark.parametrize("stored, where", [(False, "page"), (True, "item")])
def test_a_label_element_given_its_control_s_name_is_a_second_element_carrying_that_label(tmp_path, stored, where):
    found = _checked(tmp_path, "", persists=True, controls=_the_contract_s_controls(),
                     serve=_serve_the_captured_page(second_label=True, stored=stored))

    finding = page_probe.what_the_test_found(_the_label_check(found)) or {}
    assert finding.get("kind") == "repeated_label", found
    assert [(c["role"], c["name"], c["count"], c["where"]) for c in finding["controls"]] == [
        ("checkbox", "Done", 2, where)], finding
    said = " ".join(finding["controls"][0]["carriers"])
    assert '<label class="done-label"> by aria-label' in said and "<input> by the label element around it" in said


@pytest.mark.skipif(shutil.which("node") is None or not CORE.is_file(), reason="no browser driver here")
def test_the_same_control_once_in_each_of_several_items_is_no_repeat(tmp_path):
    """The captured page without its second label: three items each show the control once, and pass."""
    found = _checked(tmp_path, "", persists=True, controls=_the_contract_s_controls(),
                     serve=_serve_the_captured_page(second_label=False, stored=True))

    assert _the_label_check(found).outcome == "passed", found


def test_the_controls_asked_are_the_contract_s_page_controls_once_each():
    lines = [*CONTRACT_LINES, 'AC-9 page / checkbox "Done"', 'AC-2 page /settings textbox "Email"',
             'AC-7 page / alert "Saved"', "AC-1 GET /api/items -> 200"]

    assert page_probe.controls_on_the_page(ic.parse(lines)[0]) == [
        ("textbox", "Title"), ("textbox", "Description"), ("button", "Add task"), ("button", "All"),
        ("button", "Active"), ("button", "Completed"), ("checkbox", "Done"), ("button", "Edit"),
        ("textbox", "Edit title"), ("button", "Save"), ("button", "Delete")]


def test_a_round_asks_the_locked_contract_s_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGE_PROBE", "on")
    _a_page_project(tmp_path, monkeypatch)
    ic.record_at_lock(tmp_path, ['AC-9 page / checkbox "Done"', "AC-1 GET /api/items -> 200"])
    specs = []

    def report(project, name, probe, web, run, compiled_by="checks", bodies=None):
        specs.append(probe[compiled_by](web))
        return SimpleNamespace(found=True, tests=[])

    monkeypatch.setattr(ic, "_the_probe_s_report", report)

    page_probe.page_errors(tmp_path, "A list kept on the page.", runner=lambda *a, **k: {})

    assert 'const CONTROLS = [{"role": "checkbox", "name": "Done"}];' in specs[0]


#: What check 5 throws, as the spec words it, for a field labelled twice within one item.
REPEATED = {"kind": "repeated_label", "controls": [
    {"role": "textbox", "name": "Email", "count": 2, "where": "item",
     "carriers": ['<label class="field-label"> by aria-label', "<input> by the label element around it"]}]}


def test_the_defect_names_the_control_where_it_is_repeated_and_what_carries_the_label(tmp_path, monkeypatch):
    described = page_probe.page_description([REPEATED])

    assert described.startswith(page_probe.PAGE_CHECK_FAILED)
    assert 'textbox "Email": 2 elements within one item' in described
    assert '<label class="field-label"> by aria-label' in described
    assert "the only element carrying its label within its item" in described
    assert not BANNED.search(described)
    _a_page_project(tmp_path, monkeypatch)
    monkeypatch.setenv("PAGE_PROBE", "on")
    monkeypatch.setattr(ic, "_the_probe_s_report", lambda *a, **k: SimpleNamespace(found=True, tests=[SimpleNamespace(
        name="page check 5: each control", outcome="failed", message=f"Error: {page_probe.MARKER} {json.dumps(REPEATED)}")]))
    assert page_probe.still_raised(tmp_path, described, runner=lambda *a, **k: {}) is True
