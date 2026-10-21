"""The brownfield bench: a previous product, a change brief, hidden tests for the old and the new (plan BW.3).

Every benchmark was greenfield while the platform's second scenario - adding
features to code that exists - was never measured. `tasks-api-change` starts a
run from the tasks-api reference (`base/`) with a brief for three additions. Its
hidden suite is the old tests and the new ones, so a run that adds the features
and breaks what was there loses points for it. The base must pass exactly the old
tests and fail every new one, or the suite does not tell the change apart.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "tasks-api-change"

httpx = pytest.importorskip("httpx")


def _hidden(product: Path, tmp_path: Path) -> str:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", str(BENCH / "hidden"), "-q", "-p", "no:cacheprovider", "-rA",
         "--rootdir", str(BENCH / "hidden"), "-c", os.devnull, "--no-header", "-o", "addopts="],
        env={**os.environ, "PRODUCT_DIR": str(product)},
        capture_output=True, text=True, timeout=300, cwd=tmp_path,
    )
    return done.stdout + done.stderr


def _old_tests() -> set[str]:
    source = (BENCH / "hidden" / "test_tasks_api.py").read_text()
    return set(re.findall(r"^def (test_\w+)", source, re.M))


def test_the_reference_passes_every_hidden_test(tmp_path):
    expected = json.loads((BENCH / "bench.json").read_text())["tests"]

    out = _hidden(BENCH / "reference", tmp_path)

    assert f"{expected} passed" in out, out[-1500:]


def test_the_base_passes_the_old_tests_and_fails_every_new_one(tmp_path):
    out = _hidden(BENCH / "base", tmp_path)

    passed = set(re.findall(r"^PASSED \S+::(test_\w+)", out, re.M))
    assert passed == _old_tests(), out[-1500:]


def test_the_old_hidden_tests_are_the_greenfield_bench_s_own():
    greenfield = ROOT / "benchmarks" / "tasks-api"
    assert (BENCH / "hidden" / "test_tasks_api.py").read_text() == (greenfield / "hidden" / "test_tasks_api.py").read_text()
    assert (BENCH / "base" / "server.py").read_text() == (greenfield / "reference" / "server.py").read_text()


def _port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _serve(product: Path, data: Path):
    port = _port()
    process = subprocess.Popen(["sh", "start.sh"], cwd=product, env={**os.environ, "PORT": str(port), "DATA_DIR": str(data)},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                return process, url
        except httpx.HTTPError:
            time.sleep(0.2)
    process.kill()
    pytest.fail(f"{product.name} did not start")


def test_data_the_base_stored_keeps_working_under_the_reference(tmp_path):
    base, url = _serve(BENCH / "base", tmp_path)
    try:
        httpx.post(f"{url}/signup", json={"username": "kept", "password": "pw-123456"})
        token = httpx.post(f"{url}/signin", json={"username": "kept", "password": "pw-123456"}).json()["token"]
        httpx.post(f"{url}/items", json={"title": "from before"}, headers={"Authorization": f"Bearer {token}"})
    finally:
        os.killpg(base.pid, 15)
        base.wait(timeout=10)

    changed, url = _serve(BENCH / "reference", tmp_path)
    try:
        items = httpx.get(f"{url}/items", headers={"Authorization": f"Bearer {token}"}).json()
    finally:
        os.killpg(changed.pid, 15)
        changed.wait(timeout=10)

    assert items == [{"id": items[0]["id"], "title": "from before", "done": False, "due": None}]


def test_a_brownfield_bench_starts_its_run_from_its_base():
    bench = json.loads((BENCH / "bench.json").read_text())
    loop = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    start = loop[loop.index("\nstart)"):loop.index("\nbench)")]
    bench_command = loop[loop.index("\nbench)"):loop.index("\nscore)")]

    assert bench["brownfield"] is True and (BENCH / bench["base"] / "start.sh").is_file()
    assert "SEED=" in bench_command and "'base'" in bench_command
    assert "/codebase" in start and '\\"type\\": \\"archive\\"' in start and "$source}" in start
