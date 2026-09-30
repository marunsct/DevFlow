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
import inspect
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


def test_read_file_numbers_every_line() -> None:
    """`replace_lines` addresses lines by number; the reads that feed it must show them."""
    from deepagents.backends.utils import format_content_with_line_numbers
    from deepagents.middleware import filesystem

    assert "format_content_with_line_numbers(" in inspect.getsource(filesystem), (
        "read_file no longer puts a line number on each line - line-addressed edits would be blind"
    )
    numbered = format_content_with_line_numbers("alpha\nbeta", start_line=7)
    assert re.search(r"\b7\b.*alpha", numbered) and re.search(r"\b8\b.*beta", numbered)
