"""`use_runtime` reaches the tool through LangGraph's tool node (measured live).

Its parameter was named `runtime`, which LangGraph's tool node reserves for the
runtime it injects, so every call failed with an empty error before the tool
ran - 4 of 4 in one fix stage.
"""
from __future__ import annotations

from langgraph.prebuilt.tool_node import _get_all_injected_args

from app.tools import runtimes


def test_no_parameter_is_taken_for_an_injected_one():
    injected = _get_all_injected_args(runtimes.build_runtime_tool("/tmp"))
    assert injected.runtime is None and not injected.state and injected.store is None


def test_the_tool_takes_the_language_and_version(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(runtimes, "use", lambda root, language, version: seen.update(language=language, version=version) or {"ok": True})

    runtimes.build_runtime_tool(str(tmp_path)).invoke({"language": "node", "version": "22"})

    assert seen == {"language": "node", "version": "22"}
