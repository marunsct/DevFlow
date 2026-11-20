"""The browser pack's own server listens on the HOST it is given (plan WS.4).

A preview started the page's server with HOST=0.0.0.0, and it listened on 127.0.0.1 anyway: the address was written
into the pack's serve script, while every service pack's server takes HOST. The script is run for real with Node.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.request

import pytest

from app.stacks.packs import browser_javascript

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="Node is not installed on this machine")


def _a_free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("", 0))
        return probe.getsockname()[1]


def test_the_page_s_server_listens_on_the_host_it_is_given(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "serve.mjs").write_text(browser_javascript.PACK.files["scripts/serve.mjs"])
    (tmp_path / "index.html").write_text("<p>the page</p>")
    port = _a_free_port()

    # 127.0.0.2 is a loopback address a server bound to 127.0.0.1 does not answer.
    server = subprocess.Popen(["node", "scripts/serve.mjs"], cwd=tmp_path, stdout=subprocess.PIPE, text=True,
                              env={"PATH": os.environ["PATH"], "PORT": str(port), "HOST": "127.0.0.2"})
    try:
        said = server.stdout.readline()
        body = None
        deadline = time.monotonic() + 10
        while body is None and time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.2:{port}/", timeout=1) as answered:
                    body = answered.read().decode()
            except OSError:
                time.sleep(0.1)
    finally:
        server.kill()
        server.wait(timeout=10)

    assert body == "<p>the page</p>"
    assert f"http://127.0.0.2:{port}/" in said
