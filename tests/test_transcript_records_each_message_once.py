"""A model request carries the whole conversation; the record kept every copy.

Measured on run-ed05e20e mid-run: a 36.6 MB transcript, of which 279
`model_request` entries were 33.4 MB. 91% of the record was text already in
it, and the file grows with the SQUARE of a stage's length. Across the stored
runs the directory had reached 490 MB.

Recording only what each request added keeps every message exactly once and
keeps the conversation reconstructible: `carried` says how many earlier
messages the request resent unchanged.

The two things that must not break, both tested here: a compaction that
rewrites history falls back to the whole conversation, because a delta
against a history that moved would be a lie; and a full copy is written every
so often, so a chain broken by a crash or a rotation self-heals instead of
leaving the rest of the stage unreadable.
"""

from __future__ import annotations

import pytest

from app.observability import transcript
from app.observability.transcript import (
    FULL_CONVERSATION_EVERY,
    MAX_CONVERSATIONS_TRACKED,
    _only_what_is_new,
)


@pytest.fixture(autouse=True)
def _forget_conversations():
    transcript._RECORDED_PREFIX.clear()
    yield
    transcript._RECORDED_PREFIX.clear()


def _grown(n: int) -> list[dict]:
    return [{"role": "human", "content": f"m{i}"} for i in range(n)]


def test_the_first_request_records_everything():
    assert _only_what_is_new("r", "s", _grown(3)) == (_grown(3), 0)


def test_a_later_request_records_only_what_it_added():
    _only_what_is_new("r", "s", _grown(3))

    added, carried = _only_what_is_new("r", "s", _grown(5))

    assert added == _grown(5)[3:]
    assert carried == 3


def test_every_message_is_recorded_exactly_once():
    """The property that makes the record still complete."""
    seen: list[dict] = []
    for length in range(1, 12):
        added, carried = _only_what_is_new("r", "s", _grown(length))
        assert carried == len(seen)
        seen.extend(added)

    assert seen == _grown(11)


def test_a_rewritten_history_records_the_whole_conversation():
    """Compaction replaces earlier messages; a delta against it would lie."""
    _only_what_is_new("r", "s", _grown(6))

    compacted = [{"role": "human", "content": "summary of the above"}]
    added, carried = _only_what_is_new("r", "s", compacted)

    assert added == compacted
    assert carried == 0


def test_a_changed_message_is_not_treated_as_a_prefix():
    _only_what_is_new("r", "s", _grown(3))

    edited = _grown(4)
    edited[1] = {"role": "human", "content": "changed"}
    added, carried = _only_what_is_new("r", "s", edited)

    assert carried == 0
    assert added == edited


def test_a_full_copy_is_written_regularly():
    """So a chain broken by a crash self-heals within a bounded window."""
    lengths = list(range(1, FULL_CONVERSATION_EVERY + 4))
    fulls = 0
    for length in lengths:
        _, carried = _only_what_is_new("r", "s", _grown(length))
        if carried == 0:
            fulls += 1

    assert fulls >= 2, "the first, and at least one refresh"


def test_two_stages_do_not_share_a_prefix():
    _only_what_is_new("r", "stage-a", _grown(4))

    added, carried = _only_what_is_new("r", "stage-b", _grown(2))

    assert carried == 0
    assert added == _grown(2)


def test_what_it_tracks_is_bounded():
    """A worker process runs many stages and this must not grow with them."""
    for n in range(MAX_CONVERSATIONS_TRACKED + 10):
        _only_what_is_new("r", f"stage-{n}", _grown(2))

    assert len(transcript._RECORDED_PREFIX) <= MAX_CONVERSATIONS_TRACKED


def test_no_run_id_records_everything():
    """Outside a run there is nothing to key on, so nothing is trimmed."""
    assert _only_what_is_new(None, "s", _grown(3)) == (_grown(3), 0)


def test_the_conversation_length_is_still_knowable(tmp_path, monkeypatch):
    """`carried + len(messages)` is what the model saw, and it is recorded."""
    written: list[dict] = []
    monkeypatch.setattr(
        transcript, "record", lambda run_id, stage, kind, **fields: written.append(fields)
    )

    callback = transcript.build_transcript_callback("r", "s")
    callback.on_chat_model_start({}, [_grown(3)])
    callback.on_chat_model_start({}, [_grown(5)])

    assert written[0]["carried"] + len(written[0]["messages"]) == 3
    assert written[1]["carried"] + len(written[1]["messages"]) == 5
