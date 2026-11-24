"""A field the brief does not refuse empty is kept when empty, and the harness asks every create and replace write so.

Measured on five scored runs of five stacks (LF.1273): the brief refused only "a title that is missing or empty" and
gave a note as `{"id": <integer>, "title": <string>, "body": <string>}`; the specification said "body: string
(required)"; every product also refused an empty body with 400, and the hidden quality test that writes
`{"title": "gone", "body": ""}` failed on it. The harness probed only the other side - a field refused empty sent empty.

Here the compiled probe runs under real pytest against a small service, with only the sandbox replaced by a local
process; what the brief, the criteria and the specification refuse decides what is asked.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import types
from http.server import ThreadingHTTPServer
from dataclasses import asdict

import pytest

from app.acceptance import interface_contract as ic
from app.acceptance import probes_at_release, suite
from app.stacks import contract

BRIEF = textwrap.dedent('''
    # Product Brief: Notes API
    ## Interface
    - JSON over HTTP. A note is `{"id": <integer>, "title": <string>, "body": <string>}`.
    - `POST /notes` with `{"title": ..., "body": ...}` creates a note and answers 201 with the note.
    - `GET /notes/{id}` answers 200 with the note, or 404 when there is none.
    - `PUT /notes/{id}` with `{"title": ..., "body": ...}` replaces both and answers 200 with the note, or 404.
    - A title that is missing or empty is refused with 400 or 422, and nothing is stored.
    ## Acceptance Criteria
    - Invalid input is refused without storing anything
''')
SPECIFICATION = "## Data contracts\n- Note: id: integer; title: string (required, non-empty); body: string (required)\n"
CONTRACT = ["AC-1 POST /notes -> 201", "AC-2 PUT /notes/{id} -> 200 or 404", "AC-3 GET /notes/{id} -> 200 or 404"]

SERVICE = textwrap.dedent('''
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import pytest

    NOTES = {}
    KEEPS_AN_EMPTY_BODY = %r
    ANSWERS_THE_BODY_AS = %r

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _answer(self, status, body=None):
            data = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _note(self):
            body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
            if not str(body.get("title") or "").strip():
                return None
            if not KEEPS_AN_EMPTY_BODY and not str(body.get("body") or "").strip():
                return None
            return body

        def _shown(self, note):
            return {**note, "body": ANSWERS_THE_BODY_AS} if ANSWERS_THE_BODY_AS is not None and not note["body"] else note

        def do_GET(self):
            note = NOTES.get(int(self.path.rsplit("/", 1)[-1]))
            self._answer(200, self._shown(note)) if note else self._answer(404, {"detail": "none"})

        def do_POST(self):
            body = self._note()
            if body is None:
                return self._answer(400, {"detail": "title and body are required"})
            note = {"id": len(NOTES) + 1, "title": body["title"], "body": body.get("body", "")}
            NOTES[note["id"]] = note
            self._answer(201, self._shown(note))

        def do_PUT(self):
            note_id = int(self.path.rsplit("/", 1)[-1])
            body = self._note()
            if body is None:
                return self._answer(400, {"detail": "title and body are required"})
            NOTES[note_id] = {"id": note_id, "title": body["title"], "body": body.get("body", "")}
            self._answer(200, self._shown(NOTES[note_id]))

    @pytest.fixture(scope="session")
    def base_url():
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}"
        server.shutdown()
''')


def _a_notes_product(root, monkeypatch, *, keeps_an_empty_body, answers_the_body_as=None,
                     specification=SPECIFICATION, criteria=("A title that is missing or empty is refused with 400 or 422",)):
    """A locked notes product on the pytest probe runner; the sandbox is a local pytest run."""
    project = root / "notes-api"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "conftest.py").write_text(SERVICE % (keeps_an_empty_body, answers_the_body_as))
    (root / "docs").mkdir()
    (root / "docs" / "technical_specification.md").write_text(specification)
    suite._save_state(root, {  # noqa: SLF001 - the lock's own record
        "interface_contract": [asdict(c) for c in ic.parse(CONTRACT)[0]],
        "interface_contract_bodies": [{"title": "Milk", "body": "two"}],
        "criteria": [{"id": f"AC-{n}", "text": text, "source": "brief"} for n, text in enumerate(criteria, start=9)],
    })
    monkeypatch.setattr(contract, "the_pack", lambda _root: (types.SimpleNamespace(probe_runner="pytest"),
                                                             {"project": "notes-api"}))

    def sandbox(argv, _kind, project_name):
        done = subprocess.run([sys.executable, *argv[1:]], cwd=root / project_name, capture_output=True, text=True,
                              timeout=120)
        return {"exit_code": done.returncode, "stdout": done.stdout, "stderr": done.stderr}

    monkeypatch.setattr(suite, "_sandbox_runner", lambda _root: sandbox)
    return sandbox


def _a_green_round(root):
    from app.graph import workflow

    state = {"repository": types.SimpleNamespace(root_path=str(root)), "document": types.SimpleNamespace(text=BRIEF)}
    result = types.SimpleNamespace(defects=[], model_copy=lambda update: types.SimpleNamespace(**update))
    return workflow._with_a_kept_empty_defect(state, result, None).defects


def test_a_product_refusing_an_empty_body_the_brief_keeps_gets_one_defect_naming_body(tmp_path, monkeypatch):
    _a_notes_product(tmp_path, monkeypatch, keeps_an_empty_body=False)

    raised = _a_green_round(tmp_path)

    assert len(raised) == 1
    said = raised[0].description
    assert said.startswith("A write refuses a field the brief keeps when empty:")
    assert "`POST /notes` with an empty `body` answered 400" in said
    assert "`PUT /notes/{id}` with an empty `body` answered 400" in said
    assert "only `title` empty" in said and "`title` answered" not in said
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", said, re.I)


def test_a_product_keeping_an_empty_body_gets_no_defect(tmp_path, monkeypatch):
    _a_notes_product(tmp_path, monkeypatch, keeps_an_empty_body=True)

    assert _a_green_round(tmp_path) == []


def test_an_empty_body_taken_but_answered_back_otherwise_is_a_finding(tmp_path, monkeypatch):
    run = _a_notes_product(tmp_path, monkeypatch, keeps_an_empty_body=True, answers_the_body_as="(no body)")

    found = ic.kept_empty_errors(tmp_path, BRIEF, runner=run)

    assert sorted((c.method, c.emptied, status) for c, status in found) == [("POST", "body", 201), ("PUT", "body", 200)]
    assert "answered 201 but gave `body` back as something else" in ic.kept_empty_description(found, ["title"])


def test_the_finding_is_settled_by_asking_again_and_still_blocks_at_release(tmp_path, monkeypatch):
    run = _a_notes_product(tmp_path, monkeypatch, keeps_an_empty_body=False)
    description = _a_green_round(tmp_path)[0].description

    gaps = probes_at_release.what_the_probes_still_find(tmp_path, runner=run)
    raised_again = ic.still_raised(tmp_path, description, runner=run)
    conftest = tmp_path / "notes-api" / "acceptance" / "conftest.py"
    conftest.write_text(conftest.read_text().replace("KEEPS_AN_EMPTY_BODY = False", "KEEPS_AN_EMPTY_BODY = True"))
    raised_after_the_fix = ic.still_raised(tmp_path, description, runner=run)

    assert any("A write refuses a field the brief keeps when empty:" in gap for gap in gaps)
    assert (raised_again, raised_after_the_fix) == (True, False)


WRITES = ic.parse(["AC-1 POST /notes -> 201", "AC-2 PUT /notes/{id} -> 200 or 404"])[0]


def _asked(bodies, brief_texts, specification=""):
    asked, _ = ic.kept_empty_checks(WRITES, bodies, brief_texts, specification)
    return sorted({(c.method, c.emptied) for c in asked})


def test_the_measured_brief_asks_each_write_to_keep_an_empty_body():
    assert _asked([{"title": "Milk", "body": "two"}], [BRIEF], SPECIFICATION) == [("POST", "body"), ("PUT", "body")]


@pytest.mark.parametrize("rule", [
    "A title or body that is missing or empty is refused with 400 or 422.",
    "The title and the body must not be empty.",
])
def test_a_brief_refusing_title_and_body_empty_asks_neither_to_be_kept(rule):
    assert _asked([{"title": "Milk", "body": "two"}], [rule]) == []


def test_a_sign_up_body_never_has_its_credentials_sent_empty():
    bodies = [{"username": "ann", "password": "secret1", "email": "ann@example.com", "display_name": "Ann"},
              {"title": "Milk", "body": "two"}]
    brief = ["A missing or empty username or password is refused with 400 or 422", "A title that is missing or empty is refused"]

    assert {field for _, field in _asked(bodies, brief)} == {"body", "display_name"}


@pytest.mark.parametrize("specification", [
    "- body: string, 1-2000 characters",
    '- Note request: {"title": {"type": "string"}, "body": {"type": "string", "minLength": 1}}',
    "- body: string (required); the body must be at least 1 character long",
])
def test_a_field_the_specification_holds_to_a_least_length_is_not_asked(specification):
    assert _asked([{"title": "Milk", "body": "two"}], [BRIEF], specification) == []


def test_a_brief_refusing_no_field_empty_asks_nothing():
    assert _asked([{"title": "Milk", "body": "two"}], ["Create a note with a title and a body"]) == []


#: Just enough of Playwright's `test`, `expect` and `request` to run the compiled spec in plain Node against a service.
PLAYWRIGHT_IN_NODE = textwrap.dedent("""
    const BASE = process.env.BASE;
    const cases = [];
    const test = (name, body) => cases.push([name, body]);
    test.skip = (skipped, why) => { if (skipped) throw { skipped: why }; };
    const expect = (value, said = '') => ({
      toBe: (want) => { if (value !== want) throw new Error(`${said}\\nExpected: ${JSON.stringify(want)}\\nReceived: ${JSON.stringify(value)}`); },
      toBeGreaterThanOrEqual: (want) => { if (!(value >= want)) throw new Error(`${said}\\nReceived: ${value}`); },
      toBeLessThan: (want) => { if (!(value < want)) throw new Error(`${said}\\nReceived: ${value}`); },
    });
    const request = { fetch: async (path, options) => {
      const answer = await fetch(BASE + path, { method: options.method, headers: { 'content-type': 'application/json' },
        body: typeof options.data === 'string' ? options.data : JSON.stringify(options.data) });
      const text = await answer.text();
      return { status: () => answer.status, ok: () => answer.ok, text: async () => text, json: async () => JSON.parse(text) };
    } };
    // THE SPEC
    const outcomes = [];
    for (const [name, body] of cases) {
      try { await body({ request }); outcomes.push([name, 'passed', '']); }
      catch (error) { outcomes.push([name, error.skipped ? 'skipped' : 'failed', String(error.skipped || error.message)]); }
    }
    console.log(JSON.stringify(outcomes));
""")


@pytest.mark.skipif(shutil.which("node") is None, reason="no node to run the compiled spec")
@pytest.mark.parametrize(("keeps", "answers_as", "outcome", "said"), [
    (False, None, "failed", "Received: 400"),
    (True, "(no body)", "failed", "READ BACK 20"),
    (True, None, "passed", ""),
])
def test_the_playwright_probe_wants_the_empty_body_taken_and_given_back(tmp_path, keeps, answers_as, outcome, said):
    service: dict = {}
    exec(SERVICE % (keeps, answers_as), service)  # noqa: S102 - the test's own service
    server = ThreadingHTTPServer(("127.0.0.1", 0), service["Handler"])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    asked, _ = ic.kept_empty_checks(WRITES, [{"title": "Milk", "body": "two"}], [BRIEF], SPECIFICATION)
    spec = ic.playwright_kept_empty_checks(asked).replace("import { test, expect } from '@playwright/test';", "")
    (tmp_path / "spec.mjs").write_text(PLAYWRIGHT_IN_NODE.replace("// THE SPEC", spec, 1))
    try:
        done = subprocess.run(["node", str(tmp_path / "spec.mjs")], capture_output=True, text=True, timeout=60,
                              env={**os.environ, "BASE": f"http://127.0.0.1:{server.server_address[1]}"})
    finally:
        server.shutdown()

    outcomes = json.loads(done.stdout.strip().splitlines()[-1])
    assert [o for _, o, _ in outcomes] == [outcome, outcome]
    assert all(said in message for _, _, message in outcomes)
