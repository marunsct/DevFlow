"""Behind `SPEC_DRY_RUN`, a spec run with stand-ins reports what throws from its own code, and nothing on suites that passed (plan item 18)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from app.acceptance import spec_dry_run, suite
from app.acceptance.junit import JUnitReport  # noqa: F401 - the suite's result type needs it importable
from app.stacks import contract, pack_named

CORPUS = Path(__file__).parent / "fixtures" / "locked_suites"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

HEAD = "import { test, expect } from '@playwright/test';\n"


def _errors(tmp_path: Path, body: str, name: str = "a.spec.js") -> list[str]:
    (tmp_path / name).write_text(HEAD + body)
    return [f["error"] for f in spec_dry_run.run(tmp_path, limit_seconds=20)["findings"]]


@pytest.mark.parametrize("body, expected", [
    ("test('x', async ({ request }) => { await request.get('/a'); expect(notDefined).toBe(1); });", "notDefined is not defined"),
    ("test('x', async ({ request }) => { const r = await request.get('/a'); await expect(r).toHaveStatusCode(200); });", "toHaveStatusCode is not a function"),
    ("test('x', async () => { const r = await fetch('/a'); expect(r.status()).toBe(200); });", "r.status is not a function"),
    ("test('x', async ({ request }) => { const r = await request.get('/a'); expect(r.statusCode).toBe(200); expect(r.status).toBe(200); });", "compares the response's method"),
    ("test('x', async ({ request }) => { const r = request.get('/a'); await r.json(); });", "r.json is not a function"),
    ("test.describe('g', () => { test.beforeEach(async () => { missing(); }); test('x', async () => {}); });", "missing is not defined"),
])
def test_a_fault_of_the_test_s_own_code_is_found(tmp_path, body, expected):
    assert any(expected in error for error in _errors(tmp_path, body)), _errors(tmp_path, body)


@pytest.mark.parametrize("body", [
    # What a product would decide: every assertion passes here.
    "test('x', async ({ request }) => { const r = await request.post('/a', { data: {} }); expect(r.status()).toBe(201); const b = await r.json(); expect(b.id).toBe(1); for (const n of b.items) expect(n.t).toBe('x'); });",
    # A thrown error may come from the stand-in's answers.
    "test('x', async () => { const r = await fetch('/a'); if (r.status !== 201) throw new Error('no'); });",
    "test('x', async () => { const r = await fetch('/a'); JSON.parse(await r.text()); });",
    # A callback for the browser does not run here.
    "test('x', async ({ page }) => { await page.goto('/'); await page.evaluate(() => document.title); await expect(page.getByRole('heading')).toBeVisible(); });",
    # A fixture of its own, `import` beside `require`, the product's files absent from the copy.
    "const base = test.extend({ svc: async ({ request }, use) => { await use({ request }); } });\nbase('x', async ({ svc }) => { await svc.request.get('/a'); });",
    "const fs = require('node:fs'); const { make } = require('../src/product.js'); test('x', async () => { make(); fs.existsSync('x'); });",
])
def test_nothing_a_product_would_decide_is_a_finding(tmp_path, body):
    assert _errors(tmp_path, body) == []


def test_no_signal_leaves_the_dry_run_and_no_process_starts(tmp_path):
    """A stored suite stops its service with `process.kill(-child.pid, ...)`: a stand-in pid of 1 made that kill(-1).

    Proved by the two session outages it caused, not by running it on the old code: run there, this test would signal
    every process of the user. Each assertion below throws a finding unless the call stayed inside the dry run.
    """
    body = """
    const { spawn, execSync } = require('node:child_process');
    test('x', async () => {
      const child = spawn('definitely-not-a-program', [], { detached: true });
      if (child.pid === 1 || child.pid < 4194304) notAPidTheKernelCouldGive();
      if (process.kill(-child.pid, 'SIGTERM') !== true) notIntercepted();
      if (execSync('definitely-not-a-program') !== '') notIntercepted();
    });
    """
    assert _errors(tmp_path, body) == []


def test_a_file_that_does_not_import_the_runner_is_not_run(tmp_path):
    (tmp_path / "helper.js").write_text("notDefined();")
    assert spec_dry_run.run(tmp_path) == {}


def test_the_stored_suites_that_passed_their_hidden_tests_give_no_finding():
    """Replay: 438 tests of 29 suites run, no finding. A finding here would be a false "cannot pass"."""
    tests = 0
    for kept in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        result = spec_dry_run.run(kept / "acceptance", limit_seconds=20)
        assert result.get("findings", []) == [], kept.name
        tests += result.get("tests", 0)
    assert tests >= 400


def _workspace(tmp_path: Path, body: str) -> Path:
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    where = tmp_path / "notes" / "acceptance"
    where.mkdir(parents=True, exist_ok=True)
    (where / "a.spec.js").write_text(HEAD + body)
    return tmp_path


BROKEN = "test('[AC-1] x', async () => { expect(notDefined).toBe(1); });"


def test_the_finding_reaches_the_cannot_pass_list_only_when_on(tmp_path, monkeypatch):
    root = _workspace(tmp_path, BROKEN)
    monkeypatch.setenv("SPEC_DRY_RUN", "off")
    assert spec_dry_run.findings(root) == []
    monkeypatch.setenv("SPEC_DRY_RUN", "on")
    found = spec_dry_run.findings(root)
    assert len(found) == 1 and "the dry run of the suite" in found[0] and "notes/acceptance/a.spec.js" in found[0]
    source = Path(suite.__file__).read_text()
    assert "*spec_dry_run.findings(repo_root)" in source[source.index("def tests_that_cannot_pass"):]


def test_one_pack_can_be_set_apart_from_the_switch(tmp_path, monkeypatch):
    root = _workspace(tmp_path, BROKEN)
    monkeypatch.setenv("SPEC_DRY_RUN", "on")
    monkeypatch.setenv("SPEC_DRY_RUN_NODE_HONO_NATIVE_API", "off")
    assert spec_dry_run.findings(root) == []
    monkeypatch.setenv("SPEC_DRY_RUN", "off")
    monkeypatch.setenv("SPEC_DRY_RUN_NODE_HONO_NATIVE_API", "on")
    assert len(spec_dry_run.findings(root)) == 1


def test_the_finding_s_words_keep_to_the_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEC_DRY_RUN", "on")
    text = spec_dry_run.findings(_workspace(tmp_path, BROKEN))[0]
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", text, re.I)


def test_it_is_an_experiment_that_ships_off():
    from app import switches

    assert "SPEC_DRY_RUN" in switches.EXPERIMENTS and "SPEC_DRY_RUN" not in switches.EXPERIMENTS_ON
    assert spec_dry_run.ON_BY_DEFAULT is False
