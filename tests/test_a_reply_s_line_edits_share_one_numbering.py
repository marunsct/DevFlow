"""Several `replace_lines` calls to one file from one reply all mean the same read.

One run's `specialist_ui_ux_1` read `style.css` and sent seven single-line
edits in one reply, the first adding a whole section. The tool node applied
them one after another, each to a file the earlier ones had already moved, and
all seven reported "edited": the file ended up with a rule on the wrong
selector and a stray `}`, and six more calls went on putting it right.
"""

from __future__ import annotations

import itertools
import json
import uuid
from pathlib import Path

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage

from app.agents.line_batches import build_line_batch_middleware
from app.tools.repository import RepositoryToolError, replace_approved_lines

ORIGINAL = "".join(f"line{n}\n" for n in range(1, 11))

EDITS = [
    {"start_line": 2, "end_line": 2, "content": "TWO-a\nTWO-b\nTWO-c"},
    {"start_line": 5, "end_line": 6, "content": "FIVE-SIX"},
    {"start_line": 9, "end_line": 9, "content": "NINE"},
]

EXPECTED = (
    "line1\nTWO-a\nTWO-b\nTWO-c\nline3\nline4\nFIVE-SIX\nline7\nline8\nNINE\nline10\n"
)


def _reply(edits: list[dict], path: str = "app/style.css") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "replace_lines", "id": uuid.uuid4().hex, "args": {"relative_path": path, **edit}}
            for edit in edits
        ],
    )


def _run(root: Path, reply: AIMessage, order: tuple[int, ...]) -> list[ToolMessage]:
    middleware = build_line_batch_middleware(str(root))

    def handler(request: ToolCallRequest) -> ToolMessage:
        call = request.tool_call
        try:
            out = replace_approved_lines(root, **call["args"])
        except RepositoryToolError as exc:
            out = {"error": str(exc)}
        return ToolMessage(content=json.dumps(out), tool_call_id=call["id"], name=call["name"])

    results = []
    for index in order:
        request = ToolCallRequest(
            tool_call=reply.tool_calls[index], tool=None, state={"messages": [reply]}, runtime=None
        )
        results.append(middleware.wrap_tool_call(request, handler))
    return results


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "style.css").write_text(ORIGINAL, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_every_order_gives_the_file_the_model_meant(root: Path, order: tuple[int, ...]) -> None:
    _run(root, _reply(EDITS), order)

    assert (root / "app" / "style.css").read_text(encoding="utf-8") == EXPECTED


def test_an_edit_overlapping_one_already_applied_is_refused(root: Path) -> None:
    edits = [EDITS[0], {"start_line": 2, "end_line": 3, "content": "clash"}]

    first, second = _run(root, _reply(edits), (0, 1))

    assert "error" not in json.loads(first.content)
    refusal = json.loads(second.content)["error"]
    assert "overlap lines 2-2, which another edit in the same reply has already replaced" in refusal


def test_a_lone_edit_is_left_alone(root: Path) -> None:
    _run(root, _reply([EDITS[1]]), (0,))

    assert "FIVE-SIX\nline7" in (root / "app" / "style.css").read_text(encoding="utf-8")


def test_edits_to_different_files_do_not_move_each_other(root: Path) -> None:
    (root / "app" / "other.css").write_text(ORIGINAL, encoding="utf-8")
    reply = AIMessage(
        content="",
        tool_calls=[
            {"name": "replace_lines", "id": uuid.uuid4().hex, "args": {"relative_path": "app/other.css", **EDITS[0]}},
            {"name": "replace_lines", "id": uuid.uuid4().hex, "args": {"relative_path": "app/style.css", **EDITS[2]}},
        ],
    )

    _run(root, reply, (0, 1))

    assert "line8\nNINE\nline10" in (root / "app" / "style.css").read_text(encoding="utf-8")


def test_every_role_agent_carries_it() -> None:
    import inspect

    from app.agents import role_agent

    assert "build_line_batch_middleware(resolved_repo_root)" in inspect.getsource(role_agent)
