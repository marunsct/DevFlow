"""A model server on the owner's machine is sent the Host its owner reaches it by.

The harness's container reaches a server on the owner's machine as
`host.docker.internal`. A server guarding against DNS rebinding answers only
to the names it was told it lives at: measured with one owner's server,
every request was 403 "Host 'host.docker.internal:9090' is not allowed",
while the same server answered `http://127.0.0.1:9090/`.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from app.models.endpoints import host_header_for


def test_the_host_s_own_name_is_sent_for_a_server_reached_from_a_container():
    assert host_header_for("http://host.docker.internal:9090/v1") == {"Host": "localhost:9090"}
    assert host_header_for("http://host.docker.internal/v1") == {"Host": "localhost"}
    assert host_header_for("http://localhost:1234/v1") == {}
    assert host_header_for("https://api.example.com/v1") == {}
    assert host_header_for(None) == {}


def test_the_model_client_and_the_readiness_check_send_it():
    from pathlib import Path

    from app.config import load_settings
    from app.models import build_default_chat_model

    model = build_default_chat_model(load_settings({
        "LLM_PROVIDER": "local", "OPENAI_BASE_URL": "http://host.docker.internal:9090/v1",
        "OPENAI_MODEL": "m", "OPENAI_API_KEY": "local-placeholder",
    }))
    assert (model.default_headers or {}).get("Host") == "localhost:9090"
    assert "host_header_for(base)" in Path("scripts/loop/model_ready.py").read_text()


class _OnlyLocalhost(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        allowed = self.headers.get("Host", "").startswith("localhost")
        self.send_response(200 if allowed else 403)
        self.end_headers()
        self.wfile.write(b'{"data": []}' if allowed else b'{"error": "Host is not allowed"}')

    def log_message(self, *args):
        pass


def test_a_server_that_answers_only_to_localhost_answers_the_header():
    server = HTTPServer(("127.0.0.1", 0), _OnlyLocalhost)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{port}/v1/models"
        assert httpx.get(url).status_code == 403, "the server refuses another name, as the owner's did"
        assert httpx.get(url, headers={"Host": f"localhost:{port}"}).status_code == 200
    finally:
        server.shutdown()
