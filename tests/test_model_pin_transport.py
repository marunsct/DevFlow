"""A run pinned to a model keeps sending to it; unpinning it moves the next request to the model in the settings.

Two fake model servers on 127.0.0.1 stand for the owner's two: A requires the configured key and names its model
one way; B needs no key, so it fails the test if it is sent any Authorization header at all. A real chat client
built by `build_default_chat_model` sends real requests through the real httpx transport.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from app.models import model_pin

RUN = "the-run-under-test"


class _FakeModelServer:
    """A stdlib HTTP server that records what it receives and answers like a chat server."""

    def __init__(self, model_name: str, required_key: str | None = None) -> None:
        self.model_name = model_name
        self.required_key = required_key
        self.seen: list[dict] = []
        self.release = threading.Event()
        self.hold_first = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.seen.append({
                    "path": self.path, "authorization": self.headers.get("Authorization"),
                    "host": self.headers.get("Host"), "model": body.get("model"), "stream": body.get("stream"),
                })
                if outer.hold_first and len(outer.seen) == 1:
                    outer.release.wait(10)
                if outer.required_key and self.headers.get("Authorization") != f"Bearer {outer.required_key}":
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if body.get("stream"):
                    chunks = [
                        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": outer.model_name,
                         "choices": [{"index": 0, "delta": {"role": "assistant", "content": f"from {outer.model_name}"},
                                      "finish_reason": None}]},
                        {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": outer.model_name,
                         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                    ]
                    data = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(data.encode())))
                    self.end_headers()
                    self.wfile.write(data.encode())
                    return
                reply = json.dumps({
                    "id": "c", "object": "chat.completion", "created": 1, "model": outer.model_name,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": f"from {outer.model_name}"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class _FakeRunStore:
    """The two columns of the run row the pin reads and writes."""

    def __init__(self) -> None:
        self.pinned = False
        self.last: dict[str, str] = {}
        self.writes = 0

    def model_state(self, run_id):
        return (self.pinned, dict(self.last))

    def set_model_last(self, run_id, snapshot):
        if self.pinned:
            return False
        self.last = dict(snapshot)
        self.writes += 1
        return True


@pytest.fixture
def two_servers(monkeypatch):
    """Server A (needs the configured key, is the settings' model) and server B (no key, pinned to by the run)."""
    from app.models.router import ModelRouter
    from app.server import runtime_settings

    a = _FakeModelServer("model-a", required_key="key-of-a")
    b = _FakeModelServer("model-b")
    store = _FakeRunStore()
    for name in ("OPENAI_API_KEY", "JUDGEMENT_MODEL", "JUDGEMENT_BASE_URL", "JUDGEMENT_PROVIDER",
                 "MODEL_CONTEXT_WINDOW", "MODEL_MAX_OUTPUT_TOKENS", "OPENAI_ENDPOINT_KIND"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("OPENAI_BASE_URL", a.url)
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setattr(runtime_settings, "overrides", lambda **_: {})
    monkeypatch.setattr(runtime_settings, "secrets", lambda **_: {"openai_api_key": "key-of-a"})
    monkeypatch.setattr(runtime_settings, "endpoint_keys", lambda: {})
    monkeypatch.setattr(model_pin, "_store", lambda: store)
    monkeypatch.setattr(model_pin, "STATE_TTL_SECONDS", 0.0)
    model_pin.forget()
    ModelRouter.reset()
    store.b_snapshot = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": b.url, "OPENAI_MODEL": "model-b"}
    yield a, b, store
    a.stop()
    b.stop()
    model_pin.forget()
    ModelRouter.reset()


def _chat():
    """The client a stage builds from the settings as they are now, as the harness builds it."""
    from app.models import build_default_chat_model

    return build_default_chat_model()


def test_a_run_that_is_not_pinned_sends_exactly_what_it_always_did(two_servers):
    """Unpinned, with the settings unchanged, a request reaches A with A's name and A's key, untouched."""
    a, b, store = two_servers
    with model_pin.as_the_run(RUN):
        reply = _chat().invoke("hi")
    assert reply.content == "from model-a"
    assert a.seen[0]["model"] == "model-a" and a.seen[0]["authorization"] == "Bearer key-of-a"
    assert b.seen == []


def test_a_pinned_run_reaches_b_with_b_s_name_and_no_authorization_at_all(two_servers):
    """Pinned to B while the settings name A: the address, the model field and the key all become B's - B has none."""
    a, b, store = two_servers
    store.pinned, store.last = True, store.b_snapshot
    with model_pin.as_the_run(RUN):
        client = _chat()
        reply = client.invoke("hi")
    assert reply.content == "from model-b"
    assert a.seen == []
    assert len(b.seen) == 1
    assert b.seen[0]["model"] == "model-b"
    assert b.seen[0]["authorization"] is None, "server A's key must never be sent to server B"


def test_a_client_built_before_the_pin_is_rerouted_at_send_time(two_servers):
    """The client was built for A; pinning afterwards moves its very next request to B, with B's model field."""
    a, b, store = two_servers
    with model_pin.as_the_run(RUN):
        client = _chat()
        client.invoke("first")
        store.pinned, store.last = True, store.b_snapshot
        client.invoke("second")
    assert [s["model"] for s in a.seen] == ["model-a"]
    assert [s["model"] for s in b.seen] == ["model-b"]
    assert b.seen[0]["authorization"] is None


def test_unpinning_mid_run_sends_the_next_request_to_the_settings_model_with_its_key(two_servers):
    """Pin on -> B (no key); pin off -> the next request reaches A with A's name and A's key."""
    a, b, store = two_servers
    store.pinned, store.last = True, store.b_snapshot
    with model_pin.as_the_run(RUN):
        client = _chat()
        client.invoke("one")
        store.pinned = False
        client.invoke("two")
    assert [s["model"] for s in b.seen] == ["model-b"] and b.seen[0]["authorization"] is None
    assert [s["model"] for s in a.seen] == ["model-a"]
    assert a.seen[0]["authorization"] == "Bearer key-of-a"


def test_an_unpinned_run_follows_the_settings_and_records_where_it_ran(two_servers, monkeypatch):
    """Unpinned, the settings changing to B moves the next request to B, and model_last says where it last ran."""
    a, b, store = two_servers
    with model_pin.as_the_run(RUN):
        client = _chat()
        client.invoke("one")
        assert store.last["OPENAI_BASE_URL"] == a.url
        monkeypatch.setenv("OPENAI_BASE_URL", b.url)
        monkeypatch.setenv("OPENAI_MODEL", "model-b")
        client.invoke("two")
    assert [s["model"] for s in b.seen] == ["model-b"]
    assert store.last["OPENAI_BASE_URL"] == b.url and store.last["OPENAI_MODEL"] == "model-b"
    assert "key-of-a" not in json.dumps(store.last), "a snapshot never holds a key"


def test_a_request_in_flight_finishes_on_the_server_it_was_sent_to(two_servers):
    """A request A is still holding completes on A after the run is pinned to B; the next one goes to B."""
    a, b, store = two_servers
    a.hold_first = True
    results: list = []

    def first():
        with model_pin.as_the_run(RUN):
            results.append(client.invoke("slow").content)

    with model_pin.as_the_run(RUN):
        client = _chat()
    thread = threading.Thread(target=first)
    thread.start()
    for _ in range(200):
        if a.seen:
            break
        threading.Event().wait(0.02)
    assert a.seen, "the first request should have reached A and be held there"
    store.pinned, store.last = True, store.b_snapshot
    with model_pin.as_the_run(RUN):
        assert client.invoke("fast").content == "from model-b"
    a.release.set()
    thread.join(10)
    assert results == ["from model-a"]
    assert len(a.seen) == 1 and len(b.seen) == 1


def test_streaming_requests_are_rerouted_like_any_other(two_servers):
    """A streamed request carries the same JSON body, so it is pointed at B with B's name and no key."""
    a, b, store = two_servers
    store.pinned, store.last = True, store.b_snapshot
    with model_pin.as_the_run(RUN):
        text = "".join(chunk.content for chunk in _chat().stream("hi"))
    assert text == "from model-b"
    assert b.seen[0]["stream"] is True and b.seen[0]["model"] == "model-b" and b.seen[0]["authorization"] is None
    assert a.seen == []


def test_the_async_client_is_rerouted_too(two_servers):
    """`ainvoke` goes through the async transport and ends on B, with B's name and no key."""
    a, b, store = two_servers
    store.pinned, store.last = True, store.b_snapshot

    async def go():
        with model_pin.as_the_run(RUN):
            return (await _chat().ainvoke("hi")).content

    assert asyncio.run(go()) == "from model-b"
    assert b.seen[0]["model"] == "model-b" and b.seen[0]["authorization"] is None and a.seen == []


def test_the_host_header_is_the_destination_s_own_name(two_servers, monkeypatch):
    """The Host a server is named by comes from `reached_from_here` for the destination, not the old server."""
    from app.models import endpoints

    a, b, store = two_servers
    real = endpoints.reached_from_here
    monkeypatch.setattr(endpoints, "reached_from_here",
                        lambda url: (real(url)[0], {"Host": "named.example:1234"} if url == b.url else {}))
    with model_pin.as_the_run(RUN):
        client = _chat()
        store.pinned, store.last = True, store.b_snapshot
        client.invoke("hi")
    assert b.seen[0]["host"] == "named.example:1234"


def test_a_run_outside_any_run_context_is_never_rerouted(two_servers):
    """The API process has no run: it sees the settings, and a pin of some run never touches its requests."""
    a, b, store = two_servers
    store.pinned, store.last = True, store.b_snapshot
    assert _chat().invoke("hi").content == "from model-a"
    assert b.seen == []


def test_a_pin_that_cannot_be_read_leaves_the_request_where_it_was_built(two_servers, monkeypatch):
    """A failed read of the run's pin falls back to the settings (here: unchanged), never to a guess."""
    a, b, store = two_servers
    monkeypatch.setattr(model_pin, "_store", lambda: (_ for _ in ()).throw(RuntimeError("database away")))
    with model_pin.as_the_run(RUN):
        assert _chat().invoke("hi").content == "from model-a"
    assert b.seen == []


def test_a_destination_of_another_kind_is_not_rewritten(two_servers, monkeypatch):
    """A hosted API is never the target of a client built for a self-hosted server: the request stays where it was."""
    a, b, store = two_servers
    store.pinned = True
    store.last = {"LLM_PROVIDER": "local", "OPENAI_BASE_URL": "https://api.example.com/v1", "OPENAI_MODEL": "hosted"}
    with model_pin.as_the_run(RUN):
        client = _chat()
    # built for the pinned hosted address; now the settings-built client for A is asked under that pin
    assert client is not None
    store.pinned = False
    with model_pin.as_the_run(RUN):
        a_client = _chat()
        store.pinned, store.last = True, dict(store.last)
        assert a_client.invoke("hi").content == "from model-a"
    assert b.seen == []


def test_the_transport_returns_the_identical_request_when_nothing_differs():
    """With no run, the request object handed to the inner transport is the one the client made."""
    sent: list[httpx.Request] = []

    class Recorder(httpx.BaseTransport):
        def handle_request(self, request):
            sent.append(request)
            return httpx.Response(200, json={})

    rerouter = model_pin._Rerouter("http://127.0.0.1:1/v1", "m")
    client = httpx.Client(transport=model_pin.PinTransport(rerouter, Recorder()))
    client.post("http://127.0.0.1:1/v1/chat/completions", json={"model": "m"}, headers={"Authorization": "Bearer k"})
    assert sent[0].headers["authorization"] == "Bearer k"
    assert json.loads(sent[0].content) == {"model": "m"}
