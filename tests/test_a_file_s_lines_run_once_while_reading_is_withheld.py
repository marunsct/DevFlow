"""While reading is withheld and decided file by file, a file's lines run once in a stage visit, across summaries.

Measured on a medium run in parallel mode (LF.1577): a backend builder with thinking off for the stage had its reads
decided file by file (LF.1527), and each was refused only when the conversation the call sent still held it. Every
request was fitted to the model's context, cutting the earlier results, so the same windows of `routes.py`,
`schemas.py` and `conftest.py` counted as never read and ran again: 134 reads run while withheld in one stage, until
it reached its step limit and the run failed. The captured visit here made 31 reads across four fitted requests.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.agents import settled_answer, stage_memory
from app.agents.settled_answer import build_settled_answer_middleware
from app.agents.shell_reads import build_shell_read_middleware

CAPTURED = json.loads((Path(__file__).parent / "captured" / "builder-reads-while-withheld-across-summaries.json")
                      .read_text(encoding="utf-8"))
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FROM_DISK = "read from disk"
OFFERED = ("read_file", "grep", "ls", "write_artifact", "edit_artifact", "run_terminal_command")
ROUTES = "task-management-dashboard/task_management_dashboard/routes.py"
#: What a fitted request still holds of the visit: its request and its latest search, no read.
SUMMARISED = [
    HumanMessage(content="Build the routes"),
    AIMessage(content="", tool_calls=[{"name": "grep", "id": "g1", "args": {"pattern": "def create_"}}]),
    ToolMessage(content="routes.py:120: def create_item(", tool_call_id="g1", name="grep"),
]


class Answer(BaseModel):
    changed_files: list[str]


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


@pytest.fixture
def a_builder_with_thinking_off(monkeypatch):
    """The builder's answer guard, thinking off for the rest of the stage, in one stage visit."""
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "off")
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    monkeypatch.setattr(settled_answer, "_thinking_stays_off_for_the_stage", lambda *a, **k: True)
    guard = build_settled_answer_middleware(Answer, "specialist_backend", 40)
    with stage_memory.remembering("a-builder-thread"):
        yield guard
    stage_memory.forget_everything()


def _a_call_after_a_summary(guard) -> None:
    """A model call whose conversation no longer holds any earlier read: the request was fitted, its results cut."""
    guard.wrap_model_call(_Request(messages=SUMMARISED,
                                   tools=[SimpleNamespace(name=name) for name in OFFERED], model=None,
                                   model_settings={}), lambda request: None)


def _sent(guard, name: str, args: dict) -> ToolMessage:
    call = SimpleNamespace(tool_call={"name": name, "id": "c1", "args": args})
    return guard.wrap_tool_call(call, lambda request: ToolMessage(content=FROM_DISK, tool_call_id="c1"))


def _ran(answer: ToolMessage) -> bool:
    return answer.content == FROM_DISK


def _replayed(guard) -> list[tuple[str, ToolMessage]]:
    answers = []
    for read in CAPTURED["reads"]:
        _a_call_after_a_summary(guard)
        answers.append((read["args"]["file_path"].rsplit("/", 1)[-1], _sent(guard, read["tool"], read["args"])))
    return answers


def test_the_captured_builder_s_reads_run_each_window_once_across_summaries(a_builder_with_thinking_off):
    """Worked out from the captured windows: `routes.py` 0-400, 400-800 and 800-1200 run; `schemas.py` 0-400 and
    200-600; one each of `conftest.py`, `models.py`, `main.py`; `test_routes.py` 0-400 and 400-800. Old code: 31."""
    ran = Counter(name for name, answer in _replayed(a_builder_with_thinking_off) if _ran(answer))

    assert ran == {"routes.py": 3, "schemas.py": 2, "test_routes.py": 2, "conftest.py": 1, "models.py": 1,
                   "main.py": 1}


def test_lines_read_before_a_summary_are_refused_by_name_as_already_read(a_builder_with_thinking_off):
    _a_call_after_a_summary(a_builder_with_thinking_off)
    _sent(a_builder_with_thinking_off, "read_file", {"file_path": ROUTES})
    _a_call_after_a_summary(a_builder_with_thinking_off)

    again = _sent(a_builder_with_thinking_off, "read_file", {"file_path": ROUTES, "offset": 260, "limit": 100})

    assert not _ran(again)
    assert ROUTES in again.content and "already read in this stage" in again.content


def test_a_file_written_since_is_read_again(a_builder_with_thinking_off):
    _a_call_after_a_summary(a_builder_with_thinking_off)
    _sent(a_builder_with_thinking_off, "read_file", {"file_path": ROUTES})
    _sent(a_builder_with_thinking_off, "edit_artifact", {"relative_path": ROUTES, "find": "a", "replace": "b"})
    _a_call_after_a_summary(a_builder_with_thinking_off)

    assert _ran(_sent(a_builder_with_thinking_off, "read_file", {"file_path": ROUTES}))


def test_one_file_runs_at_most_four_reads_while_withheld(a_builder_with_thinking_off):
    ran = 0
    for offset in range(0, 2000, 400):
        _a_call_after_a_summary(a_builder_with_thinking_off)
        ran += _ran(_sent(a_builder_with_thinking_off, "read_file", {"file_path": ROUTES, "offset": offset}))

    assert ran == 4


def test_past_sixteen_reads_the_read_tool_is_withheld_whole(a_builder_with_thinking_off):
    answers = []
    for number in range(18):
        _a_call_after_a_summary(a_builder_with_thinking_off)
        answers.append(_sent(a_builder_with_thinking_off, "read_file", {"file_path": f"pkg/module_{number}.py"}))

    assert [_ran(answer) for answer in answers] == [True] * 16 + [False, False]
    assert "withheld" in answers[-1].content


def test_a_command_that_reads_the_same_lines_again_after_a_summary_is_refused(tmp_path, a_builder_with_thinking_off):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "routes.py").write_text("".join(f"line {n}\n" for n in range(30)), encoding="utf-8")
    shell = build_shell_read_middleware(str(tmp_path))
    answers = []
    for _ in range(2):
        _a_call_after_a_summary(a_builder_with_thinking_off)
        shell.wrap_model_call(_Request(messages=SUMMARISED), lambda request: None)
        call = SimpleNamespace(tool_call={"name": "run_terminal_command", "id": "c1",
                                          "args": {"command": ["sed", "-n", "1,20p", "app/routes.py"]}})
        answers.append(shell.wrap_tool_call(call, lambda request: ToolMessage(content="ran", tool_call_id="c1")))

    assert "line 0" in answers[0].content
    assert "already read in this stage" in answers[1].content


def test_the_refusals_avoid_the_banned_words(a_builder_with_thinking_off):
    refusals = [answer.content for _, answer in _replayed(a_builder_with_thinking_off) if not _ran(answer)]
    for offset in range(1200, 2000, 400):
        _a_call_after_a_summary(a_builder_with_thinking_off)
        refusals.append(_sent(a_builder_with_thinking_off, "read_file", {"file_path": ROUTES, "offset": offset}).content)
    for number in range(20):
        _a_call_after_a_summary(a_builder_with_thinking_off)
        refusals.append(_sent(a_builder_with_thinking_off, "read_file", {"file_path": f"pkg/m_{number}.py"}).content)
    said = [re.sub(r"'[^']*'", "", text) for text in refusals]  # the file's own name is the product's

    assert len(set(said)) >= 3 and not [text for text in said if BANNED.search(text)]
