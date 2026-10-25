"""A Node service pack keeps a helper that starts the project's own start script on a chosen data folder, so a persistence criterion is tested.

Measured over five runs: QA marked every criterion about data surviving a restart as one it "cannot verify, the server runs
once per suite" and shipped it deferred. In one run the product lost its notes on a restart and the hidden test caught it.
"""
from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.mark.parametrize("name", ["node-hono-api", "node-hono-native-api", "go-http-api", "php-slim-api"])
def test_the_pack_writes_and_keeps_the_helper(name):
    pack = pack_named(name)
    assert "acceptance/service.cjs" in pack.kept_files
    assert "startService" in pack.files["acceptance/service.cjs"]
    assert "acceptance/service.cjs" in pack.acceptance_guide and "startService" in pack.acceptance_guide


def test_the_restart_guide_is_free_of_banned_words():
    assert not BANNED.search(pack_named("node-hono-native-api").acceptance_guide.split("A criterion about the data")[-1])


def test_a_helper_a_stage_changed_is_put_back(tmp_path):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    (project / "acceptance").mkdir(parents=True)
    (project / "acceptance" / "service.cjs").write_text("module.exports = {};\n")

    contract.enforce(tmp_path)

    assert "startService" in (project / "acceptance" / "service.cjs").read_text()


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_the_helper_starts_stops_and_restarts_on_the_same_data(tmp_path):
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "service.cjs").write_text(pack_named("node-hono-native-api").files["acceptance/service.cjs"])
    (tmp_path / "start.sh").write_text('#!/bin/sh\ncd "$(dirname "$0")" && exec node server.cjs\n')
    (tmp_path / "server.cjs").write_text(
        "const http = require('http'), fs = require('fs'), path = require('path');\n"
        "const file = path.join(process.env.DATA_DIR, 'n.txt');\n"
        "http.createServer((req, res) => {\n"
        "  if (req.method === 'POST') { fs.writeFileSync(file, 'kept'); res.end('ok'); }\n"
        "  else res.end(fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : 'none');\n"
        "}).listen(Number(process.env.PORT), process.env.HOST);\n"
    )
    (tmp_path / "check.cjs").write_text(
        "const { startService } = require('./acceptance/service.cjs');\n"
        "(async () => {\n"
        "  const first = await startService();\n"
        "  await fetch(first.baseURL + '/', { method: 'POST' });\n"
        "  await first.stop();\n"
        "  const second = await startService({ dataDir: first.dataDir });\n"
        "  const text = await (await fetch(second.baseURL + '/')).text();\n"
        "  await second.stop();\n"
        "  const third = await startService();\n"
        "  const fresh = await (await fetch(third.baseURL + '/')).text();\n"
        "  await third.stop();\n"
        "  console.log(text + ',' + fresh);\n"
        "})().catch((e) => { console.error(e); process.exit(1); });\n"
    )

    done = subprocess.run(["node", "check.cjs"], cwd=tmp_path, capture_output=True, text=True, timeout=90)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "kept,none"
