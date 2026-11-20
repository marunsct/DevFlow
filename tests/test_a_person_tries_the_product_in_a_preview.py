"""A person starts the product from the run page and uses it through the app (plan WS.4, switch PRODUCT_PREVIEW).

The owner asked to run and check the product in the browser while it is built. What must hold: only a signed-in
operator of the run's tenant starts, reads or stops a preview, and every start and stop is audited; one preview per
run; the product is reached only through a short-lived link signed for that run and that preview; nothing of the
browser's sign-in or cookies reaches the product, and every request goes to the preview's own host and port whatever
its path says; its page never runs with the app's origin; a preview nobody uses is stopped; a product that fails to
start says why in its own error lines.

The product is a real HTTP server on this machine standing in for the preview's container (Docker is the worker's;
its half is tested in `test_the_worker_starts_a_preview_in_its_own_container.py`).
"""
from __future__ import annotations

import http.server
import json
import subprocess
import threading
import time
import uuid
from types import SimpleNamespace

import pytest

from app.server import preview


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _workspace(root, *, sprint_accepted=True):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "h@example.com")
    _git(root, "config", "user.name", "harness")
    (root / "start.sh").write_text("node server.js\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "Scaffold: a stack")
    if sprint_accepted:
        _git(root, "tag", "sprint-1")
    return root


@pytest.fixture
def audited(monkeypatch):
    from app.server import runs

    lines: list[dict] = []
    monkeypatch.setattr(runs, "record_audit", lambda **kwargs: lines.append(kwargs))
    return lines


def _the_worker_serves(monkeypatch, mode):
    """The worker's preview loop says it serves, with the worker's setting; the app keeps its own, as deployed (only
    the worker carries SANDBOX_EXECUTION_MODE=container)."""
    from app.server import preview_worker

    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", mode)
    preview_worker.say_it_serves()
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")


@pytest.fixture
def preview_on(monkeypatch, tmp_path):
    monkeypatch.setenv("PRODUCT_PREVIEW", "on")
    monkeypatch.setenv("PRODUCT_PREVIEW_NETWORK", "preview-net")
    monkeypatch.setenv("WORKFLOW_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.delenv("PRODUCT_PREVIEW_ORIGIN", raising=False)
    _the_worker_serves(monkeypatch, "container")


def _client(root, run_id, *, tenant="t"):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.server import runs
    from app.server.auth import get_current_active_user, require_operator

    run = SimpleNamespace(run_id=run_id, tenant_id="t", status="running", repo_root=str(root))
    runner = SimpleNamespace(run_store=SimpleNamespace(load=lambda wanted: run if wanted == run_id else None))
    app = FastAPI()
    app.include_router(runs.create_runs_router(runner, SimpleNamespace(), str(root), str(root)))
    user = SimpleNamespace(username="owner", role="operator", tenant_id=tenant)
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[require_operator] = lambda: user
    return TestClient(app)


def _a_run():
    return f"run-{uuid.uuid4().hex[:10]}"


def _worker_requests(run_id):
    from app.server.redis_client import get_redis_client

    # Pushed on the left and taken from the right: oldest last in the list.
    raw = list(reversed(get_redis_client().lrange("devflow:preview:requests", 0, -1)))
    return [r for r in (json.loads(item) for item in raw) if r.get("run_id") == run_id]


class _Product(http.server.BaseHTTPRequestHandler):
    """The product: answers every path, recording what reached it."""

    seen: list[dict] = []
    page = b"<html><head><title>p</title></head><body><script src=\"/app.js\"></script></body></html>"

    def _answer(self):
        length = int(self.headers.get("content-length") or 0)
        _Product.seen.append({"method": self.command, "path": self.path, "headers": dict(self.headers),
                              "body": self.rfile.read(length) if length else b""})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Set-Cookie", "product_session=1; Path=/")
        self.end_headers()
        self.wfile.write(_Product.page)

    do_GET = do_POST = _answer

    def log_message(self, *args):  # quiet
        pass


@pytest.fixture
def product():
    _Product.seen = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Product)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


def _a_ready_preview(client, run_id, port, **changes):
    """Started through the API, then as the worker leaves it running at the product's address; its link."""
    assert client.post(f"/api/runs/{run_id}/preview", json={"source": "accepted"}).status_code == 200
    state = preview.read(run_id)
    preview.write({**state, "host": "127.0.0.1", "port": port, "running": True, **changes})
    shown = client.get(f"/api/runs/{run_id}/preview").json()
    assert shown["state"] == "ready", shown
    return shown["url"]


def test_with_the_switch_off_nothing_starts_and_the_page_says_so(tmp_path, monkeypatch, audited):
    monkeypatch.setenv("PRODUCT_PREVIEW", "off")
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)

    refused = client.post(f"/api/runs/{run_id}/preview")

    assert refused.status_code == 403
    assert client.get(f"/api/runs/{run_id}/preview").json()["state"] == "off"
    assert _worker_requests(run_id) == [] and audited == []


def test_a_start_from_the_accepted_sprint_asks_the_worker_and_is_audited(tmp_path, preview_on, audited):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)

    started = client.post(f"/api/runs/{run_id}/preview")

    assert started.status_code == 200
    assert (started.json()["state"], started.json()["source"], started.json()["label"]) == (
        "starting", "accepted", "sprint 1")
    assert "url" not in started.json() or started.json()["url"] is None
    assert [r["action"] for r in _worker_requests(run_id)] == ["start"]
    assert [line["action"] for line in audited] == ["run.preview.start"]
    assert 42000 <= preview.read(run_id)["port"] <= 42019


def test_one_preview_per_run(tmp_path, preview_on, audited):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    client.post(f"/api/runs/{run_id}/preview", json={"source": "live"})

    again = client.post(f"/api/runs/{run_id}/preview", json={"source": "accepted"})

    assert again.status_code == 409
    assert [r["action"] for r in _worker_requests(run_id)] == ["start"]


def test_the_accepted_sprint_needs_one_and_the_live_workspace_does_not(tmp_path, preview_on, audited):
    run_id = _a_run()
    client = _client(_workspace(tmp_path, sprint_accepted=False), run_id)

    assert client.post(f"/api/runs/{run_id}/preview", json={"source": "accepted"}).status_code == 409
    live = client.post(f"/api/runs/{run_id}/preview", json={"source": "live"})
    assert (live.status_code, live.json()["label"]) == (200, "being built")


def test_another_tenant_s_operator_cannot_start_read_or_stop_it(tmp_path, preview_on, audited):
    run_id = _a_run()
    stranger = _client(_workspace(tmp_path), run_id, tenant="other")

    assert stranger.post(f"/api/runs/{run_id}/preview").status_code == 404
    assert stranger.get(f"/api/runs/{run_id}/preview").status_code == 404
    assert stranger.delete(f"/api/runs/{run_id}/preview").status_code == 404
    assert _worker_requests(run_id) == []


def test_a_worker_that_runs_commands_in_itself_has_no_container_for_a_preview(tmp_path, preview_on, monkeypatch,
                                                                              audited):
    _the_worker_serves(monkeypatch, "in-container")
    run_id = _a_run()

    refused = _client(_workspace(tmp_path), run_id).post(f"/api/runs/{run_id}/preview")

    assert refused.status_code == 409 and "SANDBOX_EXECUTION_MODE" in refused.json()["detail"]
    assert _worker_requests(run_id) == []


def test_with_no_worker_serving_previews_a_start_is_refused_as_unavailable(tmp_path, preview_on, audited):
    """A real deployment: the app's start was refused as if commands ran in-process, because it read its own
    SANDBOX_EXECUTION_MODE, which only the worker carries. With no worker's word, the start waits for a worker."""
    from app.server.redis_client import get_redis_client

    get_redis_client().delete("devflow:preview:worker")
    run_id = _a_run()

    refused = _client(_workspace(tmp_path), run_id).post(f"/api/runs/{run_id}/preview")

    assert refused.status_code == 503 and "worker" in refused.json()["detail"]
    assert _worker_requests(run_id) == [] and audited == []


def test_the_worker_s_preview_loop_says_it_serves_and_the_app_starts_on_its_word(tmp_path, preview_on, monkeypatch,
                                                                                 audited):
    """The app's own setting says in-container; the worker's says container. One pass of the worker's loop is what
    lets the app start a preview."""
    from app.server import preview_worker
    from app.server.redis_client import get_redis_client

    redis = get_redis_client()
    redis.delete("devflow:preview:worker", "devflow:preview:requests")
    redis.lpush("devflow:preview:requests", "{}")  # something to take, so the pass does not wait
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    passes = iter([False, True])
    preview_worker.serve_for_ever(stop_when=lambda: next(passes))
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "in-container")
    run_id = _a_run()

    started = _client(_workspace(tmp_path), run_id).post(f"/api/runs/{run_id}/preview")

    assert started.status_code == 200, started.text
    assert redis.ttl("devflow:preview:worker") > 0  # it lapses when the worker stops saying it


def test_the_product_is_served_through_the_signed_link_without_the_browser_s_cookies(tmp_path, preview_on, audited,
                                                                                    product):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    url = _a_ready_preview(client, run_id, product)

    shown = client.post(url + "api/items?x=1", content=b'{"name": "a"}', headers={
        "Cookie": "app_session=secret", "Authorization": "Bearer app-token", "Content-Type": "application/json",
        "X-Forwarded-For": "10.0.0.1"})

    assert shown.status_code == 200
    reached = _Product.seen[-1]
    assert (reached["method"], reached["path"], reached["body"]) == ("POST", "/api/items?x=1", b'{"name": "a"}')
    sent = {key.lower() for key in reached["headers"]}
    assert not sent & {"cookie", "authorization", "x-forwarded-for"}
    assert {k.lower(): v for k, v in reached["headers"].items()}["content-type"] == "application/json"
    assert "set-cookie" not in {key.lower() for key in shown.headers}
    csp = shown.headers["content-security-policy"]
    assert "sandbox" in csp and "allow-scripts" in csp and "allow-same-origin" not in csp


def test_a_page_s_paths_from_the_root_are_pointed_under_the_link(tmp_path, preview_on, audited, product):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    url = _a_ready_preview(client, run_id, product)

    page = client.get(url).text

    assert f'src="{url}app.js"' in page


@pytest.mark.parametrize("path", ["//elsewhere.example/x", "http://elsewhere.example/x", "%2e%2e/%2e%2e/x", "@elsewhere.example/x"])
def test_every_path_goes_to_the_preview_s_own_host_and_port(tmp_path, preview_on, audited, product, path):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    url = _a_ready_preview(client, run_id, product)
    before = len(_Product.seen)

    answered = client.get(url + path)

    assert answered.status_code == 200
    assert len(_Product.seen) == before + 1
    assert {k.lower(): v for k, v in _Product.seen[-1]["headers"].items()}["host"] == f"127.0.0.1:{product}"


def test_with_a_separate_origin_the_product_is_served_only_there(tmp_path, preview_on, audited, product, monkeypatch):
    monkeypatch.setenv("PRODUCT_PREVIEW_ORIGIN", "https://preview.example")
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    link = _a_ready_preview(client, run_id, product)
    path = link.removeprefix("https://preview.example")

    on_the_app_s_host = client.get(path)
    on_its_own = client.get(path, headers={"Host": "preview.example"})

    assert link.startswith("https://preview.example/api/runs/")
    assert on_the_app_s_host.status_code == 403
    assert on_its_own.status_code == 200 and "allow-same-origin" in on_its_own.headers["content-security-policy"]


def test_a_link_opens_only_its_own_run_s_current_preview_until_it_expires(tmp_path, preview_on, audited, product):
    run_id, other = _a_run(), _a_run()
    client = _client(_workspace(tmp_path), run_id)
    url = _a_ready_preview(client, run_id, product)
    instance = preview.read(run_id)["instance"]
    token = url.rstrip("/").rsplit("/", 1)[1]
    before = len(_Product.seen)

    expired = preview.token_for(run_id, instance, int(time.time()) - 1)
    forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    for wrong in (f"/api/runs/{run_id}/preview/app/{expired}/", f"/api/runs/{run_id}/preview/app/{forged}/",
                  f"/api/runs/{run_id}/preview/app/not-a-token/", url.replace(run_id, other)):
        assert client.get(wrong).status_code == 403, wrong
    assert client.get(url).status_code == 200
    assert len(_Product.seen) == before + 1


def test_a_stopped_preview_s_link_opens_nothing_and_the_worker_is_asked_to_end_it(tmp_path, preview_on, audited,
                                                                                  product):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    url = _a_ready_preview(client, run_id, product)

    stopped = client.delete(f"/api/runs/{run_id}/preview")

    assert (stopped.status_code, stopped.json()["state"]) == (200, "stopped")
    assert client.get(url).status_code == 403
    assert [r["action"] for r in _worker_requests(run_id)] == ["start", "stop"]
    assert [line["action"] for line in audited] == ["run.preview.start", "run.preview.stop"]
    # A new preview has a new link; the old one still opens nothing.
    client.post(f"/api/runs/{run_id}/preview")
    preview.write({**preview.read(run_id), "host": "127.0.0.1", "port": product, "running": True})
    assert client.get(f"/api/runs/{run_id}/preview").json()["url"] != url
    assert client.get(url).status_code == 403


def test_a_preview_nobody_uses_is_stopped(tmp_path, preview_on, audited, monkeypatch):
    monkeypatch.setenv("PRODUCT_PREVIEW_IDLE_MINUTES", "15")
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    client.post(f"/api/runs/{run_id}/preview")
    preview.write({**preview.read(run_id), "last_used": time.time() - 16 * 60})

    shown = client.get(f"/api/runs/{run_id}/preview").json()

    assert shown["state"] == "stopped" and "15 minutes" in shown["reason"]
    assert [r["action"] for r in _worker_requests(run_id)] == ["start", "stop"]


def test_a_product_that_exits_at_start_shows_its_own_error_lines(tmp_path, preview_on, audited):
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    client.post(f"/api/runs/{run_id}/preview")
    output = preview.scratch_for(run_id, preview.read(run_id)["instance"]) / ".preview"
    output.mkdir(parents=True)
    frames = "\n".join(f"    at Object.<anonymous> (/workspace/server.js:{n}:5)" for n in range(400))
    (output / "output.log").write_text(f"Error: SQLITE_ERROR: near \"TABEL\": syntax error\n{frames}\n")
    (output / "exit-code").write_text("1\n")

    shown = client.get(f"/api/runs/{run_id}/preview").json()

    assert shown["state"] == "failed"
    assert "exit code 1" in shown["reason"]
    assert 'near "TABEL": syntax error' in shown["error"]


def test_a_product_that_never_answers_fails_after_the_start_time(tmp_path, preview_on, audited, monkeypatch):
    monkeypatch.setenv("PRODUCT_PREVIEW_START_SECONDS", "60")
    run_id = _a_run()
    client = _client(_workspace(tmp_path), run_id)
    client.post(f"/api/runs/{run_id}/preview")
    state = preview.read(run_id)
    # Nothing listens on the port: a port this machine just gave up.
    preview.write({**state, "host": "127.0.0.1", "port": 9, "running": True, "started_at": time.time() - 61})

    shown = client.get(f"/api/runs/{run_id}/preview").json()

    assert shown["state"] == "failed" and "did not answer" in shown["reason"]


def test_a_preview_s_page_may_ask_the_preview_across_origins_without_the_app_s_cors_rules(client, preview_on,
                                                                                         product):
    """Its page has an opaque origin (`Origin: null`): the app's own CORS list refused its preflight before."""
    run_id = _a_run()
    instance = uuid.uuid4().hex[:16]
    preview.write({"run_id": run_id, "instance": instance, "state": "ready", "host": "127.0.0.1", "port": product,
                   "scratch": "/nonexistent", "started_at": time.time(), "last_used": time.time()})
    token = preview.token_for(run_id, instance, int(time.time()) + 600)

    answered = client.options(f"/api/runs/{run_id}/preview/app/{token}/api/items", headers={
        "Origin": "null", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})

    assert answered.status_code == 204
    assert answered.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in answered.headers


def test_the_app_s_own_paths_keep_its_cors_rules(client):
    refused = client.options("/api/runs", headers={"Origin": "null", "Access-Control-Request-Method": "POST"})

    assert refused.status_code == 400
    assert "access-control-allow-origin" not in refused.headers


@pytest.fixture(autouse=True)
def _no_preview_left_from_another_test():
    from app.server.redis_client import get_redis_client

    client = get_redis_client()
    for key in client.scan_iter(match="devflow:preview:*"):
        client.delete(key)
