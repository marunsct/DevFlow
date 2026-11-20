"""The worker's half of a product preview (plan WS.4): the product copied and started in a container of its own.

What must hold: the container sees a scratch copy, never the run's workspace; `accepted` is the last accepted sprint's
files and `live` the files now, both with the installed folders the workspace has; the container gets the sandbox's
restrictions, the preview network and none of the worker's secrets; a product with nothing to start, or a container
that does not start, fails the preview with the reason; a stop ends the container and removes the copy. Docker is
stood in for by a recording spy: the argv is what reaches it.
"""
from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path

import pytest

from app.server import preview, preview_worker


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _workspace(root: Path) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "h@example.com")
    _git(root, "config", "user.name", "harness")
    (root / ".gitignore").write_text("node_modules/\n.harness/\n.agent-home/\n")
    (root / "start.sh").write_text("node server.js\n")
    (root / "server.js").write_text("// sprint one\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Sprint 1")
    _git(root, "tag", "sprint-1")
    (root / "server.js").write_text("// being written\n")
    (root / "routes.js").write_text("// new since the sprint\n")
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1\n")
    (root / ".harness").mkdir()
    (root / ".harness" / "steering.json").write_text("[]")
    (root / ".agent-home").mkdir()
    (root / ".agent-home" / "history").write_text("x")
    return root


class _Docker:
    """A spy for the docker command line: records each call, answers as told."""

    def __init__(self, code=0, stderr=""):
        self.calls: list[list[str]] = []
        self.code, self.stderr = code, stderr

    def __call__(self, *argv):
        command = list(argv[0]) if len(argv) == 1 and isinstance(argv[0], list) else ["docker", *argv]
        self.calls.append(command)
        return subprocess.CompletedProcess(command, self.code, stdout="", stderr=self.stderr)


@pytest.fixture
def started(tmp_path, monkeypatch):
    """A starting preview recorded as the app records one; the worker's start, with Docker stood in for."""
    from app.tools import sandbox

    monkeypatch.setenv("PRODUCT_PREVIEW", "on")
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setenv("PRODUCT_PREVIEW_NETWORK", "preview-net")
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.delenv("SANDBOX_WORKSPACE_VOLUME", raising=False)
    monkeypatch.setenv("JWT_SECRET_KEY_FOR_THIS_TEST", "worker-secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-worker-secret")
    monkeypatch.setattr(sandbox, "_docker_binary", lambda: "docker")
    preview_worker.say_it_serves()
    root = _workspace(tmp_path / "workspaces" / "t" / "run")

    def start(source="accepted", docker=None):
        run_id = f"run-{uuid.uuid4().hex[:10]}"
        state = preview.start(run_id, str(root), source)
        docker = docker or _Docker()
        preview_worker.start({"run_id": run_id, "instance": state["instance"]}, run=docker)
        return preview.read(run_id), docker

    start.root = root
    return start


def test_the_accepted_sprint_starts_from_a_copy_of_its_files_with_the_installs(started):
    state, docker = started("accepted")

    copy = Path(state["scratch"])
    assert (copy / "server.js").read_text() == "// sprint one\n"
    assert not (copy / "routes.js").exists()
    assert (copy / "node_modules" / "left-pad" / "index.js").exists()
    assert not (copy / ".git").exists() and not (copy / ".harness" / "steering.json").exists()
    assert not (copy / ".agent-home" / "history").exists()
    assert state["running"] is True and state["command"] == "sh start.sh"
    assert len(docker.calls) == 1


def test_the_live_source_starts_from_the_files_as_they_are_now(started):
    state, _ = started("live")

    copy = Path(state["scratch"])
    assert (copy / "server.js").read_text() == "// being written\n"
    assert (copy / "routes.js").exists()


def test_a_write_by_the_product_to_its_own_file_leaves_the_workspace_alone(started):
    state, _ = started("live")

    (Path(state["scratch"]) / "server.js").write_text("changed by the product")

    assert (started.root / "server.js").read_text() == "// being written\n"


def test_the_container_is_restricted_on_the_preview_network_and_holds_no_worker_secret(started):
    state, docker = started("accepted")

    argv = docker.calls[0]
    joined = " ".join(argv)
    assert argv[:4] == ["docker", "run", "-d", "--rm"]
    assert argv[argv.index("--network") + 1] == "preview-net"
    assert argv[argv.index("--cap-drop") + 1] == "ALL" and "--read-only" in argv
    assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert argv[argv.index("-v") + 1] == f"{state['scratch']}:/workspace"
    assert str(started.root) + ":" not in joined
    assert f"PORT={state['port']}" in argv and "HOST=0.0.0.0" in argv
    assert "worker-secret-value" not in joined and "sk-worker-secret" not in joined
    assert argv[-2:] == ["sh", "start.sh"]


def test_a_product_with_nothing_to_start_fails_with_the_reason_and_no_container(started):
    for name in ("start.sh", "server.js"):
        (started.root / name).unlink()

    state, docker = started("live")

    assert state["state"] == "failed" and "no way to start" in state["reason"]
    assert docker.calls == []


def test_a_container_that_does_not_start_fails_the_preview_with_docker_s_words(started):
    state, _ = started("accepted", docker=_Docker(code=125, stderr="network preview-net not found"))

    assert state["state"] == "failed" and "network preview-net not found" in state["reason"]


def test_a_stop_ends_the_container_and_removes_the_copy(started):
    state, _ = started("accepted")
    docker = _Docker()

    preview_worker.stop({"run_id": state["run_id"], "instance": state["instance"]}, run=docker)

    assert docker.calls == [["docker", "kill", state["host"]]]
    assert not Path(state["scratch"]).exists()


def test_the_sweep_stops_an_idle_preview_and_leaves_a_used_one(started, monkeypatch):
    monkeypatch.setenv("PRODUCT_PREVIEW_IDLE_MINUTES", "15")
    idle, _ = started("accepted")
    used, _ = started("live")
    preview.write({**idle, "last_used": time.time() - 16 * 60})

    ended = preview_worker.end_the_idle()

    assert idle["run_id"] in ended and used["run_id"] not in ended
    assert preview.read(idle["run_id"])["state"] == "stopped"
    assert preview.read(used["run_id"])["state"] == "starting"


@pytest.fixture(autouse=True)
def _no_preview_left_from_another_test():
    from app.server.redis_client import get_redis_client

    client = get_redis_client()
    for key in client.scan_iter(match="devflow:preview:*"):
        client.delete(key)


def test_a_restarted_worker_ends_the_preview_containers_nobody_holds(started):
    held, _ = started("accepted")

    class _Listed(_Docker):
        def __call__(self, *argv):
            done = super().__call__(*argv)
            if "ps" in argv:
                done.stdout = f"{held['host']}\ndevflow-preview-0123456789ab-deadbeef\n"
            return done

    docker = _Listed()
    ended = preview_worker.end_the_orphans(run=docker)

    assert ended == ["devflow-preview-0123456789ab-deadbeef"]
    assert ["docker", "kill", held["host"]] not in docker.calls


# --- the port forwarder: a product that listens on the loopback only is still reached --------------------------------
#
# The container's command is run here for real: its environment from the --env flags, the workspace where the
# container mounts it, the image's PATH. A real container keeps the product's 127.0.0.1 to itself; here 127.0.0.2
# stands in for the app on another host: a socket bound to 127.0.0.1 does not answer it, one bound to 0.0.0.0 does.

_ELSEWHERE = "127.0.0.2"


def _a_free_port_pair():
    """A port, and the one 1000 above it, both free here."""
    import socket

    for _ in range(100):
        with socket.socket() as probe:
            probe.bind(("", 0))
            port = probe.getsockname()[1]
        if port + 1000 > 65535:
            continue
        try:
            with socket.socket() as above:
                above.bind(("", port + 1000))
        except OSError:
            continue
        return port
    pytest.skip("no free pair of ports on this machine")


def _the_product(scratch: Path, host: str, wait: float = 0.0) -> None:
    """The product the preview starts (`sh start.sh`): a plain HTTP server on the address it chose, whatever HOST says."""
    (scratch / "product.py").write_text(
        "import http.server, os, socket, time\n"
        f"time.sleep({wait})\n"
        "class Server(http.server.ThreadingHTTPServer):\n"
        f"    address_family = socket.AF_INET6 if ':' in {host!r} else socket.AF_INET\n"
        f"Server(({host!r}, int(os.environ['PORT'])), http.server.SimpleHTTPRequestHandler).serve_forever()\n"
    )
    (scratch / "start.sh").write_text("exec python3 product.py\n")


def _run_the_container_s_command(argv: list[str], scratch: Path, path: str):
    import re

    def here(value: str) -> str:
        return re.sub(r"/workspace(?![\w.-])", str(scratch), value)

    environment = dict(here(argv[i + 1]).split("=", 1) for i, part in enumerate(argv) if part == "--env")
    environment["PATH"] = path
    return subprocess.Popen([here(part) for part in argv[argv.index("/bin/sh"):]], cwd=here(argv[argv.index("-w") + 1]),
                            env=environment, start_new_session=True, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def _the_page(port: int, seconds: float) -> int | None:
    import urllib.request

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{_ELSEWHERE}:{port}/start.sh", timeout=1) as answered:
                return answered.status
        except OSError:
            time.sleep(0.1)
    return None


def _ended(process) -> None:
    import os
    import signal

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def _a_path_without_node(tmp_path: Path) -> str:
    import shutil
    import sys

    folder = tmp_path / "image-bin"
    folder.mkdir()
    (folder / "python3").symlink_to(sys.executable)
    (folder / "sh").symlink_to(shutil.which("sh"))
    return str(folder)


@pytest.fixture
def forwarded(started, monkeypatch):
    port = _a_free_port_pair()
    monkeypatch.setenv("PRODUCT_PREVIEW_PORTS", f"{port}-{port}")
    state, docker = started("accepted")
    return state, docker.calls[0], Path(state["scratch"])


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="Node is not installed on this machine")
@pytest.mark.parametrize("binds", ["127.0.0.1", "0.0.0.0", "::1"])
def test_a_product_listening_on_the_loopback_only_is_reached_through_the_forwarder(forwarded, binds):
    """A real deployment: a product that listened on 127.0.0.1 only could not be reached from the app's container.
    It gets an inner port; the forwarder answers on the preview's port on every address. A product that binds every
    address itself, or the IPv6 loopback, is reached the same way."""
    import os

    state, argv, scratch = forwarded
    _the_product(scratch, binds)

    process = _run_the_container_s_command(argv, scratch, os.environ["PATH"])
    try:
        status = _the_page(state["port"], 20)
    finally:
        _ended(process)

    assert status == 200


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="Node is not installed on this machine")
def test_the_preview_s_port_opens_only_once_the_product_answers(forwarded):
    """The app judges a start by the preview's port answering: a forwarder that answered at once would call a product
    ready that has not started."""
    import os

    state, argv, scratch = forwarded
    _the_product(scratch, "127.0.0.1", wait=3)

    process = _run_the_container_s_command(argv, scratch, os.environ["PATH"])
    try:
        early = _the_page(state["port"], 1)
        later = _the_page(state["port"], 20)
    finally:
        _ended(process)

    assert early is None and later == 200


def test_an_image_without_node_starts_the_product_on_the_preview_s_own_port(forwarded, tmp_path):
    state, argv, scratch = forwarded
    _the_product(scratch, "0.0.0.0")

    process = _run_the_container_s_command(argv, scratch, _a_path_without_node(tmp_path))
    try:
        status = _the_page(state["port"], 20)
    finally:
        _ended(process)

    assert status == 200
    assert "no Node" in (scratch / ".preview" / "output.log").read_text()


def test_a_product_that_never_answers_without_a_forwarder_is_told_to_listen_on_host(forwarded, tmp_path,
                                                                                      monkeypatch):
    monkeypatch.setenv("PRODUCT_PREVIEW_IDLE_MINUTES", "100000")
    state, argv, scratch = forwarded
    (scratch / "start.sh").write_text("exec python3 -c 'import time; time.sleep(60)'\n")
    process = _run_the_container_s_command(argv, scratch, _a_path_without_node(tmp_path))
    try:
        deadline = time.monotonic() + 10
        while "no Node" not in _read(scratch / ".preview" / "output.log") and time.monotonic() < deadline:
            time.sleep(0.1)

        failed = preview.observe(state["run_id"], now=time.time() + 3600, answers=lambda host, port: False)
    finally:
        _ended(process)

    assert failed["state"] == "failed" and "HOST" in failed["reason"] and "Node" in failed["reason"]


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""
