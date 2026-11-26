"""LF.1575: `loop.sh effects` pipes the repository's script into the worker, which holds the deployed code. A merged but
undeployed item's module raised `ModuleNotFoundError` and the whole report was lost (measured twice in one day)."""
from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"


def _report(monkeypatch, module: str, stand_in) -> str:
    # `None` in `sys.modules` is how Python marks a module that cannot be imported: the worker without it.
    monkeypatch.setitem(sys.modules, module, stand_in)
    effects = runpy.run_path(str(SCRIPT))["effects"]
    return "\n".join(effects([{"kind": "defect", "event": "left open", "detail": ""}], ""))


def test_an_item_the_deployed_code_lacks_is_named_and_the_rest_still_prints(monkeypatch):
    lines = _report(monkeypatch, "app.agents.read_windows", None)
    assert "LF.1570: not in the deployed code" in lines
    # Items before and after it are still reported.
    assert "defects: left open 1" in lines
    assert "LF.1543 batch reverts by cause" in lines and "LF.1547 rewrites after a revert" in lines


def test_an_item_that_fails_is_named_with_its_error_and_the_rest_still_prints(monkeypatch):
    def broken(records):
        raise KeyError("stage")

    lines = _report(monkeypatch, "app.agents.read_windows", types.SimpleNamespace(effects_lines=broken))
    assert "LF.1570: its lines failed (KeyError" in lines
    assert "LF.1547 rewrites after a revert" in lines
