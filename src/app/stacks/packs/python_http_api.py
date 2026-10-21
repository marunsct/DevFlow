"""An HTTP service in Python, on FastAPI."""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _python

REQUIREMENTS = """fastapi>=0.115
uvicorn>=0.30
"""

REQUIREMENTS_DEV = """pytest>=8
httpx>=0.27
pytest-timeout>=2
"""

MAIN = '''"""The service's HTTP interface."""

from fastapi import FastAPI

app = FastAPI(title="{{title}}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
'''

CONFTEST = '''"""Starts the service for the acceptance suite. The harness owns this file.

The service runs as its own process, the way a user's client meets it, with
`PORT` and `DATA_DIR` set: a service that stores anything keeps it under
`DATA_DIR`, which starts empty for every run of this suite.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Service:
    """The running service: its address, and a restart that keeps its data."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self._process = None

    def start(self) -> None:
        env = {**os.environ, "PORT": str(self.port), "DATA_DIR": str(self.data_dir)}
        # The way the brief starts it, when the project has its `start.sh`:
        # what the customer runs is what every test here proves starts.
        brief_s_way = ["sh", "start.sh"] if (PROJECT / "start.sh").is_file() else None
        self._process = subprocess.Popen(
            brief_s_way or [sys.executable, "-m", "uvicorn", "{{package}}.main:app",
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=PROJECT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(f"{self.url}/health", timeout=1):
                    return
            except OSError:
                if self._process.poll() is not None or time.monotonic() > deadline:
                    self.stop()
                    output = self._process.stdout.read() if self._process.stdout else ""
                    pytest.fail(f"The service did not start:\\n{output[-3000:]}")
                time.sleep(0.2)

    def stop(self) -> None:
        # The whole group: a start script that runs the server as its child
        # would leave it serving the port after the script itself had gone.
        if self._process and self._process.poll() is None:
            try:
                os.killpg(self._process.pid, 15)
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self._process.pid, 9)
            except ProcessLookupError:
                pass

    def restart(self) -> None:
        self.stop()
        self.start()


@pytest.fixture(scope="session")
def service(tmp_path_factory):
    running = Service(tmp_path_factory.mktemp("service-data"))
    running.start()
    yield running
    running.stop()


@pytest.fixture(scope="session")
def base_url(service) -> str:
    return service.url
'''

#: How a person (or anything that deploys it) starts the service: the port in
#: PORT, the interface in HOST (default 127.0.0.1), its data under DATA_DIR.
START = """#!/bin/sh
cd "$(dirname "$0")" && exec .venv/bin/python -m uvicorn {{package}}.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
"""

SMOKE_UNIT = '''from fastapi.testclient import TestClient

from {{package}}.main import app


def test_the_service_reports_its_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
'''

SMOKE_ACCEPTANCE = '''import httpx


def test_the_running_service_answers(base_url):
    assert httpx.get(f"{base_url}/health").json() == {"status": "ok"}
'''

GUIDE = _python.UNIT_GUIDE + """
The application object is `app` in `{{package}}/main.py`; add routes there or in
modules it includes. A service that stores data keeps it under the directory in
the `DATA_DIR` environment variable (default `data/`), never in memory only. A
unit test calls routes through `fastapi.testclient.TestClient(app)`."""

ACCEPTANCE_GUIDE = """Acceptance tests go in `acceptance/`, named `test_<feature>.py`, as pytest
functions. The suite's `conftest.py` starts the real service as its own process:
take the `base_url` fixture and call it with `httpx` (`httpx.post(f"{base_url}/items",
json={...})`), checking status codes and JSON bodies exactly as a client would.
To prove data survives a restart, take the `service` fixture and call
`service.restart()` between the write and the read. The service keeps its data
for the whole session, so a test must not assume it starts empty: create what it
reads, and look for its own records rather than counting all of them.
""" + _python.NAMING

PACK = StackPack(
    name="python-http-api",
    title="HTTP service in Python on FastAPI",
    kind="http_api",
    language="python",
    frameworks=("fastapi", "starlette", "uvicorn"),
    files={
        "requirements.txt": REQUIREMENTS,
        "requirements-dev.txt": REQUIREMENTS_DEV,
        "pytest.ini": _python.PYTEST_INI,
        ".gitignore": _python.GITIGNORE,
        "{{package}}/__init__.py": '"""{{title}}."""\n',
        "{{package}}/main.py": MAIN,
        "acceptance/conftest.py": CONFTEST,
        "start.sh": START,
    },
    install=_python.INSTALL,
    unit_test=_python.UNIT_TEST,
    acceptance_test=_python.ACCEPTANCE_TEST,
    unit_report="test-results/unit.xml",
    acceptance_report="test-results/acceptance.xml",
    unit_dir="tests",
    acceptance_dir="acceptance",
    acceptance_pattern="test_*.py",
    unit_pattern="test_*.py",
    entrypoint="{{package}}/main.py",
    wired_by_imports=True,
    unit_test_names=_python.UNIT_TEST_NAMES,
    test_helpers=_python.TEST_HELPERS,
    kept_files=("pytest.ini", "acceptance/conftest.py"),
    kept_scripts={},
    smoke_files={
        "tests/test_scaffold_smoke.py": SMOKE_UNIT,
        "acceptance/test_scaffold_smoke.py": SMOKE_ACCEPTANCE,
    },
    guide=GUIDE,
    acceptance_guide=ACCEPTANCE_GUIDE,
    stack={
        "language": "Python",
        "framework": "FastAPI",
        "frontend_framework": "",
        "testing_framework": "pytest for unit tests, pytest with httpx against the running service for acceptance tests",
    },
    check_families=frozenset({"python"}),
    test_bugs=_python.TEST_BUGS,
    ci_setup=_python.CI_SETUP,
    release_files={
        "Dockerfile": _python.service_dockerfile("uvicorn {{package}}.main:app"),
        ".dockerignore": _python.DOCKERIGNORE,
    },
)
