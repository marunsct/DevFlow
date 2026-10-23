"""A model the server lists but does not answer for is not ready.

The readiness check asked only whether the model was listed. A server that
lists every model it has on disk answered each request "No model loaded": the
check said ALL READY, a run started and failed at its first stage, and the new
model's automatic diagnosis kept the refusals as the model's own.
"""
from __future__ import annotations

import ast
import io
import json
import urllib.error
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "model_ready.py").read_text()


def _answers():
    tree = ast.parse(SOURCE)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "answers")
    scope = {"json": json, "urllib": urllib}
    import urllib.request  # noqa: F401 - the function uses it

    exec(compile(ast.Module(body=[function], type_ignores=[]), "model_ready", "exec"), scope)
    return scope["answers"]


def test_a_server_with_no_model_loaded_says_why(monkeypatch):
    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {},
                                     io.BytesIO(b'{"error": {"message": "No model loaded."}}'))

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert _answers()("http://server/v1", {}, "", "m") == "HTTP 400 No model loaded."


def test_a_model_that_answers_is_ready(monkeypatch):
    class _Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout=None: _Reply(b'{"choices": [{"message": {"content": "ready"}}]}'))
    assert _answers()("http://server/v1", {}, "", "m") == ""
