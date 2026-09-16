"""A full, unclipped record of a run, for opening it again later.

The event stream is a UI feed: it clips at 2,000 characters, carries tool
output as the tool produced it rather than as the model received it, and has
never recorded the prompts. Each of those cost diagnosis time in one session -
a notice past the clip read as "no note fired", middleware notices were
mis-measured until a live agent was driven by hand, and "largest model output"
came back as the clip rather than the model.
"""

from __future__ import annotations

import json

import pytest

from app.observability.transcript import (
    MAX_FIELD_CHARS,
    read_transcript,
    record,
    render_transcript,
    transcript_path,
    transcripts_enabled,
)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RUN_TRANSCRIPT", raising=False)
    return tmp_path


def test_an_entry_round_trips() -> None:
    record("run-1", "product_manager", "model_request",
           messages=[{"role": "human", "content": "Build a to-do app."}])

    entries = read_transcript("run-1")

    assert len(entries) == 1
    assert entries[0]["kind"] == "model_request"
    assert entries[0]["messages"][0]["content"] == "Build a to-do app."
    assert entries[0]["stage"] == "product_manager"


def test_nothing_is_clipped_at_the_event_feed_s_limit() -> None:
    """The whole reason this exists beside the event stream."""
    body = "x" * 50_000

    record("run-1", "s", "tool_result", content=body)

    assert read_transcript("run-1")[0]["content"] == body


def test_a_field_past_the_cap_says_how_much_is_missing() -> None:
    """Truncation is recorded, never silent - a silent cut is what made the
    event stream misleading rather than merely partial."""
    body = "y" * (MAX_FIELD_CHARS + 5_000)

    record("run-1", "s", "tool_result", content=body)
    kept = read_transcript("run-1")[0]["content"]

    assert len(kept) < len(body)
    assert "5,000 further characters not recorded" in kept
    assert f"{MAX_FIELD_CHARS + 5000:,} characters" in kept


def test_a_torn_line_does_not_cost_the_entries_before_it() -> None:
    """A run killed mid-write leaves one, and the rest is still the record."""
    record("run-1", "s", "note", text="first")
    record("run-1", "s", "note", text="second")
    path = transcript_path("run-1")
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"kind": "note", "text": "tor')

    entries = read_transcript("run-1")

    assert [e["text"] for e in entries] == ["first", "second"]


def test_a_value_that_will_not_serialise_keeps_the_entry() -> None:
    record("run-1", "s", "note", obj=object())

    entries = read_transcript("run-1")

    assert len(entries) == 1
    assert entries[0]["kind"] == "note"


def test_kinds_can_be_filtered() -> None:
    record("run-1", "s", "model_request", messages=[])
    record("run-1", "s", "tool_call", tool="ls")
    record("run-1", "s", "tool_result", tool="ls", content="a")

    assert len(read_transcript("run-1", {"tool_call", "tool_result"})) == 2


def test_it_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("RUN_TRANSCRIPT", "false")

    assert not transcripts_enabled()
    record("run-1", "s", "note", text="x")
    assert read_transcript("run-1") == []


def test_a_run_with_no_transcript_reads_as_empty() -> None:
    assert read_transcript("never-ran") == []
    assert "No transcript" in render_transcript("never-ran")


def test_a_missing_run_id_records_nothing() -> None:
    record(None, "s", "note", text="x")
    record("", "s", "note", text="x")  # must not raise


def test_the_rendered_form_shows_both_sides_of_a_turn() -> None:
    record("run-1", "pm", "model_request",
           messages=[{"role": "human", "content": "Build it."}])
    record("run-1", "pm", "model_response", text="",
           tool_calls=[{"name": "read_file", "args": {"file_path": "/a.md"}}],
           usage={"input_tokens": 10}, finish_reason="tool_calls")
    record("run-1", "pm", "tool_call", tool="read_file", args={"file_path": "/a.md"})
    record("run-1", "pm", "tool_result", tool="read_file", content="# A")

    rendered = render_transcript("run-1")

    assert "### stage: pm" in rendered
    assert "Build it." in rendered
    assert "calls read_file" in rendered
    assert "# A" in rendered


def test_a_run_id_cannot_escape_the_transcript_directory(tmp_path) -> None:
    """The id reaches this from a request; a path separator in it must not
    place the file somewhere else."""
    path = transcript_path("../../etc/passwd")

    assert path is not None
    assert path.parent == tmp_path / "transcripts"
    assert "/" not in path.name.replace(".jsonl", "")


def test_both_halves_of_the_record_are_wired() -> None:
    """The callback records prompts and replies; the middleware records tool
    results after the notices. Neither alone is the record."""
    import inspect

    from app.agents import role_agent
    from app.server import agent_stream

    assert "build_transcript_callback" in inspect.getsource(agent_stream.build_activity_callbacks)
    assert "build_transcript_middleware(stage)" in inspect.getsource(role_agent.create_role_agent)


def test_the_run_id_reaches_the_inner_agent() -> None:
    """Middleware inside a role agent can only see `get_config()`.

    The callbacks carry the run id because they are constructed with it. A
    middleware is constructed once per agent and cannot be, so the id has to
    travel in the config - and until it did, the transcript recorded every
    prompt and reply and not one tool call, which is half a run.
    """
    from app.graph.workflow import _inner_agent_config
    from app.tracing import APP_RUN_ID_KEY

    config = _inner_agent_config("thread-1", "run-7", [], recursion_limit=60)

    assert config["configurable"][APP_RUN_ID_KEY] == "run-7"
    assert config["configurable"]["thread_id"] == "thread-1"
    assert config["recursion_limit"] == 60


def test_a_run_with_no_id_still_produces_a_usable_config() -> None:
    from app.graph.workflow import _inner_agent_config
    from app.tracing import APP_RUN_ID_KEY

    config = _inner_agent_config("thread-1", None, [])

    assert APP_RUN_ID_KEY not in config["configurable"]
    assert config["configurable"]["thread_id"] == "thread-1"


def test_every_inner_invocation_builds_its_config_the_same_way() -> None:
    """Two call sites, and a third would otherwise be written without the id -
    which is how the transcript came to record half a run."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)

    # Both invocations go through the builder. `agent.get_state` may still take
    # a bare thread id: it reads a checkpoint and runs no middleware.
    invokes = [ln for ln in source.splitlines() if "agent.invoke(" in ln]
    assert len(invokes) == 2
    assert source.count("_inner_agent_config(") == 3  # the definition and both sites
