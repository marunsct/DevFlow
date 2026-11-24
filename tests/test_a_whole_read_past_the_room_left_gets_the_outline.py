"""A whole-file read the request has no room left for is answered with the file's outline (LF.1289).

Measured on a medium run: a technical lead's request held 51,000-64,000 tokens before its first read against a
59,776-token room, it read about eight whole files a reply, and 23% of the run's model calls were past the room - so
the files it read were summarised away within a call or two and read again. Behind `READS_SIZED_TO_THE_ROOM`: a read
naming no range, whose numbered text is larger than the room left (the last reply's reported input tokens against the
input ceiling, less what was returned since), gets each definition with its lines; a range read never changes.
"""
from __future__ import annotations

import re
import sys

import pytest
from deepagents.backends.utils import format_content_with_line_numbers
from langchain_core.messages import AIMessage, ToolMessage

from app.agents import stage_memory
from app.agents.room_for_reads import answer, build_room_for_reads_middleware
from app.agents.workspace_backend import WorkspaceBackend

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The input ceiling every test runs under, in tokens; at three characters a token.
CEILING = 50_000


def _source(lines: int = 300) -> str:
    """A file of `lines` lines: a top-level function every 30 lines, `handle_refund` at line 151."""
    out = []
    for n in range(1, lines + 1):
        if n % 30 == 1:
            out.append("def handle_refund(order, amount):" if n == 151 else f"def step_{n}(value):")
        else:
            out.append(f"    value = value + {n}  # keep the running total")
    return "\n".join(out) + "\n"


SOURCE = _source()


class _ModelCall:
    model = None


class _ToolCall:
    def __init__(self, args: dict) -> None:
        self.tool_call = {"name": "read_file", "args": args, "id": "r1"}


def _a_reply_reported(middleware, input_tokens: int) -> None:
    reply = AIMessage(content="", usage_metadata={"input_tokens": input_tokens, "output_tokens": 20,
                                                  "total_tokens": input_tokens + 20})
    middleware.wrap_model_call(_ModelCall(), lambda request: reply)


def _read(middleware, backend: WorkspaceBackend, **args) -> str:
    """`read_file` as the stage calls it: the model's arguments, a 400-line window filled in, the text numbered."""

    def tool(request):
        given = request.tool_call["args"]
        result = backend.read(given["file_path"], offset=given.get("offset", 0), limit=given.get("limit", 400))
        return ToolMessage(content=format_content_with_line_numbers(result.file_data["content"]),
                           tool_call_id="r1")

    return middleware.wrap_tool_call(_ToolCall(args), tool).content


@pytest.fixture
def stage(tmp_path, monkeypatch):
    monkeypatch.setenv("READS_SIZED_TO_THE_ROOM", "on")
    monkeypatch.setenv("CTX_MAX_TOKENS", str(CEILING))
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    (tmp_path / "billing.py").write_text(SOURCE, encoding="utf-8")
    stage_memory.forget_everything()
    with stage_memory.remembering(f"stage-room-{tmp_path.name}"):
        yield build_room_for_reads_middleware(), WorkspaceBackend(str(tmp_path), virtual_mode=True)
    stage_memory.forget_everything()


def test_a_whole_read_past_the_room_left_gets_the_outline_and_its_ranges(stage):
    middleware, backend = stage
    _a_reply_reported(middleware, CEILING - 1_000)  # 3,000 characters left; the file numbered is about 12,000

    given = _read(middleware, backend, file_path="/billing.py")

    assert "keep the running total" not in given
    assert "300 lines" in given
    assert re.search(r"^\s*151-\d+\s+def handle_refund\(order, amount\):?", given, re.M)
    assert "by range" in given


@pytest.mark.parametrize("window", [{"offset": 140, "limit": 20}, {"limit": 400}, {"offset": 100}])
def test_a_range_read_is_never_answered_with_an_outline(stage, window):
    middleware, backend = stage
    _a_reply_reported(middleware, CEILING + 5_000)  # already past the ceiling

    given = _read(middleware, backend, file_path="/billing.py", **window)

    assert "def handle_refund(order, amount):" in given
    assert "room left" not in given


def test_a_whole_read_that_fits_is_whole(stage):
    middleware, backend = stage
    _a_reply_reported(middleware, 10_000)

    given = _read(middleware, backend, file_path="/billing.py")

    assert given == format_content_with_line_numbers(SOURCE)


def test_what_this_reply_s_earlier_reads_returned_comes_out_of_the_room(stage, tmp_path):
    """Each file fits the room alone; the second does not fit beside the first."""
    middleware, backend = stage
    (tmp_path / "ledger.py").write_text(SOURCE, encoding="utf-8")
    numbered = len(format_content_with_line_numbers(SOURCE))
    _a_reply_reported(middleware, CEILING - (numbered * 3 // 2) // 3)

    first = _read(middleware, backend, file_path="/billing.py")
    second = _read(middleware, backend, file_path="/ledger.py")

    assert first == format_content_with_line_numbers(SOURCE)
    assert "keep the running total" not in second and "def handle_refund" in second


def test_with_the_switch_off_a_whole_read_past_the_room_is_whole(stage, monkeypatch):
    middleware, backend = stage
    monkeypatch.setenv("READS_SIZED_TO_THE_ROOM", "off")
    _a_reply_reported(middleware, CEILING + 5_000)

    given = _read(middleware, backend, file_path="/billing.py")

    assert given == format_content_with_line_numbers(SOURCE)


def test_before_any_reply_the_room_is_not_known_and_a_read_is_whole(stage):
    middleware, backend = stage

    given = _read(middleware, backend, file_path="/billing.py")

    assert given == format_content_with_line_numbers(SOURCE)


def test_without_the_outline_module_the_top_level_definitions_are_given(monkeypatch):
    monkeypatch.setitem(sys.modules, "app.analysis.outline", None)  # the import fails, as before that module exists
    text = "class Ledger:\n    def total(self):\n        return 1\n\n\ndef settle(ledger):\n    return ledger\n"

    given = answer("/ledger.py", text, room=10)

    assert re.search(r"^\s*1-5\s+class Ledger:$", given, re.M)
    assert re.search(r"^\s*6-7\s+def settle\(ledger\):$", given, re.M)
    assert "def total" not in given


def test_the_answer_uses_no_banned_word():
    given = answer("/billing.py", SOURCE, room=500)

    assert not BANNED.search(given)
