"""The built page shows the empty, busy and failed states its specification names (PQ.8 proof, behind
`INTERFACE_STATES_AS_CRITERIA`).

The specification is asked to name each state as a line with a role and the words shown; nothing then looked at the
built page. Read in stored products: the best page of the set showed nothing on a failed request and no busy state
while one ran. The page check now loads the page again with its requests held back and with them failing, and a state
the page shows in none of those, nor anywhere in its code, is a defect for the interface's builder.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.agents import interface_states
from app.analysis import interface_style_checks
from app.graph import acceptance_nodes
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT = ROOT / "scripts" / "ui" / "node_modules" / "playwright-core"
CHROMES = sorted(Path(os.path.expanduser("~/.cache/ms-playwright")).glob(
    "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))

DESIGN = [
    'Empty: the notes view shows an element with role "status" reading "No notes yet"',
    'Busy: while the notes load, role "status" reads "Loading notes"',
    'Failed: role "alert" reads "Could not load notes. Try again."',
    "The notes view lists each note with its title.",
]


def _report(shows: str = '- status: No notes yet', requests: int = 1, busy: str = "- status: Loading notes",
            failed: str = "- alert: Could not load notes. Try again.") -> dict:
    return {"shows": shows, "facts": {"states": {"requests": requests, "busy": busy, "failed": failed}}}


class TestWhatThePageShows:
    def test_a_page_that_shows_each_state_is_missing_none(self):
        assert interface_states.not_shown(DESIGN, _report(), "") == []

    def test_a_failure_the_page_never_shows_is_named(self):
        missing = interface_states.not_shown(DESIGN, _report(failed="- heading \"Notes\""), "")

        assert len(missing) == 1 and missing[0].startswith('Failed: "Could not load notes. Try again."')
        assert "role `alert`" in missing[0]

    def test_a_state_shown_under_another_role_is_named(self):
        missing = interface_states.not_shown(DESIGN, _report(busy="- paragraph: Loading notes"), "")

        assert missing == ['Busy: "Loading notes" is shown, but no element has the role `status` the specification names']

    def test_a_state_the_page_cannot_be_put_in_is_looked_for_in_its_code(self):
        """No request at load: the busy and failed states are reached later, so the page's code decides."""
        report = _report(requests=0, busy="", failed="")

        assert interface_states.not_shown(DESIGN, report, "status.textContent = 'Loading notes';\n"
                                                          "alert.textContent = 'Could not load notes. Try again.';") == []
        assert [line.split(":")[0] for line in interface_states.not_shown(DESIGN, report, "")] == ["Busy", "Failed"]

    def test_records_already_listed_leave_the_empty_state_to_the_code(self):
        report = _report(shows="- list:\n  - listitem: First")

        assert interface_states.not_shown(DESIGN, report, "") == ['Empty: "No notes yet" (role `status`) is not shown '
                                                                  "anywhere in the page's code"]
        assert interface_states.not_shown(DESIGN, report, "<p role=status>No notes yet</p>") == []

    def test_case_and_punctuation_do_not_matter(self):
        assert interface_states.not_shown(DESIGN, _report(failed="- alert: could not load notes - try again"), "") == []


def _a_page_product(root: Path, report: dict) -> None:
    contract.write(root, pack_named("browser-javascript"), "notes", "Notes")
    (root / "notes" / "test-results").mkdir(parents=True)
    (root / "notes" / "test-results" / "page-load.json").write_text(json.dumps(report))
    (root / "notes" / "index.html").write_text("<!doctype html><html><body><h1>Notes</h1></body></html>")
    saved = root / suite.RESULT_FILE
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"ran": True, "shows": report.get("shows")}))


def _state(root: Path) -> dict:
    return {"repository": SimpleNamespace(root_path=str(root)),
            "technical_specification": SimpleNamespace(interface_design=DESIGN)}


def test_with_the_switch_on_a_state_not_shown_is_a_defect_for_the_interface_s_builder(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERFACE_STATES_AS_CRITERIA", "on")
    _a_page_product(tmp_path, _report(failed="- heading \"Notes\""))

    raised = [d for d in acceptance_nodes.interface_defects(_state(tmp_path))
              if d.description.startswith(interface_style_checks.STATES_NOT_SHOWN)]

    assert len(raised) == 1 and raised[0].severity == "major" and raised[0].owner == "ui_ux"
    assert "Could not load notes" in raised[0].actual_behavior
    for text in (raised[0].description, raised[0].expected_behavior, raised[0].reproduction_steps):
        assert not BANNED.search(text)


def test_with_the_switch_off_nothing_is_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERFACE_STATES_AS_CRITERIA", "off")
    _a_page_product(tmp_path, _report(failed="- heading \"Notes\""))

    assert not [d for d in acceptance_nodes.interface_defects(_state(tmp_path))
                if d.description.startswith(interface_style_checks.STATES_NOT_SHOWN)]


SERVER_PAGE = """<!doctype html><html><body><h1>Notes</h1><p id="state"></p><ul id="list"></ul><script>
const state = document.getElementById('state');
state.setAttribute('role', 'status');
state.textContent = 'Loading notes';
fetch('/api/notes').then((r) => r.json()).then((notes) => {
  state.textContent = notes.length ? '' : 'No notes yet';
}).catch(() => {
  state.setAttribute('role', 'alert');
  state.textContent = 'Could not load notes. Try again.';
});
</script></body></html>"""


@pytest.mark.skipif(not (PLAYWRIGHT.is_dir() and CHROMES and shutil.which("node")),
                    reason="needs node, playwright-core and a headless Chromium")
def test_the_page_check_holds_back_and_fails_the_page_s_requests(tmp_path):
    from app.stacks.packs import _javascript

    script = _javascript.page_check("/")
    states_of = script[script.index("async function statesOf"):script.index("export default async function pageCheck")]
    runner = tmp_path / "states.mjs"
    runner.write_text(
        "import http from 'node:http';\n"
        f"import {{ chromium }} from {json.dumps(str(PLAYWRIGHT / 'index.mjs'))};\n"
        + states_of
        + f"const page = {json.dumps(SERVER_PAGE)};\n"
        "const server = http.createServer((req, res) => {\n"
        "  if (req.url === '/api/notes') { res.setHeader('content-type', 'application/json'); res.end('[]'); return; }\n"
        "  res.setHeader('content-type', 'text/html'); res.end(page);\n"
        "});\n"
        "await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));\n"
        f"const browser = await chromium.launch({{ executablePath: {json.dumps(str(CHROMES[-1]))} }});\n"
        "const found = await statesOf(browser, `http://127.0.0.1:${server.address().port}/`);\n"
        "console.log(JSON.stringify(found));\n"
        "await browser.close();\nserver.close();\nprocess.exit(0);\n"
    )
    done = subprocess.run(["node", str(runner)], capture_output=True, text=True, timeout=90)
    found = json.loads(done.stdout.strip().splitlines()[-1])

    assert found["requests"] >= 1
    assert "status" in found["busy"] and "Loading notes" in found["busy"]
    assert "alert" in found["failed"] and "Could not load notes" in found["failed"]
