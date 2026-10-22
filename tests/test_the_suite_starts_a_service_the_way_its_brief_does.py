"""The acceptance suite starts a service the way its brief does - its `start.sh` - whenever the project has one.

One run's drafting rewrote `start.sh` to a Python with none of the product's
dependencies. The suite started the service by the framework's own command, so
every one of its 67 tests passed; the hidden tests, which start it with `sh
start.sh` as the brief says, failed all ten - and passed all ten with the
script put back. What the customer runs is now what every test proves starts.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from app.stacks import pack_named
from app.stacks.packs import ALL_PACKS

SERVER = textwrap.dedent('''
    import http.server, os
    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status": "ok"}')
        def log_message(self, *args):
            pass
    http.server.HTTPServer(("127.0.0.1", int(os.environ["PORT"])), Health).serve_forever()
''')


def _project(root: Path, pack_name: str) -> Path:
    project = root / "notes-api"
    (project / "acceptance").mkdir(parents=True)
    files = pack_named(pack_name).render("notes-api", "Notes API", "notes_api")
    (project / "acceptance" / "conftest.py").write_text(files["acceptance/conftest.py"])
    (project / "server.py").write_text(SERVER)
    # A start script that runs the server as its child, not by exec.
    (project / "start.sh").write_text(f'#!/bin/sh\ntouch started-by-start-sh\n"{sys.executable}" server.py\n')
    (project / "acceptance" / "test_started.py").write_text(textwrap.dedent('''
        from pathlib import Path
        def test_the_service_came_up_through_start_sh(service):
            assert (Path(__file__).resolve().parent.parent / "started-by-start-sh").exists()
    '''))
    return project


def test_a_python_service_suite_starts_it_through_start_sh_and_stops_it_all(tmp_path: Path):
    for pack in ("python-http-api", "python-flask-api"):
        project = _project(tmp_path / pack, pack)

        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "acceptance"],
                              cwd=project, capture_output=True, text=True, timeout=120)

        assert "1 passed" in done.stdout, pack + "\n" + done.stdout[-1500:] + done.stderr[-500:]
        left = subprocess.run(["pgrep", "-f", str(project / "server.py")], capture_output=True, text=True)
        still = subprocess.run(["pgrep", "-af", "server.py"], capture_output=True, text=True).stdout
        assert str(project) not in still, f"{pack}: the server outlived the suite"


def test_every_service_pack_s_suite_runs_start_sh_when_there_is_one():
    services = [pack for pack in ALL_PACKS if pack.kind == "http_api"]
    assert services
    for pack in services:
        files = pack.render("notes-api", "Notes API", "notes_api")
        setup = files.get("acceptance/conftest.py") or files.get("playwright.config.js") or ""
        assert "start.sh" in setup, pack.name
