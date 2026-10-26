"""When the product does not start for the suite, the harness starts it the suite's way and reports what it saw (behind `START_PROBE`).

Measured on a small-model run: the defect said only "Timed out waiting 60000ms from config.webServer" for 40 minutes;
started by hand the suite's way, the service listened and answered `/health` with 503, because its health check needed
the data folder to exist.
"""
from __future__ import annotations

import re
import shutil

import pytest

from app.acceptance import start_probe
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _project(tmp_path, server_js):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    project.mkdir()
    (project / "playwright.config.js").write_text(pack.render("notes", "Notes", None)["playwright.config.js"])
    (project / "start.sh").write_text('#!/bin/sh\ncd "$(dirname "$0")" && exec node server.cjs\n')
    (project / "server.cjs").write_text(server_js)
    return tmp_path


NEEDS_ITS_DATA_FOLDER = """const http = require('http'), fs = require('fs');
console.log('Listening on ' + process.env.PORT);
http.createServer((q, s) => { s.statusCode = fs.existsSync(process.env.DATA_DIR) ? 200 : 503; s.end('x'); })
  .listen(Number(process.env.PORT), process.env.HOST);
"""
CRASHES = "console.error('TypeError: x is not a function'); process.exit(1);\n"


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("START_PROBE", "on")


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_a_readiness_answer_of_503_is_reported_with_what_it_means(tmp_path):
    text = start_probe.what_the_start_shows(_project(tmp_path, NEEDS_ITS_DATA_FOLDER))

    assert "`GET /health` answered 503" in text and "Listening on" in text
    assert "does not exist yet" in text
    assert not BANNED.search(text)


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_a_service_that_exits_is_reported_with_its_output(tmp_path):
    text = start_probe.what_the_start_shows(_project(tmp_path, CRASHES))

    assert "exited with code 1" in text and "is not a function" in text


def test_off_or_without_a_start_script_nothing_is_added(tmp_path, monkeypatch):
    root = _project(tmp_path, CRASHES)
    monkeypatch.setenv("START_PROBE", "off")
    assert start_probe.what_the_start_shows(root) == ""
    monkeypatch.setenv("START_PROBE", "on")
    (root / "notes" / "start.sh").unlink()
    assert start_probe.what_the_start_shows(root) == ""


def test_the_start_defect_carries_it():
    import inspect

    from app.graph import acceptance_nodes

    assert "_what_the_start_shows(_root(state))" in inspect.getsource(acceptance_nodes.failing_due_defects)
