"""A file read again is answered with its text when the earlier text is no longer in the model's request.

Measured on two Java testing stages: 172 of 207 reads of a file read earlier came after the earlier result had been
summarised out of the request, and the read guard still counted them as repeats ("you have already read lines",
"same bytes", withheld text) about text the model could not see. The guard now asks what the last request showed.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents import stage_memory
from app.agents.workspace_backend import WorkspaceBackend, build_fresh_conversation_middleware

SOURCE = "\n".join(f"public int method{i}() {{ return {i} * 17; }}" for i in range(1, 30))


class _Request:
    def __init__(self, messages):
        self.messages = messages


def _model_is_sent(*tool_texts: str) -> None:
    history = [HumanMessage(content="work"), AIMessage(content="", tool_calls=[
        {"name": "read_file", "args": {}, "id": "c0"}])]
    history += [ToolMessage(content=t, tool_call_id=f"c{i}") for i, t in enumerate(tool_texts)]
    build_fresh_conversation_middleware().wrap_model_call(_Request(history), lambda request: None)


def _read(backend: WorkspaceBackend) -> str:
    return backend.read("/Service.java").file_data["content"]


def _backend(tmp_path) -> WorkspaceBackend:
    (tmp_path / "Service.java").write_text(SOURCE, encoding="utf-8")
    return WorkspaceBackend(str(tmp_path), virtual_mode=True)


def test_a_read_whose_earlier_result_was_summarised_away_gets_the_text_and_no_notice(tmp_path):
    with stage_memory.remembering("stage-sight-gone"):
        backend = _backend(tmp_path)
        for _ in range(4):
            _model_is_sent(SOURCE)
            _read(backend)
        _model_is_sent("a summary now stands where the file was")

        answer = _read(backend)

        assert answer == SOURCE


def test_a_read_whose_earlier_result_is_still_in_the_request_gets_the_notice(tmp_path):
    with stage_memory.remembering("stage-sight-kept"):
        backend = _backend(tmp_path)
        for _ in range(4):
            _model_is_sent(SOURCE)
            _read(backend)

        answer = _read(backend)

        assert answer != SOURCE
        assert "has not changed" in answer


def test_after_the_text_is_given_again_the_count_starts_over(tmp_path):
    with stage_memory.remembering("stage-sight-reset"):
        backend = _backend(tmp_path)
        for _ in range(9):
            _model_is_sent(SOURCE)
            backend.read("/Service.java")
        _model_is_sent("summary")
        backend.read("/Service.java")
        _model_is_sent(SOURCE)

        result = backend.read("/Service.java")

        assert result.error is None
        assert SOURCE in result.file_data["content"]


def test_recording_what_the_request_shows_does_not_change_the_messages():
    with stage_memory.remembering("stage-sight-pure"):
        history = [HumanMessage(content="work"), ToolMessage(content=SOURCE, tool_call_id="c1")]
        before = [m.model_dump() for m in history]

        build_fresh_conversation_middleware().wrap_model_call(_Request(history), lambda request: None)

        assert [m.model_dump() for m in history] == before


def test_a_read_outside_any_request_is_judged_as_before(tmp_path):
    with stage_memory.remembering("stage-sight-unknown"):
        backend = _backend(tmp_path)
        answers = [_read(backend) for _ in range(5)]

        assert answers[0] == SOURCE
        assert answers[4] != SOURCE
