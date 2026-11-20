"""Before a run, each outside lookup source is asked live and says whether it answers - a warning, never a block (WL.7).

Measured 2026-11-20: the private search's general engines had refused every query for weeks and nothing noticed - the
container's health check tests only that it is up. A source that cannot answer is now named before every run; the
`ready` verdict, which gated starts read from its last line, stays the model's alone.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("lookup_ready", ROOT / "scripts" / "loop" / "lookup_ready.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_source_that_answers_and_one_that_does_not_are_both_named():
    probe = _module()

    assert probe._ask("github issues", lambda: 3).startswith("LOOKUPS github issues: answers (3 result(s)")  # noqa: SLF001
    silent = probe._ask("private search", lambda: 0)  # noqa: SLF001
    broken = probe._ask("stack exchange", lambda: (_ for _ in ()).throw(TimeoutError("read timed out")))  # noqa: SLF001
    assert "NO ANSWER" in silent and "not a block" in silent
    assert "NO ANSWER (TimeoutError" in broken


def test_ready_prints_the_sources_above_the_model_s_verdict_and_keeps_its_status():
    script = (ROOT / "scripts" / "loop" / "loop.sh").read_text(encoding="utf-8")
    ready = script[script.index("\nready)"):script.index(";;", script.index("\nready)"))]

    assert "lookup_ready.py" in ready, "ready asks the lookup sources"
    assert re.search(r"tail -1", ready), "the verdict is printed last, alone"
    assert re.search(r"exit \"?\$status\"?", ready), "ready keeps the model check's exit status"
