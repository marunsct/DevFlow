"""Runs started together on a model not seen before diagnose it once; the others wait and use the result (LF.1568).

Measured: a new model's diagnosis makes dozens of calls before a run's first stage, and two runs started at the same
time each found no kept diagnosis and each ran all of it on the one server at once - twice the calls, each slower
for sharing the server, and the second result written over the first.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from app.models import diagnostics


class _Server:
    """The model server: answers every request with plain text, a little slowly, and counts what it was asked."""

    def __init__(self) -> None:
        self.asked = 0
        self._lock = threading.Lock()

    def create(self, **request):
        with self._lock:
            self.asked += 1
        time.sleep(0.005)
        return {"choices": [{"message": {"role": "assistant", "content": "ready"}, "finish_reason": "stop"}],
                "usage": {"completion_tokens": 7}}


def _model(server: _Server):
    return SimpleNamespace(model_name="a-model-not-seen-before", openai_api_base="http://model-server:9/v1",
                           root_client=SimpleNamespace(chat=SimpleNamespace(
                               completions=SimpleNamespace(create=server.create))))


def _one_run_alone(tmp_path, monkeypatch) -> int:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "alone"))
    server = _Server()
    diagnostics.diagnose_if_new(_model(server))
    return server.asked


def test_two_runs_started_together_ask_the_server_what_one_run_asks(tmp_path, monkeypatch):
    alone = _one_run_alone(tmp_path, monkeypatch)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "together"))
    server = _Server()
    start = threading.Barrier(2)
    found: list = []

    def run() -> None:
        start.wait()
        found.append(diagnostics.diagnose_if_new(_model(server)))

    runs = [threading.Thread(target=run) for _ in range(2)]
    for each in runs:
        each.start()
    for each in runs:
        each.join(timeout=60)

    assert alone > 10
    assert server.asked == alone
    assert len(found) == 2 and found[0] is not None and found[0].measured_at == found[1].measured_at
