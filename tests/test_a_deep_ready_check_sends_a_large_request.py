"""`loop.sh ready deep` also sends a request of about 13,000 tokens, which the plain check does not.

Measured after the owner reloaded a model: the small request answered while every real call returned HTTP 500/502
(a 245-token request worked, a 4,500-token one did not), so the check said ALL READY and two runs failed at their
first stage.
"""
from __future__ import annotations

import ast
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts" / "loop" / "model_ready.py").read_text()


def _answers():
    tree = ast.parse(SOURCE)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "answers")
    scope = {"json": json, "urllib": urllib}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "model_ready", "exec"), scope)
    return scope["answers"]


def test_a_large_request_is_what_the_deep_check_sends(monkeypatch):
    sent = []

    def refuse_a_large_one(request, timeout=None):
        body = json.loads(request.data)
        sent.append(len(body["messages"][0]["content"]))
        if sent[-1] > 10_000:
            raise urllib.error.HTTPError(request.full_url, 500, "Server Error", {}, io.BytesIO(b"{}"))
        return io.BytesIO(b'{"choices": [{}]}')

    class _Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout=None: (refuse_a_large_one(request, timeout) and _Reply(b'{"choices": [{}]}')))
    answers = _answers()
    assert answers("http://server/v1", {}, "", "m") == ""
    assert answers("http://server/v1", {}, "", "m", words=12000).startswith("HTTP 500")
    assert sent[0] < 100 and sent[1] > 60_000


def test_the_deep_check_is_opt_in_and_reached_from_the_loop_script():
    assert 'DEEP = "deep" in sys.argv[1:]' in SOURCE
    assert 'ready)  shift; in_worker model_ready.py "$@" ;;' in (ROOT / "scripts" / "loop" / "loop.sh").read_text()
