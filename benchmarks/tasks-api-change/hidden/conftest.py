"""Starts the product the way its brief says: `sh start.sh` with PORT and DATA_DIR."""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

PRODUCT = Path(os.environ["PRODUCT_DIR"])


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Service:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.process = None

    def start(self) -> None:
        env = {**os.environ, "PORT": str(self.port), "DATA_DIR": str(self.data_dir)}
        self.process = subprocess.Popen(
            ["sh", "start.sh"], cwd=PRODUCT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.url}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            if self.process.poll() is not None:
                break
            time.sleep(0.3)
        output = self.process.stdout.read().decode(errors="replace") if self.process.poll() is not None else ""
        self.stop()
        pytest.fail(f"The service did not start with start.sh: {output[-1500:]}")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, 15)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, 9)

    def restart(self) -> None:
        self.stop()
        self.start()


@pytest.fixture(scope="session")
def service(tmp_path_factory):
    running = Service(tmp_path_factory.mktemp("tasks-data"))
    running.start()
    yield running
    running.stop()


@pytest.fixture
def api(service):
    with httpx.Client(base_url=service.url, timeout=10) as client:
        yield client


def sign_up_and_in(api, username=None, password="s3cret-pass"):
    """A new account, signed in: the headers its requests send."""
    import uuid

    username = username or f"user{uuid.uuid4().hex[:8]}"
    made = api.post("/signup", json={"username": username, "password": password})
    assert made.status_code == 201, made.text
    signed = api.post("/signin", json={"username": username, "password": password})
    assert signed.status_code == 200, signed.text
    return {"Authorization": f"Bearer {signed.json()['token']}"}
