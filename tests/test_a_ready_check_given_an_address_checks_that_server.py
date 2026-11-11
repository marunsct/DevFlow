"""`loop.sh ready http://host:port/v1` checks the server at that address, not the default one.

Measured on one day: the ready check read only `pin_url=` arguments, so every gated start and resume on the second
port, written with a bare address, checked the default port instead; the second port's server was never asked.
"""
from __future__ import annotations

import ast
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "model_ready.py").read_text()


def _the_pin_asked_for(captured: list):
    tree = ast.parse(SOURCE)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "the_pin_asked_for")
    scope: dict = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "model_ready", "exec"), scope)

    import app.models.model_pin as model_pin
    import app.server.runtime_settings as runtime_settings

    def snapshot_for(base, url, model):
        captured.append((url, model))
        return {"url": url, "model": model}

    original = (model_pin.snapshot_for, runtime_settings.global_model_snapshot)
    model_pin.snapshot_for, runtime_settings.global_model_snapshot = snapshot_for, lambda: {}
    return scope["the_pin_asked_for"], original


def test_a_bare_address_is_the_server_checked():
    import app.models.model_pin as model_pin
    import app.server.runtime_settings as runtime_settings

    captured: list = []
    the_pin_asked_for, original = _the_pin_asked_for(captured)
    try:
        assert the_pin_asked_for(["http://host.docker.internal:8888/v1"]) is not None
        assert captured[-1] == ("http://host.docker.internal:8888/v1", None)
        the_pin_asked_for(["http://a:1/v1", "pin_url=http://b:2/v1"])
        assert captured[-1][0] == "http://b:2/v1"  # a named pin_url wins
        assert the_pin_asked_for(["deep"]) is None  # no address: the default server, as before
    finally:
        model_pin.snapshot_for, runtime_settings.global_model_snapshot = original
