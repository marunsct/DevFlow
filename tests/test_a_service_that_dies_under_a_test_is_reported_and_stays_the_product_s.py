"""A service that stops by itself under a test says so, with what it wrote, and the test stays locked

Measured on one run: the restart helper started the product with its output thrown away. The product read its data folder
as a file and exited on the first write, the test saw only "fetch failed", the dispute called a fair test impossible, and
QA, who may not change the product, spent most of an hour on it.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes
from app.stacks import pack_named
from app.stacks.packs._service import SERVICE_STOPPED_BY_ITSELF

_FATAL = "Fatal error reading the data"


def _project(tmp_path, check: str):
    (tmp_path / "acceptance").mkdir()
    (tmp_path / "acceptance" / "service.cjs").write_text(pack_named("node-hono-native-api").files["acceptance/service.cjs"])
    (tmp_path / "start.sh").write_text('#!/bin/sh\ncd "$(dirname "$0")" && exec node server.cjs\n')
    (tmp_path / "server.cjs").write_text(
        "require('http').createServer((q, s) => {\n"
        "  if (q.method === 'POST') { console.error(" + repr(_FATAL) + "); process.exit(1); }\n"
        "  s.end('ok');\n"
        "}).listen(Number(process.env.PORT), process.env.HOST);\n")
    (tmp_path / "check.cjs").write_text("const { startService } = require('./acceptance/service.cjs');\n" + check)
    return subprocess.run(["node", "check.cjs"], cwd=tmp_path, capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_a_service_that_stops_by_itself_is_reported_with_what_it_wrote(tmp_path):
    done = _project(tmp_path, """(async () => {
      const s = await startService();
      await fetch(s.baseURL + '/n', { method: 'POST' }).catch(() => {});
      await new Promise((r) => setTimeout(r, 300));
      process.exit(0);
    })();
    """)
    assert SERVICE_STOPPED_BY_ITSELF in done.stderr
    assert _FATAL in done.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_a_service_a_test_stopped_is_not_reported(tmp_path):
    done = _project(tmp_path, """(async () => {
      const s = await startService();
      await s.stop();
      await new Promise((r) => setTimeout(r, 300));
      process.exit(0);
    })();
    """)
    assert done.returncode == 0, done.stderr
    assert SERVICE_STOPPED_BY_ITSELF not in done.stderr


_RESTART = "[AC-6] notes survive a restart"
_LINE = f"`{_RESTART}` cannot pass for any product that does what its criterion says: it checks that notes stay"
_OTHER = "`[AC-2] lists notes` cannot pass for any product that does what its criterion says: it checks a thing"


def _suite(monkeypatch, tmp_path, output: str):
    spec = tmp_path / "persistence.spec.js"
    spec.write_text(f"const {{ startService }} = require('./service.cjs');\ntest('{_RESTART}', async () => {{}});\n")
    other = tmp_path / "api.spec.js"
    other.write_text("test('[AC-2] lists notes', async () => {});\n")
    monkeypatch.setattr(suite, "suite_files", lambda _root: [spec, other])
    monkeypatch.setattr(suite, "last_result", lambda _root: {"output": output})


def test_a_disputed_test_whose_service_stopped_by_itself_stays_locked(monkeypatch, tmp_path):
    _suite(monkeypatch, tmp_path, f"{SERVICE_STOPPED_BY_ITSELF} (code 1)")
    assert acceptance_nodes.tests_whose_service_stayed_up(tmp_path, [_LINE, _OTHER]) == ([_OTHER], [_RESTART])


def test_with_no_such_report_a_dispute_goes_on_as_it_was(monkeypatch, tmp_path):
    _suite(monkeypatch, tmp_path, "1 failed")
    assert acceptance_nodes.tests_whose_service_stayed_up(tmp_path, [_LINE, _OTHER]) == ([_LINE, _OTHER], [])


def test_the_dispute_asks_before_it_reopens_the_suite():
    from pathlib import Path

    source = (Path(__file__).parent.parent / "src" / "app" / "graph" / "workflow.py").read_text(encoding="utf-8")
    node = source[source.index("def acceptance_dispute_node"):]
    assert node.index("tests_whose_service_stayed_up") < node.index("within_the_cap")
