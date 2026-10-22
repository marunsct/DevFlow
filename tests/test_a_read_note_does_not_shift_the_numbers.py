"""A note about a read never moves the line numbers the read shows.

`read_file` numbers every line of the text the backend returns, starting at
the first line asked for. The note about a repeated read was written into that
text, so it was numbered too, and every real line came out two numbers high:
one run's re-read of `lib/tasks.js` showed `export function deleteTask` as
line 105 when it was line 103, and each `replace_lines` sent at the numbers
shown was refused as "not what you expected". Over 25 runs, 50 `replace_lines`
calls were refused that way against 47 that succeeded.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

pytest.importorskip("deepagents")


def _tools(root):
    from deepagents.middleware.filesystem import FilesystemMiddleware

    from app.agents.workspace_backend import WorkspaceBackend
    from app.agents.workspace_paths import build_workspace_path_middleware

    filesystem = FilesystemMiddleware(backend=WorkspaceBackend(root_dir=str(root), virtual_mode=True, hold_notes=True))
    read_file = {tool.name: tool for tool in filesystem.tools}["read_file"]
    return read_file, build_workspace_path_middleware(str(root))


class _Request:
    def __init__(self, args: dict) -> None:
        self.tool_call = {"name": "read_file", "args": args, "id": "call-1"}

    def override(self, tool_call: dict) -> "_Request":
        return _Request(tool_call["args"])


def _read(read_file, paths, **args):
    def handler(request):
        return read_file.func(runtime=SimpleNamespace(tool_call_id="call-1"), **request.tool_call["args"])

    return paths.wrap_tool_call(_Request({"file_path": "/app/tasks.js", **args}), handler).content


def _numbered(content: str) -> dict[int, str]:
    rows = {}
    for row in content.splitlines():
        found = re.match(r"^\s*(\d+)\s{2}(.*)$", row)
        if found:
            rows[int(found.group(1))] = found.group(2)
    return rows


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "tasks.js").write_text("".join(f"line {n}\n" for n in range(1, 31)), encoding="utf-8")
    return tmp_path


def test_a_repeated_read_says_so_and_keeps_every_number(project) -> None:
    read_file, paths = _tools(project)

    _read(read_file, paths, offset=5, limit=10)
    # Lines inside the served ones, not the same window: that one is answered
    # with where its lines are, without them (Initiative AQ).
    again = _read(read_file, paths, offset=5, limit=8)

    assert again.startswith("["), again[:200]
    rows = _numbered(again)
    assert rows[6] == "line 6" and rows[13] == "line 13"
    assert all(text == f"line {number}" for number, text in rows.items())


def test_a_first_read_is_numbered_as_it_always_was(project) -> None:
    read_file, paths = _tools(project)

    rows = _numbered(_read(read_file, paths, offset=0, limit=30))

    assert rows == {n: f"line {n}" for n in range(1, 31)}


def test_a_held_note_is_taken_once() -> None:
    from app.agents import workspace_backend

    workspace_backend._HELD.note = "a note"

    assert workspace_backend.held_read_note() == "a note"
    assert workspace_backend.held_read_note() == ""


def test_read_directly_the_note_stays_in_the_text(project) -> None:
    """The backend's own contract is unchanged for a caller that does not number."""
    from app.agents.workspace_backend import WorkspaceBackend

    backend = WorkspaceBackend(root_dir=str(project), virtual_mode=True)
    backend.read("/app/tasks.js", offset=5, limit=10)
    again = backend.read("/app/tasks.js", offset=5, limit=10).file_data["content"]

    assert again.startswith("[")
