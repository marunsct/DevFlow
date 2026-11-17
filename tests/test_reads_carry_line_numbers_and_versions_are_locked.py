"""The model sees line numbers, and what is tested is what runs.

On 2026-09-30 production ran deepagents 0.7.20 while this suite ran 0.7.13,
because the image resolved `pyproject.toml`'s ranges and ignored `uv.lock`
(38 packages differed). 0.7.20 replaced `read_file`'s per-line number gutter
with one `@@ lines A-B of T @@` header, so every `replace_lines` a model made
was counted by hand from unnumbered text - the largest class of failed edits
that day - and nothing here could see it.
"""
from __future__ import annotations

import importlib.metadata
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: The packages whose behaviour the agents' tools and prompts are written
#: against. A difference in any of them is a difference in what the model sees.
AGENT_STACK = ("deepagents", "langchain", "langchain-core", "langchain-openai", "langgraph", "openai")


def _locked_versions() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {package["name"]: package["version"] for package in lock.get("package", [])}


@pytest.mark.parametrize("name", AGENT_STACK)
def test_the_suite_runs_the_locked_version(name: str) -> None:
    assert importlib.metadata.version(name) == _locked_versions()[name], (
        f"{name} installed here differs from uv.lock - run `uv sync`; the image installs the lock"
    )


def test_both_images_install_the_lock() -> None:
    for dockerfile in ("Dockerfile", "Dockerfile.test"):
        text = (ROOT / dockerfile).read_text(encoding="utf-8")
        assert "uv export --frozen" in text and "uv.lock" in text, dockerfile
        for line in re.findall(r"uv pip install[^\n]*", text):
            if re.search(r'"?\.(\[test\])?"?\s*\\?$', line):
                assert "--no-deps" in line, f"{dockerfile} resolves the project's dependencies: {line}"


def test_read_file_numbers_every_line(tmp_path, monkeypatch) -> None:
    """`replace_lines` addresses lines by number; the reads that feed it must show them."""
    from langchain_core.messages import AIMessage, ToolMessage

    from workflow_nodes import a_role_agent, an_answer

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "app.js").write_text("alpha\nbeta\n")
    read = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "/app.js", "offset": 0, "limit": 2}, "id": "r",
                                              "type": "tool_call"}])

    result, _ = a_role_agent(tmp_path, read, an_answer())

    [shown] = [m.content for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "read_file"]
    assert re.search(r"\b1\b.*alpha", shown) and re.search(r"\b2\b.*beta", shown), shown
