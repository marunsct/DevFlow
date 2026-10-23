"""`loop.sh ready` said "reply salvage unmeasured" of a model the diagnosis had just measured.

It described the model by its configured name; the measurements are kept under
the file name the server reports. It now names the model the way the worker does.
"""
from __future__ import annotations

from pathlib import Path

READY = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "model_ready.py"


def test_the_model_line_names_the_model_as_the_worker_does():
    source = READY.read_text(encoding="utf-8")
    line = next(l for l in source.splitlines() if "describe(" in l and "MODEL" in l)
    assert "served_as(" in line
    assert source.index("server_profile.record()") < source.index(line)
