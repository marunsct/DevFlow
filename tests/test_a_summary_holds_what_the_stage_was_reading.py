"""After a summary, a reading or writing stage's memory holds whole the files it was reading and writing (LF.1288).

Measured on one medium run: a technical lead summarised 21 times re-read 20 files 12 times each, and the suite's
author read its own file 3-8 times a visit (up to 24). Each memory held the files the visit began with; every file
read since was in the conversation, which a summary deletes, so the stage read it again - and the author's own file
was held as it stood at the start, "read for the current text". A summary is where the stage loses what it read, so
there the memory is chosen again: the files it wrote, then those it read most. Between summaries, and on a product
whose files fit, the memory stays byte for byte as it was.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables.config import var_child_runnable_config

from app.agents import project_memory, stage_memory
from app.agents.compaction import RequestKeepingSummarization
from app.agents.review_files import held_named_in, held_section

READER = "test_round_0"
WRITER = "acceptance_author_0"
#: The writing stages: the suite's author, and a builder (measured on a medium run: a sprint's backend builder read
#: about six files a call for 24 minutes, a summary every two or three calls, one write).
WRITERS = pytest.mark.parametrize("writer", [WRITER, "specialist_backend_0"])
A, B, C, D, E = (f"app/f{n:02}.py" for n in range(5))


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "65536")
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("CANONICAL_MEMORY", "on")
    stage_memory.forget_everything()
    yield
    stage_memory.forget_everything()


def _file(root, name: str, size: int, said: str = "") -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    head = f"def {name.rsplit('/', 1)[-1].split('.')[0]}():\n    return {said or 'None'!r}\n"
    (root / name).write_text(head + "".join(f"# what {name} does, line {k}\n" for k in range(size // 32)))


def _a_product_past_its_room(root) -> None:
    """Five 18,000-character files: two fit the memory's room numbered, the others are outlined."""
    for name in (A, B, C, D, E):
        _file(root, name, 18_000)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "technical_specification.md").write_text("# Specification\nThe product keeps records.\n")


class _Request(SimpleNamespace):
    def override(self, **changes):
        return _Request(**{**self.__dict__, **changes})


class _Visit:
    """One stage visit: its project memory's calls, its summaries and its reads, in one stage's memory."""

    def __init__(self, root, stage: str, tmp_path):
        self.root, self.stage, self.tmp = root, stage, tmp_path
        self.memory = project_memory.build_project_memory_middleware(str(root))

    def __enter__(self):
        self._token = var_child_runnable_config.set(
            {"configurable": {"app_stage": self.stage, "thread_id": f"{self.stage}-visit"}})
        return self

    def __exit__(self, *exc):
        var_child_runnable_config.reset(self._token)

    def call(self, messages: list) -> list:
        """The messages the model is sent for one call."""
        seen: list = []
        self.memory.wrap_model_call(_Request(messages=messages, model=None), lambda request: seen.append(request))
        return seen[-1].messages

    def summarised(self, messages: list) -> list:
        """The conversation after the stage's summariser replaced all but its last four messages."""
        summariser = GenericFakeChatModel(messages=iter([AIMessage(content="The stage read and wrote files.")] * 2))
        middleware = RequestKeepingSummarization(summariser, backend=FilesystemBackend(root_dir=str(self.tmp)),
                                                 trigger=("messages", 10), keep=("messages", 4),
                                                 trim_tokens_to_summarize=1_000)
        seen: list = []

        def handler(request):
            seen.append(request.messages)
            return ModelResponse(result=[AIMessage(content="done")])

        middleware.wrap_model_call(ModelRequest(model=summariser, messages=messages, state={"messages": messages},
                                                tools=[]), handler)
        return seen[-1]

    def read(self, path: str):
        call = SimpleNamespace(tool_call={"name": "read_file", "id": "after", "args": {"file_path": path}})
        return self.memory.wrap_tool_call(call, lambda request: "the file from disk")


def _read(n: int, path: str, root) -> list:
    text = (root / path).read_text()
    numbered = "\n".join(f"{k:>6}\t{line}" for k, line in enumerate(text.splitlines(), start=1))
    return [AIMessage(content="", id=f"ai-read{n}", tool_calls=[
                {"id": f"read{n}", "name": "read_file", "args": {"file_path": path}}]),
            ToolMessage(content=numbered, tool_call_id=f"read{n}", id=f"tool-read{n}")]


def _wrote(n: int, path: str) -> list:
    return [AIMessage(content="", id=f"ai-write{n}", tool_calls=[
                {"id": f"write{n}", "name": "write_artifact", "args": {"relative_path": path, "content": "x"}}]),
            ToolMessage(content="written", tool_call_id=f"write{n}", id=f"tool-write{n}")]


def _later() -> list:
    """Four messages a summary keeps."""
    return [AIMessage(content="Looking further.", id="ai-on0"), HumanMessage(content="Go on.", id="on0"),
            AIMessage(content="Looking further.", id="ai-on1"), HumanMessage(content="Go on.", id="on1")]


def _opening(stage: str = READER) -> HumanMessage:
    return HumanMessage(content="Run the tests of this milestone.\n\n" + held_section([A, B], stage), id="opening")


def _first_message(messages: list) -> str:
    return messages[0].content


def _a_reading_visit(root, tmp_path, reads: list[str]) -> tuple[_Visit, str, str]:
    """A test round opened holding A and B; it reads `reads` and is summarised. The memory of its first call and of
    the call after the summary."""
    opening = _opening()
    with _Visit(root, READER, tmp_path) as visit:
        first = _first_message(visit.call([opening]))
        conversation = [opening]
        for n, path in enumerate(reads):
            conversation += _read(n, path, root)
        after = _first_message(visit.call(visit.summarised(conversation + _later())))
    return visit, first, after


def test_after_a_summary_the_memory_holds_the_files_the_stage_read(tmp_path):
    _a_product_past_its_room(tmp_path)
    opening = _opening()
    with _Visit(tmp_path, READER, tmp_path) as visit:
        first = _first_message(visit.call([opening]))
        assert f"=== {C} (numbered lines" not in first, "the arrangement: C is not held"
        conversation = [opening, *_read(0, C, tmp_path), *_read(1, D, tmp_path), *_read(2, C, tmp_path)]
        after = _first_message(visit.call(visit.summarised(conversation + _later())))
        answer = visit.read(C)

    assert f"=== {C} (numbered lines) ===\n     1\tdef f02():" in after
    assert f"=== {D} (numbered lines) ===" in after
    assert isinstance(answer, ToolMessage) and project_memory.HELD_POINTER in answer.content


@WRITERS
def test_after_a_summary_a_writing_stage_holds_its_files_as_they_are_now(tmp_path, writer):
    for n in range(10):
        _file(tmp_path, f"proj/app/part{n:02}.py", 8_000)
    written = "proj/acceptance/records.spec.js"
    (tmp_path / written).parent.mkdir(parents=True)
    (tmp_path / written).write_text("test('[AC-1] keeps a record', async () => {});\n")
    opening = HumanMessage(content="Write the acceptance tests of AC-1.", id="opening")
    with _Visit(tmp_path, writer, tmp_path) as visit:
        visit.call([opening])
        (tmp_path / written).write_text("test('[AC-1] keeps a record as it is now', async () => {});\n")
        after = _first_message(visit.call(visit.summarised([opening, *_wrote(0, written), *_wrote(1, written),
                                                            *_wrote(2, written), *_later()])))

    assert f"=== {written} (numbered lines) ===\n     1\ttest('[AC-1] keeps a record as it is now'" in after


def test_the_request_names_the_files_held_now(tmp_path):
    _a_product_past_its_room(tmp_path)

    _, _, after = _a_reading_visit(tmp_path, tmp_path, [C, D, C])

    closing = after[after.rindex("[Already in front of you"):]
    assert held_named_in(after) == (C, D)
    assert f"`{C}`, `{D}`" in closing and f"`{A}`" not in closing and f"`{B}`" not in closing


def test_a_later_sprint_s_tests_are_not_chosen(tmp_path, monkeypatch):
    from app.acceptance import sprint_scope

    _a_product_past_its_room(tmp_path)
    monkeypatch.setattr(sprint_scope, "later_sprints_files", lambda root: {C: ["AC-9"]})

    _, _, after = _a_reading_visit(tmp_path, tmp_path, [C, D, C])

    assert f"=== {C} (numbered" not in after and f"=== {D} (numbered lines) ===" in after


def test_a_file_the_harness_keeps_is_not_chosen(tmp_path, monkeypatch):
    _a_product_past_its_room(tmp_path)
    monkeypatch.setattr(project_memory, "kept_by_the_harness", lambda root: (C,))

    _, _, after = _a_reading_visit(tmp_path, tmp_path, [C, D, C])

    assert f"=== {C} (numbered" not in after and f"=== {D} (numbered lines) ===" in after


def test_the_memory_is_not_rendered_again_between_summaries(tmp_path):
    """Guard: a write between two calls leaves the memory byte for byte, so the server's cache holds."""
    _a_product_past_its_room(tmp_path)
    opening = _opening()
    with _Visit(tmp_path, READER, tmp_path) as visit:
        first = _first_message(visit.call([opening]))
        _file(tmp_path, A, 18_000, said="changed")
        second = visit.call([opening, AIMessage(content="Changed A.", id="ai0"), HumanMessage(content="Go on.")])

    assert _first_message(second) == first


def test_a_stage_whose_reads_were_all_held_keeps_its_memory(tmp_path):
    """Guard: reads of the files it holds only - nothing to choose again."""
    _a_product_past_its_room(tmp_path)

    _, first, after = _a_reading_visit(tmp_path, tmp_path, [A, B, A])

    assert after.startswith(first[:first.index("Run the tests of this milestone.")])


@WRITERS
def test_a_writing_stage_whose_files_fit_keeps_its_memory(tmp_path, writer):
    """Guard: a small product's author is as today - its memory is the one its visit opened on."""
    (tmp_path / "app.py").write_text("def main():\n    return 1\n")
    written = "acceptance/records.spec.js"
    (tmp_path / "acceptance").mkdir()
    (tmp_path / written).write_text("test('[AC-1] keeps a record', async () => {});\n")
    opening = HumanMessage(content="Write the acceptance tests of AC-1.", id="opening")
    with _Visit(tmp_path, writer, tmp_path) as visit:
        first = _first_message(visit.call([opening]))
        (tmp_path / written).write_text("test('[AC-1] keeps a record as it is now', async () => {});\n")
        after = _first_message(visit.call(visit.summarised([opening, *_wrote(0, written), *_wrote(1, written),
                                                            *_wrote(2, written), *_later()])))

    memory = first[:first.index("Write the acceptance tests of AC-1.")]
    assert after.startswith(memory) and "(numbered lines" not in after


def test_a_builder_past_its_room_opens_on_an_outline_of_the_files_it_does_not_hold(tmp_path):
    for n in range(10):
        _file(tmp_path, f"proj/app/part{n:02}.py", 8_000)

    memory, held = project_memory.render_for_a_stage(tmp_path, None, "Build the records routes.", "specialist_backend_0")

    left = next(f"proj/app/part{n:02}.py" for n in range(10) if f"proj/app/part{n:02}.py" not in held)
    assert f"\n{left} (252 lines)\n  1-252  def part{left[-5:-3]}()\n" in memory


def test_a_builder_whose_files_fit_has_no_outline(tmp_path):
    """Guard: a small product's builder opens on the memory it always had."""
    for n in range(3):
        _file(tmp_path, f"proj/app/part{n:02}.py", 300)

    memory, held = project_memory.render_for_a_stage(tmp_path, None, "Build the records routes.", "specialist_backend_0")

    assert {f"proj/app/part{n:02}.py" for n in range(3)} <= set(held)
    assert "=== Outline" not in memory and "(numbered lines" not in memory
