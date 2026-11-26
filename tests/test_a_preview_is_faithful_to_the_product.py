"""A preview a product can be tested in (plans UX.9-UX.11, behind PRODUCT_PREVIEW).

The preview research (2026-11-25) found that a product which signs in, streams or keeps a live connection could not
be tried in the preview: cookies were dropped both ways, every answer was read whole before it was sent, a WebSocket
upgrade had no route, and the preview never said it was behind the build. What must hold now:

- on a separate preview origin the product's cookies pass, host-only and scoped to the run's previews; on the app's
  host they still never do; with wildcard DNS each run gets a host of its own; the preview origin answers nothing of
  the app's own API;
- an event stream's first chunk reaches the browser before the product has finished the answer;
- a WebSocket upgrade with a good link is relayed both ways; one with a bad or expired link is refused;
- the status names the commit the preview runs and says when a newer accepted sprint (or, for the workspace being
  built, a newer commit) is ready, and a restart replaces the running preview with it.

The product is a real server on this machine standing in for the preview's container.
"""
from __future__ import annotations

import http.server
import json
import socket
import subprocess
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from app.server import preview


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _workspace(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "h@example.com")
    _git(root, "config", "user.name", "harness")
    (root / "start.sh").write_text("node server.js\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Scaffold: a stack")
    _git(root, "tag", "sprint-1")
    return root


def _commit(root, name, text):
    (root / name).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"Write {name}")


def _head(root):
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def preview_on(monkeypatch, tmp_path):
    from app.server import preview_worker, runs

    monkeypatch.setenv("PRODUCT_PREVIEW", "on")
    monkeypatch.setenv("PRODUCT_PREVIEW_NETWORK", "preview-net")
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.delenv("PRODUCT_PREVIEW_ORIGIN", raising=False)
    monkeypatch.setattr(runs, "record_audit", lambda **kwargs: None)
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    preview_worker.say_it_serves()
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")


def _app(root, run_ids):
    from fastapi import FastAPI

    from app.server import runs
    from app.server.auth import get_current_active_user, require_operator

    found = {run_id: SimpleNamespace(run_id=run_id, tenant_id="t", status="running", repo_root=str(root))
             for run_id in run_ids}
    runner = SimpleNamespace(run_store=SimpleNamespace(load=found.get))
    app = FastAPI()
    app.include_router(runs.create_runs_router(runner, SimpleNamespace(), str(root), str(root)))
    user = SimpleNamespace(username="owner", role="operator", tenant_id="t")
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[require_operator] = lambda: user
    return app


def _client(root, *run_ids):
    from fastapi.testclient import TestClient

    return TestClient(_app(root, run_ids))


def _a_run():
    return f"run-{uuid.uuid4().hex[:10]}"


def _a_ready_preview(client, run_id, port, source="accepted"):
    """Started through the API, then as the worker leaves it running at the product's address; its status."""
    assert client.post(f"/api/runs/{run_id}/preview", json={"source": source}).status_code == 200
    preview.write({**preview.read(run_id), "host": "127.0.0.1", "port": port, "running": True})
    shown = client.get(f"/api/runs/{run_id}/preview").json()
    assert shown["state"] == "ready", shown
    return shown


def _worker_requests(run_id):
    from app.server.redis_client import get_redis_client

    raw = list(reversed(get_redis_client().lrange("devflow:preview:requests", 0, -1)))
    return [r for r in (json.loads(item) for item in raw) if r.get("run_id") == run_id]


class _SignsIn(http.server.BaseHTTPRequestHandler):
    """A product that signs a person in with cookies, one of them for a parent domain."""

    seen: list[dict] = []

    def do_GET(self):  # noqa: N802 - the server's own name
        _SignsIn.seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Set-Cookie", "sid=abc123; Domain=example.com; Path=/; HttpOnly; SameSite=Lax")
        self.send_header("Set-Cookie", "theme=dark; Path=/account")
        self.end_headers()
        self.wfile.write(b'{"signed_in": true}')

    def log_message(self, *args):
        pass


@pytest.fixture
def signs_in():
    _SignsIn.seen = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SignsIn)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


# --- UX.9: a separate origin, the product's cookies on it only -------------------------------------------------------


def test_on_a_separate_origin_the_product_s_cookies_pass_host_only_and_scoped_to_the_run(tmp_path, preview_on,
                                                                                        monkeypatch, signs_in):
    monkeypatch.setenv("PRODUCT_PREVIEW_ORIGIN", "https://preview.example.com")
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    link = _a_ready_preview(client, run_id, signs_in)["url"].removeprefix("https://preview.example.com")

    answered = client.get(link + "me", headers={"Host": "preview.example.com", "Cookie": "sid=abc123"})

    assert answered.status_code == 200
    assert _SignsIn.seen[-1]["headers"].get("cookie") == "sid=abc123"
    scope = f"/api/runs/{run_id}/preview/app/"
    assert answered.headers.get_list("set-cookie") == [
        f"sid=abc123; HttpOnly; SameSite=Lax; Path={scope}", f"theme=dark; Path={scope}"]


def test_on_the_app_s_own_host_the_product_s_cookies_pass_neither_way(tmp_path, preview_on, signs_in):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    link = _a_ready_preview(client, run_id, signs_in)["url"]

    answered = client.get(link + "me", headers={"Cookie": "sid=abc123"})

    assert answered.status_code == 200
    assert "cookie" not in _SignsIn.seen[-1]["headers"]
    assert answered.headers.get_list("set-cookie") == []


def test_with_wildcard_dns_each_run_s_preview_has_a_host_of_its_own(tmp_path, preview_on, monkeypatch, signs_in):
    monkeypatch.setenv("PRODUCT_PREVIEW_ORIGIN", "https://*.preview.example.com")
    first, second = _a_run(), _a_run()
    client = _client(_workspace(tmp_path), first, second)
    one = _a_ready_preview(client, first, signs_in)["url"]
    other = _a_ready_preview(client, second, signs_in)["url"]
    own_host = one.split("/")[2]

    on_its_own = client.get(one.split(own_host, 1)[1], headers={"Host": own_host})
    on_another_s = client.get(one.split(own_host, 1)[1], headers={"Host": other.split("/")[2]})

    assert own_host.endswith(".preview.example.com") and own_host != other.split("/")[2]
    assert "*" not in one + other
    assert on_its_own.status_code == 200
    assert on_another_s.status_code == 403
    assert on_its_own.headers.get_list("set-cookie")[0] == "sid=abc123; HttpOnly; SameSite=Lax; Path=/"


@pytest.mark.parametrize("origin, host", [
    ("https://preview.example.com", "preview.example.com"),
    ("https://*.preview.example.com", "p0123456789abcdef.preview.example.com"),
])
def test_a_preview_origin_answers_nothing_of_the_app_s_own(client, monkeypatch, origin, host):
    """A product's script runs with the preview origin and may ask it anything: the app's API is not there."""
    monkeypatch.setenv("PRODUCT_PREVIEW_ORIGIN", origin)

    on_the_preview_host = client.get("/api/health", headers={"Host": host})
    on_the_app_s_host = client.get("/api/health")

    assert on_the_preview_host.status_code == 404
    assert on_the_app_s_host.status_code == 200


# --- UX.10: streams and WebSockets -----------------------------------------------------------------------------------


class _Streams(http.server.BaseHTTPRequestHandler):
    """An event stream: one event, then it holds the answer open until told to finish (or a few seconds pass)."""

    protocol_version = "HTTP/1.1"
    released = threading.Event()
    finished = threading.Event()

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self._chunk(b"data: first\n\n")
        _Streams.released.wait(4)
        _Streams.finished.set()
        self._chunk(b"data: last\n\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _chunk(self, data):
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def log_message(self, *args):
        pass


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def served(tmp_path):
    """The app served for real (the test client reads an answer whole, which would hide a stream)."""
    import uvicorn

    servers = []

    def serve(app):
        port = _free_port()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off"))
        threading.Thread(target=server.run, daemon=True).start()
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        servers.append(server)
        return f"http://127.0.0.1:{port}"

    yield serve
    for server in servers:
        server.should_exit = True


def test_an_event_stream_s_first_chunk_arrives_before_the_product_finishes(tmp_path, preview_on, served):
    import httpx

    _Streams.released.clear()
    _Streams.finished.clear()
    product = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Streams)
    threading.Thread(target=product.serve_forever, daemon=True).start()
    run_id = _a_run()
    app = _app(_workspace(tmp_path), [run_id])
    base = served(app)
    with httpx.Client(base_url=base, timeout=10) as browser:
        assert browser.post(f"/api/runs/{run_id}/preview", json={"source": "accepted"}).status_code == 200
        preview.write({**preview.read(run_id), "host": "127.0.0.1", "port": product.server_address[1],
                       "running": True})
        link = browser.get(f"/api/runs/{run_id}/preview").json()["url"]

        with browser.stream("GET", link + "events") as answer:
            chunks = answer.iter_bytes()
            first = next(chunks)
            finished_before_the_first_chunk = _Streams.finished.is_set()
            _Streams.released.set()
            rest = b"".join(chunks)
    product.shutdown()

    assert answer.status_code == 200 and answer.headers["content-type"].startswith("text/event-stream")
    assert first.startswith(b"data: first")
    assert not finished_before_the_first_chunk
    assert b"data: last" in first + rest


@pytest.fixture
def echoes():
    """A product's WebSocket that echoes each message, and says which subprotocol it was asked for."""
    from websockets.sync.server import serve

    def answer(connection):
        for message in connection:
            connection.send(message)

    server = serve(answer, "127.0.0.1", 0, subprotocols=["vite-hmr"])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.socket.getsockname()[1]
    server.shutdown()


def test_a_websocket_with_a_good_link_is_relayed_both_ways(tmp_path, preview_on, echoes):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    link = _a_ready_preview(client, run_id, echoes)["url"]

    with client.websocket_connect(link + "hmr", subprotocols=["vite-hmr"]) as socket_:
        socket_.send_text("hello")
        heard = socket_.receive_text()
        socket_.send_bytes(b"\x00\x01")
        heard_bytes = socket_.receive_bytes()
        chosen = socket_.accepted_subprotocol

    assert (heard, heard_bytes, chosen) == ("hello", b"\x00\x01", "vite-hmr")


def test_a_websocket_with_a_bad_or_expired_link_is_refused(tmp_path, preview_on, echoes):
    from starlette.websockets import WebSocketDisconnect

    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    _a_ready_preview(client, run_id, echoes)
    expired = preview.token_for(run_id, preview.read(run_id)["instance"], int(time.time()) - 1)

    for token in (expired, "not-a-token"):
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect(f"/api/runs/{run_id}/preview/app/{token}/hmr") as socket_:
                socket_.receive_text()
        assert refused.value.code == 1008


# --- UX.11: follow the build -----------------------------------------------------------------------------------------


def test_the_status_names_the_sprint_s_commit_and_says_when_a_later_sprint_is_accepted(tmp_path, preview_on,
                                                                                      signs_in):
    root = _workspace(tmp_path)
    run_id = _a_run()
    client = _client(root, run_id)
    sprint_one = _head(root)
    shown = _a_ready_preview(client, run_id, signs_in)
    _commit(root, "routes.js", "// sprint two\n")
    later = client.get(f"/api/runs/{run_id}/preview").json()
    _git(root, "tag", "sprint-2")

    behind = client.get(f"/api/runs/{run_id}/preview").json()

    assert sprint_one.startswith(shown["commit"]) and (shown["behind"], shown["newer"]) == (False, None)
    assert later["behind"] is False  # a commit is not an accepted sprint
    assert (behind["behind"], behind["newer"], behind["label"]) == (True, "sprint 2", "sprint 1")


def test_the_workspace_being_built_is_behind_once_a_stage_commits(tmp_path, preview_on, signs_in):
    root = _workspace(tmp_path)
    run_id = _a_run()
    client = _client(root, run_id)
    _a_ready_preview(client, run_id, signs_in, source="live")
    (root / "half-written.js").write_text("function (")
    written = client.get(f"/api/runs/{run_id}/preview").json()
    _commit(root, "half-written.js", "function done() {}\n")

    committed = client.get(f"/api/runs/{run_id}/preview").json()

    assert written["behind"] is False  # writes are not followed: half-written files would break the page
    assert committed["behind"] is True and committed["newer"] == f"commit {_head(root)[:7]}"


def test_a_restart_replaces_the_running_preview_with_the_newer_version(tmp_path, preview_on, signs_in):
    root = _workspace(tmp_path)
    run_id = _a_run()
    client = _client(root, run_id)
    _a_ready_preview(client, run_id, signs_in)
    _commit(root, "routes.js", "// sprint two\n")
    _git(root, "tag", "sprint-2")

    restarted = client.post(f"/api/runs/{run_id}/preview", json={"source": "accepted", "restart": True})

    assert restarted.status_code == 200
    assert (restarted.json()["state"], restarted.json()["label"], restarted.json()["behind"]) == (
        "starting", "sprint 2", False)
    assert [r["action"] for r in _worker_requests(run_id)] == ["start", "stop", "start"]
    assert restarted.json()["commit"] == _head(root)[:12]


@pytest.fixture(autouse=True)
def _no_preview_left_from_another_test():
    from app.server.redis_client import get_redis_client

    client = get_redis_client()
    for key in client.scan_iter(match="devflow:preview:*"):
        client.delete(key)
