"""Streaming works through the agent path on the libraries in use (Initiative T, the spike's result).

Streaming was switched off after a run died on its first call: langchain routed
a bound model through the non-streaming `_generate`, handed an `openai.Stream`.
The spike reproduces that path - `create_agent`, a tool call, the harness's own
model class - against a local fake server, and keeps it passing; turning
streaming on is a separate, measured change.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "streaming_spike.py"


def _spike():
    spec = importlib.util.spec_from_file_location("streaming_spike", SPIKE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_langchain_s_own_model_streams_through_the_agent_path():
    passed, said = _spike().spike(False)
    assert passed, said


def test_the_harness_s_model_streams_through_the_agent_path():
    passed, said = _spike().spike(True)
    assert passed, said
