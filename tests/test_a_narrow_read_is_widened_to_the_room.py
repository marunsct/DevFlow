"""A narrow range read is widened toward the read tool's 400-line default while the request has room (LF.1570).

Measured on a medium run: one sprint's code review, on its second visit, made 62 reads, 55 of them distinct, almost all
50-60-line windows such as `read_file(routes.py, offset 50, limit 60)`, at about 40k tokens of conversation a call -
some 3M input tokens for one review. The file is the 939-line `routes.py` that review read, captured from its workspace.
Behind `READ_WINDOWS_SIZED_TO_THE_ROOM`: the window keeps its start and is widened up to the default, the file's end and
half the room left, never into lines the conversation still holds; one line ahead of the text says so.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from deepagents.backends.utils import format_content_with_line_numbers
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents import stage_memory
from app.agents.room_for_reads import build_room_for_reads_middleware
from app.agents.workspace_backend import WorkspaceBackend

CAPTURED = Path(__file__).parent / "captured"
ROUTES = (CAPTURED / "sources" / "routes-939-lines-fastapi.py.txt").read_text(encoding="utf-8")
LINES = ROUTES.splitlines()
PATH = "/task-management-dashboard/task_management_dashboard/routes.py"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The input ceiling every test runs under, in tokens; at three characters a token.
CEILING = 100_000


class _ModelCall:
    model = None

    def __init__(self, messages: list | None = None) -> None:
        self.messages = messages or [HumanMessage(content="Review the sprint's changes.")]


class _ToolCall:
    def __init__(self, args: dict, call_id: str) -> None:
        self.tool_call = {"name": "read_file", "args": args, "id": call_id}


def _a_reply_reported(middleware, input_tokens: int, messages: list | None = None) -> None:
    reply = AIMessage(content="", usage_metadata={"input_tokens": input_tokens, "output_tokens": 120,
                                                  "total_tokens": input_tokens + 120})
    middleware.wrap_model_call(_ModelCall(messages), lambda request: reply)


def _read(middleware, backend: WorkspaceBackend, call_id: str = "r1", **args) -> ToolMessage:
    """`read_file` as the stage calls it: the model's arguments, a 400-line window filled in where it named none, the
    text numbered from the line the backend says it starts at."""

    def tool(request):
        given = request.tool_call["args"]
        offset = given.get("offset", 0)
        result = backend.read(given["file_path"], offset=offset, limit=given.get("limit", 400))
        start = getattr(result, "start_line", None) or offset + 1
        return ToolMessage(content=format_content_with_line_numbers(result.file_data["content"], start_line=start),
                           tool_call_id=call_id, name="read_file")

    return middleware.wrap_tool_call(_ToolCall({"file_path": PATH, **args}, call_id), tool)


def _numbered(content: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?m)^ *(\d+)  ", content)]


@pytest.fixture
def stage(tmp_path, monkeypatch):
    monkeypatch.setenv("READ_WINDOWS_SIZED_TO_THE_ROOM", "on")
    monkeypatch.setenv("READS_SIZED_TO_THE_ROOM", "off")
    monkeypatch.setenv("CTX_MAX_TOKENS", str(CEILING))
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    target = tmp_path / PATH.lstrip("/")
    target.parent.mkdir(parents=True)
    target.write_text(ROUTES, encoding="utf-8")
    stage_memory.forget_everything()
    with stage_memory.remembering(f"stage-windows-{tmp_path.name}"):
        yield build_room_for_reads_middleware(), WorkspaceBackend(str(tmp_path), virtual_mode=True, hold_notes=True)
    stage_memory.forget_everything()


def test_a_sixty_line_window_with_room_is_widened_to_the_default_from_its_start(stage):
    middleware, backend = stage
    _a_reply_reported(middleware, 40_000)  # 180,000 characters left

    given = _read(middleware, backend, offset=50, limit=60).content

    assert _numbered(given) == list(range(51, 451))
    assert LINES[449] in given
    first = given.splitlines()[0]
    assert "widened" in first and "51-450" in first and "939" in first and "51-110" in first


def test_a_window_near_the_end_is_widened_only_to_the_file_s_end(stage):
    middleware, backend = stage
    _a_reply_reported(middleware, 40_000)

    given = _read(middleware, backend, offset=900, limit=20).content

    assert _numbered(given) == list(range(901, 940))
    assert "901-939" in given.splitlines()[0]


def test_a_window_is_never_widened_past_half_the_room_left(stage):
    middleware, backend = stage
    _a_reply_reported(middleware, CEILING - 4_000)  # 12,000 characters left: 6,000 for this read

    given = _read(middleware, backend, offset=50, limit=60).content

    numbers = _numbered(given)
    text = given.split("\n", 1)[1]
    assert numbers[0] == 51 and 110 < numbers[-1] < 450
    assert len(text) <= 6_000


def test_a_window_is_not_widened_into_lines_the_conversation_still_holds(stage):
    middleware, backend = stage
    earlier = format_content_with_line_numbers("\n".join(LINES[150:250]), start_line=151)
    conversation = [
        HumanMessage(content="Review the sprint's changes."),
        AIMessage(content="", tool_calls=[{"name": "read_file", "id": "r0",
                                           "args": {"file_path": PATH, "offset": 150, "limit": 100}}]),
        ToolMessage(content=earlier, tool_call_id="r0", name="read_file"),
    ]
    _a_reply_reported(middleware, 40_000, conversation)

    given = _read(middleware, backend, offset=50, limit=60).content

    assert _numbered(given) == list(range(51, 151))


def test_the_lines_a_widened_window_gave_are_held_for_the_next_reads(stage):
    """The model's arguments named 51-110; the conversation holds 51-450, so a read of 301-360 adds nothing to it."""
    middleware, backend = stage
    _a_reply_reported(middleware, 40_000)
    widened = _read(middleware, backend, call_id="r1", offset=50, limit=60)
    conversation = [
        HumanMessage(content="Review the sprint's changes."),
        AIMessage(content="", tool_calls=[{"name": "read_file", "id": "r1",
                                           "args": {"file_path": PATH, "offset": 50, "limit": 60}}]),
        widened,
    ]
    _a_reply_reported(middleware, 45_000, conversation)

    given = _read(middleware, backend, call_id="r2", offset=300, limit=60).content

    assert _numbered(given) == list(range(301, 361))
    assert "widened" not in given


def test_a_second_window_of_the_same_reply_is_not_widened_into_the_first(stage):
    middleware, backend = stage
    _a_reply_reported(middleware, 40_000)
    _read(middleware, backend, call_id="r1", offset=50, limit=60)

    given = _read(middleware, backend, call_id="r2", offset=100, limit=60).content

    assert _numbered(given) == list(range(101, 161))


@pytest.mark.parametrize("window", [{"offset": 50, "limit": 400}, {"offset": 50}, {}])
def test_a_read_of_the_default_window_or_more_is_as_asked(stage, window):
    middleware, backend = stage
    _a_reply_reported(middleware, 40_000)

    given = _read(middleware, backend, **window).content

    assert "widened" not in given
    assert len(_numbered(given)) == 400


def test_with_the_switch_off_a_narrow_window_is_as_asked(stage, monkeypatch):
    middleware, backend = stage
    monkeypatch.setenv("READ_WINDOWS_SIZED_TO_THE_ROOM", "off")
    _a_reply_reported(middleware, 40_000)

    given = _read(middleware, backend, offset=50, limit=60).content

    assert _numbered(given) == list(range(51, 111))


def test_before_any_reply_the_room_is_not_known_and_a_window_is_as_asked(stage):
    middleware, backend = stage

    given = _read(middleware, backend, offset=50, limit=60).content

    assert _numbered(given) == list(range(51, 111))


def test_the_widened_line_uses_no_banned_word(stage):
    middleware, backend = stage
    _a_reply_reported(middleware, 40_000)

    first = _read(middleware, backend, offset=50, limit=60).content.splitlines()[0]

    assert "widened" in first and not BANNED.search(first)


def test_the_effects_report_counts_widened_reads_and_each_visit_s_reads_and_input_tokens(stage):
    """The captured records are one acceptance review's and one fixer's visits of that run, in narrow windows."""
    from app.agents.read_windows import effects_lines

    middleware, backend = stage
    _a_reply_reported(middleware, 40_000)
    widened = _read(middleware, backend, offset=50, limit=60)
    records = json.loads((CAPTURED / "review-and-fixer-reads-in-narrow-windows.json").read_text(encoding="utf-8"))
    records.append({"stage": "acceptance_review_2", "kind": "tool_result", "tool": "read_file",
                    "content": widened.content})

    (line,) = effects_lines(records)

    assert line.split()[0] == "1" and "LF.1570" in line
    assert "reviews: 1 visits, median 43 reads and 1,234,011 input tokens" in line
    assert "fixers: 1 visits, median 8 reads and 598,154 input tokens" in line
