"""The code graph answers inside the search and read tools the model already calls (plan KG.6).

Measured: the `code_graph` tool was called 0 times in about 3,500 offers; stages searched and read instead, and
searched again to learn where a name is defined and who calls it. With `GRAPH_IN_SEARCH_ANSWERS` on, a search for a
name the project defines says first where it is defined and which files use it, a range read that opens on a
definition says what calls it, and a whole read answered by an outline says what uses each definition.

The project is a real Go product's files (`tests/captured/projects/go-notes-api`); the lines were read from them.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("deepagents")

from deepagents.backends.utils import format_content_with_line_numbers  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

PROJECTS = Path(__file__).parent / "captured" / "projects"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    monkeypatch.setenv("GRAPH_IN_SEARCH_ANSWERS", "on")
    shutil.copytree(PROJECTS / "go-notes-api", tmp_path / "go-notes-api")
    (tmp_path / ".project-directory").write_text("go-notes-api")
    return tmp_path


class _Request:
    def __init__(self, name: str, args: dict) -> None:
        self.tool_call = {"name": name, "args": args, "id": "call-1"}

    def override(self, tool_call: dict) -> "_Request":
        return _Request(tool_call["name"], tool_call["args"])


def _called(root: Path, name: str, **args) -> str:
    """`name` called as a stage calls it: the path middleware around the real filesystem tool."""
    from deepagents.middleware.filesystem import FilesystemMiddleware

    from app.agents.workspace_backend import WorkspaceBackend
    from app.agents.workspace_paths import build_workspace_path_middleware

    tools = {tool.name: tool for tool in FilesystemMiddleware(
        backend=WorkspaceBackend(root_dir=str(root), virtual_mode=True, hold_notes=True)).tools}

    def handler(request):
        content = tools[name].func(runtime=SimpleNamespace(tool_call_id="call-1"), **request.tool_call["args"])
        return content if isinstance(content, ToolMessage) else ToolMessage(content=str(content), tool_call_id="call-1")

    return build_workspace_path_middleware(str(root)).wrap_tool_call(_Request(name, args), handler).content


def test_a_search_for_a_name_the_project_defines_says_where_and_who_uses_it_first(workspace):
    answer = _called(workspace, "grep", pattern="NewStore", path="/")
    first, _, rest = answer.partition("\n")
    assert "`NewStore` is defined in `go-notes-api/store/store.go` lines 38-45" in first
    assert "used in `go-notes-api/main.go`" in first
    assert "main.go" in rest  # the matches still follow


def test_a_search_for_text_that_is_no_name_is_as_before(workspace):
    answer = _called(workspace, "grep", pattern="title is required", path="/")
    assert "The harness's code graph:" not in answer


def test_a_range_read_of_a_definition_says_what_calls_it(workspace):
    answer = _called(workspace, "read_file", file_path="/go-notes-api/store/store.go", offset=129, limit=21)
    assert ("`Store.Create` (lines 130-149) is called by `createHandler` in `go-notes-api/server.go`"
            in answer.splitlines()[0])


def test_a_read_with_no_range_is_as_before(workspace):
    answer = _called(workspace, "read_file", file_path="/go-notes-api/store/store.go")
    assert "The harness's code graph:" not in answer


def test_with_the_switch_off_a_search_is_as_before(workspace, monkeypatch):
    monkeypatch.setenv("GRAPH_IN_SEARCH_ANSWERS", "off")
    assert "The harness's code graph:" not in _called(workspace, "grep", pattern="NewStore", path="/")


def test_an_outline_in_place_of_a_whole_read_says_what_uses_each_definition(workspace, monkeypatch):
    from app.agents import stage_memory
    from app.agents.room_for_reads import build_room_for_reads_middleware
    from app.agents.workspace_backend import WorkspaceBackend

    monkeypatch.setenv("READS_SIZED_TO_THE_ROOM", "on")
    monkeypatch.setenv("CTX_MAX_TOKENS", "50000")
    backend = WorkspaceBackend(str(workspace), virtual_mode=True)
    stage_memory.forget_everything()
    with stage_memory.remembering(f"stage-graph-{workspace.name}"):
        middleware = build_room_for_reads_middleware()
        reply = AIMessage(content="", usage_metadata={"input_tokens": 49_500, "output_tokens": 1, "total_tokens": 1})
        middleware.wrap_model_call(SimpleNamespace(model=None), lambda request: reply)

        def tool(request):
            result = backend.read(request.tool_call["args"]["file_path"], offset=0, limit=400)
            return ToolMessage(content=format_content_with_line_numbers(result.file_data["content"]),
                               tool_call_id="r1")

        answer = middleware.wrap_tool_call(_Request("read_file", {"file_path": "/go-notes-api/store/store.go"}),
                                           tool).content
    stage_memory.forget_everything()
    assert "outline" in answer
    assert re.search(r"^\s*130-149\s+`Store\.Create`: `createHandler` in `go-notes-api/server.go`$", answer, re.M)
    assert re.search(r"^\s*38-45\s+`NewStore`: `main` in `go-notes-api/main.go`$", answer, re.M)


def test_what_the_graph_adds_uses_no_product_word(workspace):
    said = "\n".join([
        _called(workspace, "grep", pattern="NewStore", path="/").splitlines()[0],
        _called(workspace, "read_file", file_path="/go-notes-api/store/store.go", offset=129, limit=21).splitlines()[0],
    ])
    assert "The harness's code graph:" in said and not BANNED.search(said)
