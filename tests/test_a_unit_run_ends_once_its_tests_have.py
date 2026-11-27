"""A pack's unit run ends once its tests have, with its report written, whatever a test left open (LF.1640).

Measured on a service run: a test helper declared a request body and never sent it, so twenty-five tests each waited
out Node's limit for one test - 20 seconds - one after another, and each one left its server listening. Every unit run
was ended at the sandbox's 300-second limit with no report written; reproduced on a copy, the run took 520 seconds.
With each test held to 5 seconds and the runner told to exit once its tests have ended, the same tests end within the
limit and the report names every one that timed out. Jest, run in one process, stays alive after its last test the
same way.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.plugins import seed
from app.stacks import pack_named
from app.stacks.packs import ALL_PACKS
from app.tools.sandbox import TIMEOUTS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _unit_scripts() -> list[tuple[str, str]]:
    found = []
    for pack in ALL_PACKS:
        manifest = (pack.files or {}).get("package.json")
        if not manifest:
            continue
        try:
            scripts = json.loads(re.sub(r"\{\{\w+\}\}", "p", manifest)).get("scripts", {})
        except ValueError:
            continue
        script = scripts.get("test", "")
        if "--test" in script or re.search(r"\bjest\b", script):
            found.append((pack.name, script))
    return found


@pytest.mark.parametrize("pack,script", _unit_scripts())
def test_every_unit_run_ends_once_its_tests_have(pack, script):
    assert "--test-force-exit" in script or "--forceExit" in script, f"{pack}: {script}"


@pytest.mark.parametrize("pack,script", [(p, s) for p, s in _unit_scripts() if "--test-timeout=" in s])
def test_twenty_five_tests_held_to_the_unit_limit_end_within_a_test_run_s_limit(pack, script):
    per_test_ms = int(re.search(r"--test-timeout=(\d+)", script).group(1))

    assert 25 * per_test_ms / 1000 < TIMEOUTS["test"], f"{pack}: {script}"


def _node_major() -> int:
    node = shutil.which("node")
    if not node:
        return 0
    try:
        return int(subprocess.run([node, "--version"], capture_output=True, text=True).stdout.lstrip("v").split(".")[0])
    except (OSError, ValueError):
        return 0


LEAVES_A_SERVER_OPEN = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

test('answers and leaves its server listening', async () => {
  const server = http.createServer((request, response) => response.end('ok'));
  await new Promise((resolve) => server.listen(0, resolve));
  assert.ok(server.listening);
});
"""


@pytest.mark.skipif(_node_major() < 22, reason="Node's runner exits once its tests end from Node 22")
def test_a_node_unit_run_whose_test_leaves_a_server_open_ends_with_its_report(tmp_path):
    script = json.loads(re.sub(r"\{\{\w+\}\}", "p", pack_named("node-http-api").files["package.json"]))["scripts"]["test"]
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "server.test.js").write_text(LEAVES_A_SERVER_OPEN, encoding="utf-8")
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")

    try:
        ran = subprocess.run(["sh", "-c", script], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("the unit run was still running 30 seconds after its one test had passed")

    assert ran.returncode == 0, ran.stdout + ran.stderr
    report = (tmp_path / "test-results" / "unit.xml").read_text(encoding="utf-8")
    assert 'name="answers and leaves its server listening"' in report and report.rstrip().endswith("</testsuites>")


def test_a_custom_javascript_setup_is_told_to_end_when_its_tests_do():
    flat = " ".join(seed._JAVASCRIPT_TESTING.split())

    assert "`--test-force-exit`" in flat and "`--forceExit`" in flat
    assert "must also end when its tests do" in flat
    assert not BANNED.search(seed._JAVASCRIPT_TESTING)
