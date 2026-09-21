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


DEAD_TWO = (
    "<!DOCTYPE html><html><body>"
    "<input id='task-input' /><button id='add-btn'>Add</button>"
    "<script type='module' src='app.js'></script>"
    "<link rel='stylesheet' href='missing.css'>"
    "</body></html>"
)


def test_several_blocking_problems_are_still_reported(run_audit):
    """The summary writes "means" for one finding and "mean" for several.

    Matching the singular reported "no blocking cross-file problems" for every
    workspace that had more than one - silent in exactly the case that matters
    most. Run 1ae7671d had nine and the audit called it clean.
    """
    out = run_audit({"index.html": DEAD_TWO, "app.js": PURE})

    assert "BLOCKING problems found" in out


def test_one_blocking_problem_is_reported(run_audit):
    out = run_audit({"index.html": DEAD_PAGE, "app.js": PURE})

    assert "BLOCKING problems found" in out


class TestASandboxRefusalIsNotACost:
    """A guard firing is prevented damage, not a failure that cost the run.

    `audit_run.py`'s `SAVED` tuple marks the messages that mean "the harness
    stopped something bad". Its own docstring says to keep it in step with the
    refusals in `app/tools/repository.py` - and the sandbox writes its own,
    which the list had never covered.

    On run b0db10b1, six of the eight calls filed under "failures that cost the
    run" were sandbox refusals: five withheld repeats of a settled command and
    one refused long-running server. Counting them as costs made the number the
    script exists to drive down rise whenever a guard did its job. Corrected,
    that run reports 2 costly failures (0.3%) rather than 8 (1.2%), and twice
    the prevented damage.
    """

    def _saved(self):
        # Read out of the source rather than imported. Importing a script to
        # look at one constant runs everything else in it, and this one parses
        # `sys.argv` - under the full suite that is pytest's, so the first
        # version died with `IsADirectoryError: Is a directory: 'tests/'`.
        # `audit_run.py` now guards its entry point, and this no longer depends
        # on whether it does.
        import ast

        assert SCRIPT.is_file()
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        for node in tree.body:
            targets = getattr(node, "targets", [])
            if any(getattr(t, "id", None) == "SAVED" for t in targets):
                return ast.literal_eval(node.value)
        raise AssertionError("audit_run.py no longer defines SAVED")

    def test_the_sandbox_refusals_are_marked_as_prevented(self):
        saved = self._saved()
        for fragment in (
            "Not running this again",
            "it runs until it is stopped",
            "installs system packages as root",
        ):
            assert fragment in saved, f"{fragment!r} would be counted as a cost"

    def test_every_marker_is_a_phrase_the_tools_really_emit(self):
        """A fragment that stops matching moves real refusals into the cost column.

        The same staleness `_BREAKS_BEHAVIOUR` is checked for, applied to the
        other list that decides what a number means.
        """
        import inspect
        import re

        # `javascript_parse` too: "Node cannot parse" is written there, not in
        # either tool module, and a search of the two alone reported a live
        # marker as stale.
        from app.analysis import javascript_parse
        from app.tools import repository, sandbox

        source = "".join(
            inspect.getsource(module)
            for module in (repository, sandbox, javascript_parse)
        )
        joined = re.sub(r'"\s*\n\s*"', "", source)

        missing = [
            fragment for fragment in self._saved() if fragment not in joined
        ]
        assert not missing, f"no tool emits these any more: {missing}"
