"""Starts the service for the acceptance suite. The harness owns this file.

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
LOG = PROJECT / "test-results" / "service.log"


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
        # Everything the service prints goes to a file the harness reads when a test meets a server error: a
        # 500 says nothing about its cause, the traceback the service logged does. (A file, not a pipe: a pipe
        # nobody reads fills up and stops the service.)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(LOG, "a", encoding="utf-8")
        self._process = subprocess.Popen(
            brief_s_way or [sys.executable, "-m", "uvicorn", "tasks_api.main:app",
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=PROJECT, env=env, stdout=self._log, stderr=subprocess.STDOUT, text=True,
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
                    output = LOG.read_text(encoding="utf-8", errors="replace") if LOG.is_file() else ""
                    pytest.fail(f"The service did not start:\n{output[-3000:]}")
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
        log = getattr(self, "_log", None)
        if log is not None and not log.closed:
            log.close()

    def restart(self) -> None:
        self.stop()
        self.start()


@pytest.fixture(scope="session")
def service(tmp_path_factory):
    LOG.unlink(missing_ok=True)
    running = Service(tmp_path_factory.mktemp("service-data"))
    running.start()
    yield running
    running.stop()


@pytest.fixture(scope="session")
def base_url(service) -> str:
    return service.url
