"""The audit's last section answers what the transcript cannot: does it work?

Every run in this harness's history that shipped something broken shipped it
with a green suite. Run 0c5aabdb had no HTML at all; run 0afef410 had HTML and
JavaScript that never met; run 7e960f06 had a page with no `<script>` tag. In
each case the transcript looked fine - the cost numbers were good and the
failures were few - because nothing in a transcript says whether the product
runs.

So the script takes an optional workspace and prints what the cross-file checks
say about it, and says plainly whether anything blocks.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_run.py"

TRANSCRIPT = (
    '{"kind": "model_request", "stage": "specialist_ui_ux_0", "messages": []}\n'
    '{"kind": "tool_call", "stage": "specialist_ui_ux_0", "tool": "write_artifact", "args": {}}\n'
    '{"kind": "tool_result", "stage": "specialist_ui_ux_0", "tool": "write_artifact", "content": "{\\"status\\": \\"written\\"}"}\n'
)

DEAD_PAGE = (
    "<!DOCTYPE html><html><body>"
    "<input id='task-input' /><button id='add-btn'>Add</button>"
    "<ul id='task-list'></ul>"
    "<script type='module' src='app.js'></script>"
    "</body></html>"
)
PURE = "export function addTask(t) { return t; }\nexport function getTasks() { return []; }\n"
WIRED = PURE + "document.getElementById('add-btn').addEventListener('click', () => {});\n"


@pytest.fixture
def run_audit(tmp_path: Path):
    transcript = tmp_path / "run.jsonl"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")

    def go(files: dict[str, str] | None) -> str:
        argv = [sys.executable, str(SCRIPT), str(transcript)]
        if files is not None:
            workspace = tmp_path / "ws"
            project = workspace / "app"
            project.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (project / name).write_text(content, encoding="utf-8")
            argv.append(str(workspace))
        done = subprocess.run(argv, capture_output=True, text=True, timeout=180)
        assert done.returncode == 0, done.stderr
        return done.stdout

    return go


def test_without_a_workspace_it_behaves_as_before(run_audit):
    out = run_audit(None)

    assert "model calls" in out
    assert "the product:" not in out


def test_a_dead_page_is_reported_as_blocking(run_audit):
    out = run_audit({"index.html": DEAD_PAGE, "app.js": PURE})

    assert "BLOCKING problems found" in out
    assert "add-btn" in out


def test_a_working_product_is_not(run_audit):
    out = run_audit({"index.html": DEAD_PAGE, "app.js": WIRED})

    assert "no blocking cross-file problems" in out


def test_the_size_of_the_product_is_printed(run_audit):
    out = run_audit({"index.html": DEAD_PAGE, "app.js": WIRED})

    assert "application:" in out
    assert "of them code" in out


def test_the_cost_numbers_are_still_printed_alongside(run_audit):
    """The two questions are separate and both are wanted."""
    out = run_audit({"index.html": DEAD_PAGE, "app.js": WIRED})

    assert "failures that cost the run" in out
    assert "the product:" in out
