"""A test that imports its runner has every name it uses checked, as product code is.

Measured on one run: QA, repairing a locked suite, wrote a test calling
`getTask`, which nothing defined; the review ran out of rounds and the suite
was locked with a test no product could pass. Names were checked only in the
product's own code, because a Jest or Vitest test may use globals its runner
supplies. Playwright's and Node's runners supply none: a file that imports
`@playwright/test` or `node:test` defines or imports every name it uses. Swept
over the 1,038 such test files stored from earlier runs: 5 flagged, each a real
fault (`expect` never imported, `JSDOM` never imported, an undeclared `taskId`),
none a false alarm once a function handed to the page (`page.evaluate`) is left
to the page's own globals.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.analysis import language_service as service
from app.analysis.typescript_parse import compiler_for

needs_the_compiler = pytest.mark.skipif(
    shutil.which("node") is None or compiler_for(None) is None,
    reason="no TypeScript compiler beside Node here (the worker image has one)",
)

PLAYWRIGHT_TEST = """import { test, expect } from '@playwright/test';

test('[AC-4] defaults to medium', async ({ request, page }) => {
  const fetched = await getTask(request, 1);
  const title = await page.evaluate(() => { if (typeof init === 'function') init(); return document.title; });
  await page.addInitScript(function () { seedStore(); });
  expect(process.env.HOME).toBeDefined();
  expect(fetched.priority).toBe('medium');
});
"""

JEST_GLOBALS_TEST = "describe('x', () => { it('y', () => { expect(1).toBe(1); }); });\n"


@pytest.mark.parametrize("content, imports", [
    ("import { test, expect } from '@playwright/test';", True),
    ('import test from "node:test";', True),
    ("const { test } = require('@playwright/test');", True),
    ("import { describe, it } from 'vitest';", False),
    (JEST_GLOBALS_TEST, False),
])
def test_only_a_runner_with_no_globals_counts(content, imports):
    assert service.imports_its_runner(content) is imports


def _asked(tmp_path, monkeypatch, relative: str, content: str) -> list[str]:
    """The argv the language service is started with, for `content` at `relative`."""
    started: list[list[str]] = []
    monkeypatch.setattr(service.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr("app.analysis.typescript_parse.compiler_for", lambda target: "/x/typescript.js")

    def run(argv, **kwargs):
        started.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, json.dumps({"here": [], "elsewhere": []}), "")

    monkeypatch.setattr(service.subprocess, "run", run)
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    service.underlined(tmp_path, target, content, tmp_path / "app")
    return started[0][-2:]


def test_a_runner_importing_test_is_checked_for_names_with_both_runtimes_globals(tmp_path, monkeypatch):
    assert _asked(tmp_path, monkeypatch, "app/acceptance/a.spec.js", PLAYWRIGHT_TEST) == [service.BOTH, "1"]


def test_a_test_on_runner_globals_is_still_not(tmp_path, monkeypatch):
    assert _asked(tmp_path, monkeypatch, "app/tests/b.test.js", JEST_GLOBALS_TEST)[-1] == "0"


@needs_the_compiler
def test_a_name_nothing_defines_in_a_test_is_underlined_and_the_page_s_are_not(tmp_path):
    project = tmp_path / "app"
    target = project / "acceptance" / "a.spec.js"
    target.parent.mkdir(parents=True)
    target.write_text(PLAYWRIGHT_TEST)

    found = service.underlined(tmp_path, target, PLAYWRIGHT_TEST, project)

    assert [f["message"] for f in found.here] == ["Cannot find name 'getTask'."]
