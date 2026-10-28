"""The architecture review is given a finding for product behaviour the specification gives a file the pack keeps.

Measured on four runs: told the pack's files are the harness's and do nothing more, the specification still wrote
"Entry Point (src/main.ts - kept by harness): ... registering signal handlers for graceful shutdown ... Creates
DATA_DIR" and "start.sh creates DATA_DIR"; a milestone review later sent a sprint back for it.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.graph import workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STACK = SimpleNamespace(language="TypeScript", framework="Hono", frontend_framework="",
                        testing_framework="node:test for unit tests, Playwright (request fixture) for acceptance tests")
SPEC = """- Entry Point (src/main.ts — kept by harness): Wires the app, starting the server via serve(), and registering signal handlers for graceful shutdown that call shutdown(). Creates DATA_DIR if needed before starting.
- BE-7: Adopted. Use PORT and DATA_DIR env vars, start.sh creates DATA_DIR.
- start.sh launches the service; src/app.ts validates every request body.
- src/main.ts serves createApp() from src/app.ts on HOST and PORT."""


def _state(**extra):
    return {"stack_selection": SimpleNamespace(technology_stack=STACK), "document": SimpleNamespace(text="notes api"), **extra}


def test_behaviour_given_to_kept_files_is_a_major_finding_naming_the_product_file(monkeypatch):
    monkeypatch.setenv("HONO_NATIVE_TEST_RUNNER", "on")  # the pack that keeps the start file, as in compose
    finding = workflow._behaviour_the_specification_gives_kept_files(_state(), SPEC)
    assert finding is not None and finding.severity == "major"
    assert "`src/main.ts`" in finding.description and "`start.sh`" not in finding.description
    assert "signal handlers" in finding.description and "validates every request body" not in finding.description
    assert "serves createApp()" not in finding.description
    assert "src/app.ts" in finding.required_remediation
    assert not BANNED.search(finding.description + finding.required_remediation)


def test_once_per_run_and_never_on_the_last_revision():
    assert workflow._behaviour_the_specification_gives_kept_files(_state(specification_kept_files_checked=True), SPEC) is None
    last = workflow.MAX_ARCHITECTURE_REVISIONS - 1
    assert workflow._behaviour_the_specification_gives_kept_files(_state(architecture_revision_count=last), SPEC) is None


def test_the_review_adds_it():
    source = inspect.getsource(workflow)
    assert "kept_finding = _behaviour_the_specification_gives_kept_files(state, spec_text)" in source
