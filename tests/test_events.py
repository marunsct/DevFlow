"""Event bus: sequencing, bounded history, and paging."""

import pytest

from app.server.events import EventBus, RunEvent, publish_stage_event, redact_metadata


@pytest.fixture
async def bus(redis_container):
    from app.server.redis_client import reset_clients

    reset_clients()
    event_bus = EventBus()
    yield event_bus
    await event_bus.purge("run-test")


def _event(run_id: str, sequence: int, **kwargs) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        sequence=sequence,
        stage=kwargs.pop("stage", "product_manager"),
        event_type=kwargs.pop("event_type", "stage_change"),
        message=kwargs.pop("message", "working"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Sequencing - the cursor regression
# ---------------------------------------------------------------------------


async def test_sequences_are_monotonic(bus):
    first = await bus.next_sequence("run-test")
    second = await bus.next_sequence("run-test")
    assert second == first + 1


async def test_publish_stage_event_assigns_a_real_sequence(bus):
    """It used to hardcode 0, which collided every event and broke both the
    polling cursor and reconnect replay."""
    await publish_stage_event(bus, "run-test", "product_manager", "reading the brief")
    await publish_stage_event(bus, "run-test", "tools_models", "comparing options")

    history = await bus.get_history("run-test")
    sequences = [e.sequence for e in history]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)
    assert 0 not in sequences


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


async def test_history_round_trips(bus):
    await bus.publish("run-test", _event("run-test", 1, message="one"))
    await bus.publish("run-test", _event("run-test", 2, message="two"))

    history = await bus.get_history("run-test")
    assert [e.message for e in history] == ["one", "two"]


async def test_history_pages_by_offset_and_limit(bus):
    for i in range(1, 11):
        await bus.publish("run-test", _event("run-test", i, message=f"m{i}"))

    page = await bus.get_history("run-test", offset=2, limit=3)
    assert [e.message for e in page] == ["m3", "m4", "m5"]


async def test_history_length_is_reported_without_fetching_it(bus):
    for i in range(1, 6):
        await bus.publish("run-test", _event("run-test", i))
    assert await bus.history_length("run-test") == 5


async def test_replay_returns_only_events_after_a_cursor(bus):
    for i in range(1, 6):
        await bus.publish("run-test", _event("run-test", i, message=f"m{i}"))

    missed = await bus.get_history("run-test", since_sequence=3)
    assert [e.message for e in missed] == ["m4", "m5"]


async def test_history_is_capped(bus, monkeypatch):
    """Unbounded history was a Redis memory leak."""
    monkeypatch.setattr(EventBus, "MAX_HISTORY", 5)
    for i in range(1, 21):
        await bus.publish("run-test", _event("run-test", i, message=f"m{i}"))

    history = await bus.get_history("run-test")
    assert len(history) == 5
    assert [e.message for e in history] == ["m16", "m17", "m18", "m19", "m20"]


async def test_purge_clears_history_and_the_counter(bus):
    await bus.publish("run-test", _event("run-test", 1))
    await bus.purge("run-test")

    assert await bus.history_length("run-test") == 0
    assert await bus.next_sequence("run-test") == 1


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_sensitive_keys_are_redacted():
    redacted = redact_metadata(
        {
            "api_key": "sk-secret",
            "nested": {"auth_token": "t", "safe": "visible"},
            "items": [{"password": "p"}],
            "stage": "product_manager",
        }
    )
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["auth_token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "visible"
    assert redacted["items"][0]["password"] == "[REDACTED]"
    assert redacted["stage"] == "product_manager"


def test_redaction_does_not_mutate_its_input():
    original = {"api_key": "sk-secret"}
    redact_metadata(original)
    assert original["api_key"] == "sk-secret"


# ---------------------------------------------------------------------------
# The execution timeline
# ---------------------------------------------------------------------------
#
# `RunStatusResponse.stages` was a hardcoded empty list, so the dashboard's flow
# chart fell through to a fallback that fabricates one node from `current_stage`.
# A run that had finished three stages showed one.


def _stage_event(stage: str, message: str, timestamp: str, status: str = "running"):
    from types import SimpleNamespace

    return SimpleNamespace(
        event_type="stage_change", stage=stage, message=message,
        timestamp=timestamp, metadata={"status": status},
    )


def test_the_timeline_has_one_node_per_stage_in_execution_order():
    from app.server.runs import _derive_stages

    stages = _derive_stages([
        _stage_event("product_manager", "Reading.", "2026-09-10T10:00:00+00:00"),
        _stage_event("tools_models", "Comparing.", "2026-09-10T10:02:00+00:00"),
        _stage_event("principal_architect", "Spec.", "2026-09-10T10:05:00+00:00"),
    ], "principal_architect")

    assert [s["name"] for s in stages] == [
        "product_manager", "tools_models", "principal_architect",
    ]
    assert stages[0]["duration_seconds"] == 120.0
    assert stages[0]["status"] == "completed"
    assert stages[-1]["status"] == "running", "the last stage is still open"


def test_a_repeated_stage_increments_rather_than_adding_a_node():
    """The specialist loop and review revisions re-enter the same node; a row
    per iteration would make the chart unreadable."""
    from app.server.runs import _derive_stages

    stages = _derive_stages([
        _stage_event("specialist_dispatch", "Working.", "2026-09-10T10:00:00+00:00"),
        _stage_event("specialist_dispatch", "Working.", "2026-09-10T10:01:00+00:00"),
        _stage_event("specialist_dispatch", "Working.", "2026-09-10T10:02:00+00:00"),
    ], "specialist_dispatch")

    assert len(stages) == 1
    assert stages[0]["retry_count"] == 2


def test_an_empty_history_yields_an_empty_timeline():
    from app.server.runs import _derive_stages

    assert _derive_stages([], None) == []


# ---------------------------------------------------------------------------
# Agent activity
# ---------------------------------------------------------------------------
#
# The graph only reported at node boundaries, so a real model turn was minutes
# of silence.


def _captured_stream():
    from app.server.agent_stream import AgentActivityStream

    published: list = []
    stream = AgentActivityStream("run-test", "product_manager")
    stream._publish = lambda kind, message, metadata=None: published.append(
        (kind, message, metadata)
    )
    return stream, published


def test_each_message_and_tool_call_becomes_one_event():
    from types import SimpleNamespace

    stream, published = _captured_stream()
    stream.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(text="I will read the brief.")]]))
    stream.on_tool_start({"name": "write_artifact"}, '{"relative_path": "docs/x.md"}')
    stream.on_tool_end("wrote 4kb")
    stream.on_tool_error(RuntimeError("nope"))

    assert [p[0] for p in published] == [
        "agent_message", "tool_call", "tool_result", "tool_result",
    ]
    assert "write_artifact" in published[1][1]
    assert published[3][2] == {"failed": True}


def test_a_long_message_is_clipped_before_it_reaches_the_dashboard():
    """This is a UI feed, not a record: the full text is already in the model's
    context and, for tool output, in the journal."""
    from types import SimpleNamespace

    from app.server.agent_stream import MAX_TEXT

    stream, published = _captured_stream()
    stream.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(text="x" * 10_000)]]))

    assert len(published[-1][1]) < MAX_TEXT + 200


def test_a_malformed_response_does_not_raise_into_the_agents_turn():
    """Narration must never fail the run it was narrating."""
    from types import SimpleNamespace

    from app.server.agent_stream import build_activity_callbacks

    stream, published = _captured_stream()
    stream.on_llm_end(SimpleNamespace())      # no `generations` at all

    assert published == []
    assert build_activity_callbacks(None, "any_stage") == []


@pytest.mark.asyncio
async def test_activity_reaches_the_same_history_the_dashboard_reads(bus):
    """The one test that would catch a wrong Redis key name.

    Every other agent-activity test stubs `_publish`, so none of them execute
    the write. `AgentActivityStream` writes through a *sync* Redis client with
    hand-built key names rather than through `EventBus`, because it runs on a
    worker thread with no event loop. If those names ever drift from
    `EventBus._history_key` / `_sequence_key`, nothing raises - the events are
    simply written somewhere nobody reads.
    """
    from types import SimpleNamespace

    from app.server.agent_stream import AgentActivityStream

    stream = AgentActivityStream("run-test", "product_manager")
    stream.on_llm_end(
        SimpleNamespace(generations=[[SimpleNamespace(text="Reading the brief.")]])
    )
    stream.on_tool_start({"name": "write_artifact"}, '{"relative_path": "docs/x.md"}')

    history = await bus.get_history("run-test")

    kinds = [e.event_type for e in history]
    assert kinds == ["agent_message", "tool_call"], kinds
    assert history[0].message == "Reading the brief."
    assert history[0].stage == "product_manager"
    # The counter is shared with EventBus, so the next bus publish must not
    # collide with a sequence the stream already used.
    assert [e.sequence for e in history] == [1, 2]
    assert (await bus.next_sequence("run-test")) == 3


@pytest.mark.asyncio
async def test_history_survives_a_record_written_by_an_older_schema(bus):
    """Removing a field must not make every stored event unreadable.

    `files_modified`, `tests_passed` and `tests_failed` were dropped from
    `RunEvent` while thousands of events carrying them sat in Redis. With
    `extra="forbid"` every one of them failed to parse, `get_history` raised,
    and the log view went blank for every existing run at once.
    """
    import json

    from app.server.redis_client import get_async_redis_client

    redis = get_async_redis_client()
    legacy = {
        "run_id": "run-test", "event_id": "e1", "sequence": 1,
        "timestamp": "2026-09-10T10:00:00+00:00", "stage": "product_manager",
        "event_type": "stage_change", "message": "Reading the brief.",
        "files_modified": 0, "tests_passed": 0, "tests_failed": 0,
        "metadata": {},
    }
    await redis.rpush("run:run-test:history", json.dumps(legacy))

    history = await bus.get_history("run-test")

    assert [e.message for e in history] == ["Reading the brief."]
    assert not hasattr(history[0], "files_modified")


@pytest.mark.asyncio
async def test_one_unreadable_record_does_not_lose_the_whole_page(bus):
    """A display feed should show 1 of 2 events rather than raise."""
    import json

    from app.server.redis_client import get_async_redis_client

    redis = get_async_redis_client()
    await redis.rpush("run:run-test:history", json.dumps({"not": "an event"}))
    await bus.publish("run-test", _event("run-test", 2, message="Still readable."))

    history = await bus.get_history("run-test")

    assert [e.message for e in history] == ["Still readable."]
