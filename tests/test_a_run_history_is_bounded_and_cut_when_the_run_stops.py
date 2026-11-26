"""A run's event history in Redis is bounded while live and cut when the run stops (LF.1507).

Measured on the owner's machine: the Redis the queue shares under `noeviction` held 299 MB of run histories, up to
5,000 events (5.9 MB) each, kept 30 days whether the run was live or long finished; 81% of it was agent activity that
nothing reads after a run. A full Redis refuses the queue's own writes.
"""

from __future__ import annotations

import json
import os

import pytest
import redis

from app.server import agent_stream, event_history
from app.server.events import EventBus, RunEvent
from app.server.run_store import RunRecord, RunStore

DAY = 24 * 3600


def _client(db: int | None = None) -> redis.Redis:
    """The test Redis; with `db`, an emptied database of its own, so a scan sees only this test's histories."""
    url = os.environ["REDIS_URL"]
    if db is None:
        return redis.Redis.from_url(url, decode_responses=True)
    client = redis.Redis.from_url(f"{url.rsplit('/', 1)[0]}/{db}", decode_responses=True)
    client.flushdb()
    return client


@pytest.fixture
def bus(redis_container):
    from app.server.redis_client import reset_clients

    reset_clients()
    client = _client()
    for key in client.scan_iter(match="run:run-history-*"):
        client.delete(key)
    return EventBus()


def _event(run_id: str, sequence: int, event_type: str, message: str = "working") -> RunEvent:
    return RunEvent(run_id=run_id, sequence=sequence, stage="developer", event_type=event_type, message=message)


async def _publish_by_bus(bus: EventBus, run_id: str, sequence: int, message: str) -> None:
    await bus.publish(run_id, _event(run_id, sequence, "tool_result", message))


async def _publish_by_worker(bus: EventBus, run_id: str, sequence: int, message: str) -> None:
    assert agent_stream.publish_one(run_id, "developer", "tool_result", message)


@pytest.mark.parametrize("publish", [_publish_by_bus, _publish_by_worker], ids=["event bus", "worker stream"])
async def test_appending_past_the_byte_cap_keeps_only_the_latest_events(bus, monkeypatch, publish):
    """An item cap alone let one run hold 5.9 MB: large tool results fill few items."""
    monkeypatch.setattr(event_history, "MAX_BYTES", 3_500)  # room for two events of ~1.3 KB, not three
    run_id = "run-history-bytes"
    for i in range(1, 9):
        await publish(bus, run_id, i, f"m{i}:" + "x" * 1_000)

    history = await bus.get_history(run_id)

    assert [event.message.split(":")[0] for event in history] == ["m7", "m8"]


async def test_a_stopped_run_keeps_its_structure_and_its_last_activity_for_the_finished_ttl(bus, monkeypatch):
    """The timeline and wizard of a finished run are built from its structural events; the bulk is agent activity."""
    monkeypatch.setattr(event_history, "FINISHED_ACTIVITY_KEPT", 3)
    run_id = "run-history-stopped"
    sequence = 0

    async def put(event_type: str, message: str) -> None:
        nonlocal sequence
        sequence += 1
        await bus.publish(run_id, _event(run_id, sequence, event_type, message))

    await put("stage_change", "intake")
    for i in range(10):
        await put("tool_call", f"call {i}")
    await put("review_decision", "approved")
    assert agent_stream.publish_one(run_id, "developer", "log", "written by the worker stream")
    for i in range(10):
        await put("agent_message", f"reply {i}")
    await put("complete", "done")

    await bus.close(run_id)

    history = await bus.get_history(run_id)
    assert [(event.event_type, event.message) for event in history] == [
        ("stage_change", "intake"),
        ("review_decision", "approved"),
        ("log", "written by the worker stream"),
        ("agent_message", "reply 7"),
        ("agent_message", "reply 8"),
        ("agent_message", "reply 9"),
        ("complete", "done"),
    ]
    client = _client()
    for key in (f"run:{run_id}:history", f"run:{run_id}:seq"):
        assert 13 * DAY < client.ttl(key) <= 14 * DAY, key


def _left_by_the_old_writer(client: redis.Redis, run_id: str, activity: int) -> None:
    """A history as the writer before the cut left it: every event, a 30-day TTL, no byte count."""
    key = f"run:{run_id}:history"
    events = [{"run_id": run_id, "sequence": 1, "stage": "intake", "event_type": "stage_change", "message": "start"}]
    events += [
        {"run_id": run_id, "sequence": 2 + i, "stage": "developer", "event_type": "tool_result", "message": "y" * 900}
        for i in range(activity)
    ]
    client.rpush(key, *(json.dumps(event) for event in events))
    client.expire(key, 30 * DAY)
    client.set(f"run:{run_id}:seq", len(events), ex=30 * DAY)


@pytest.fixture
def rows(setup_db):
    """Run rows with the statuses given; removed afterwards, since a `running` row counts against every slot."""
    saved: list[str] = []

    def _row(run_id: str, status: str) -> None:
        RunStore.shared().save(
            RunRecord(run_id=run_id, thread_id=run_id, document_names=[], document_paths=[], status=status)
        )
        saved.append(run_id)

    yield _row
    for run_id in saved:
        RunStore.shared().delete(run_id)


def test_the_worker_start_sweep_cuts_stopped_runs_and_leaves_live_ones(rows, monkeypatch):
    """The histories left before the cut existed were 299 MB; the sweep cuts every one whose run is not live."""
    monkeypatch.setattr(event_history, "FINISHED_ACTIVITY_KEPT", 2)
    client = _client(14)
    rows("run-history-finished", "completed")
    rows("run-history-live", "running")
    for run_id in ("run-history-finished", "run-history-live", "run-history-no-row"):
        _left_by_the_old_writer(client, run_id, activity=40)

    outcome = event_history.sweep(client)

    assert {run_id: client.llen(f"run:{run_id}:history") for run_id in
            ("run-history-finished", "run-history-live", "run-history-no-row")} == {
        "run-history-finished": 3, "run-history-live": 41, "run-history-no-row": 3}
    assert client.ttl("run:run-history-finished:history") <= 14 * DAY
    assert client.ttl("run:run-history-live:history") > 29 * DAY
    assert outcome["looked"] == 3 and outcome["cut"] == 2
    assert outcome["freed_bytes"] > 2 * 37 * 900


def test_a_history_with_less_time_left_than_the_finished_ttl_keeps_it(redis_container):
    """The cut never lengthens a history's life."""
    client = _client(13)
    _left_by_the_old_writer(client, "run-history-old", activity=5)
    client.expire("run:run-history-old:history", 2 * DAY)

    event_history.cut(client, "run-history-old")

    assert 0 < client.ttl("run:run-history-old:history") <= 2 * DAY


def test_the_ready_line_says_how_much_the_histories_hold(redis_container):
    client = _client(12)
    for run_id in ("run-history-a", "run-history-b"):
        _left_by_the_old_writer(client, run_id, activity=1_200)

    line = event_history.memory_line(client)

    assert line.startswith("REDIS run histories: 2 lists holding ")
    held_mb = float(line.split("holding ")[1].split(" MB")[0])
    assert held_mb >= 2
