"""A repeated read of part of a file is not told it read the whole file.

One run's `architecture_review` read lines 1-120 of a 423-line specification a
fifth time and was told "Asking for a different range of it will not help -
this is the whole file." Three hundred lines it had not re-read were right
there, and the one sentence meant to end the loop pointed away from them.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.agents import stage_memory
from app.agents.workspace_backend import REPEATS_BEFORE_SAYING_SO, WorkspaceBackend


@pytest.fixture
def backend(monkeypatch):
    stage_memory.forget_everything()
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: ("t-1", "architecture_review"))
    root = tempfile.mkdtemp()
    (Path(root) / "spec.md").write_text(
        "".join(f"line {n}\n" for n in range(1, 424)), encoding="utf-8"
    )
    (Path(root) / "small.md").write_text("one\ntwo\n", encoding="utf-8")
    yield WorkspaceBackend(root_dir=root, virtual_mode=True)
    stage_memory.forget_everything()


def _the_notice(backend, path, **window):
    """The text of the read that first carries the repeated-bytes notice."""
    for _ in range(REPEATS_BEFORE_SAYING_SO + 1):
        result = backend.read(path, **window)
    data = getattr(result, "file_data", None) or {}
    return (data.get("content") or "") + (getattr(result, "error", None) or "")


def test_a_window_of_a_longer_file_is_named_as_a_window(backend):
    text = _the_notice(backend, "/spec.md", offset=0, limit=120)

    # A window read again is answered with where its lines are (Initiative AQ).
    assert "has given you these same bytes" in text
    assert "this is the whole file" not in text
    assert "lines 1-120 of 423" in text


def test_a_read_of_the_whole_file_still_says_so(backend):
    text = _the_notice(backend, "/small.md")

    assert "same bytes this file gave you" in text
    assert "this is the whole file" in text
