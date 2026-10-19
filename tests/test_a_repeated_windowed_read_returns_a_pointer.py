"""A repeated read of the same window of an unchanged file returns a pointer (Initiative AQ step 3).

431 identical `read_file` calls on a medium run came after every other guard,
and a window read again was answered with its bytes until the third or fourth
time. The lines are in the conversation already, so the second asking says where.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from app.agents import stage_memory
from app.agents.workspace_backend import READ_WITHHELD_MARKER, WorkspaceBackend

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def backend(monkeypatch):
    stage_memory.forget_everything()
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: ("t-1", "specialist_backend_0"))
    root = tempfile.mkdtemp()
    (Path(root) / "app.py").write_text("".join(f"line {n}\n" for n in range(1, 301)), encoding="utf-8")
    made = WorkspaceBackend(root_dir=root, virtual_mode=True)
    made.root_for_the_test = root
    yield made
    stage_memory.forget_everything()


def _content(result) -> str:
    data = getattr(result, "file_data", None) or {}
    return (data.get("content") or "") + (getattr(result, "error", None) or "")


def test_the_second_read_of_a_window_is_a_pointer_without_the_bytes(backend):
    first = _content(backend.read("/app.py", offset=100, limit=50))
    second = _content(backend.read("/app.py", offset=100, limit=50))

    assert "line 125" in first
    assert READ_WITHHELD_MARKER in second and "in your context above" in second
    assert "lines 101-150 of 300" in second
    assert "line 125\n" not in second
    assert not BANNED.search(second.split("]")[0])


def test_a_window_of_a_changed_file_is_read_again(backend):
    backend.read("/app.py", offset=100, limit=50)
    Path(backend.root_for_the_test, "app.py").write_text(
        "".join(f"new {n}\n" for n in range(1, 301)), encoding="utf-8"
    )

    again = _content(backend.read("/app.py", offset=100, limit=50))

    assert "new 125" in again


def test_a_whole_file_read_twice_is_still_returned(backend):
    Path(backend.root_for_the_test, "small.py").write_text("one\ntwo\n", encoding="utf-8")
    backend.read("/small.py")

    assert "two" in _content(backend.read("/small.py"))
