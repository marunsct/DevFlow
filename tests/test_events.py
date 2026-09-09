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
