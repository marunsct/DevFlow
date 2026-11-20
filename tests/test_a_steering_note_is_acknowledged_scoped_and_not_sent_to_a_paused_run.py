"""A steering note says when it was read, can be for one stage, and is refused on a paused run (plan item AS).

The owner's note reached the end of the system prompt and nothing said so: no
acknowledgement, no scope, and a box shown on a run that was paused. Each note
now has an id, a scope (the run, or the one stage that first reads it), a record
the first time it reaches a call. The endpoint refused a note while the run was
paused; since plan WS.3 a paused run keeps it, shown as waiting, for when it
resumes (`test_a_steering_note_says_who_read_it_and_can_be_changed_until_then`).
"""
from __future__ import annotations

import json
import re

import pytest

from app.observability import transcript
from app.server import steering

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RUN_TRANSCRIPT", "true")


def test_a_note_has_an_id_and_a_scope(tmp_path):
    first = steering.add(tmp_path, "Keep the sign-in page.", "owner")
    second = steering.add(tmp_path, "Only this stage: skip the docs.", "owner", scope="next_stage")

    assert (first["id"], first["scope"]) == ("N-1", "run")
    assert (second["id"], second["scope"]) == ("N-2", "next_stage")
    with pytest.raises(ValueError):
        steering.add(tmp_path, "x", "owner", scope="forever")


def test_the_first_call_that_reads_a_note_is_recorded(tmp_path):
    steering.add(tmp_path, "Keep the sign-in page.", "owner")

    steering.as_instructions(tmp_path, "defect_fix_2_9", "run-s")
    steering.as_instructions(tmp_path, "defect_fix_2_9", "run-s")  # a second call: no second record

    sent = [e for e in transcript.read_transcript("run-s", {"steering_applied"})]
    assert len(sent) == 1 and sent[0]["note_id"] == "N-1" and sent[0]["stage"] == "defect_fix_2_9"
    note = steering.notes(tmp_path)[0]
    assert note["applied_stage"] == "defect_fix_2_9" and note["applied_at"]


def test_a_note_for_one_stage_is_dropped_when_the_next_stage_starts(tmp_path):
    steering.add(tmp_path, "Only this stage.", "owner", scope="next_stage")
    steering.add(tmp_path, "For the run.", "owner")

    in_first = steering.as_instructions(tmp_path, "defect_fix_1", "run-s")
    in_second = steering.as_instructions(tmp_path, "defect_fix_2", "run-s")

    assert "Only this stage." in in_first and "For the run." in in_first
    assert "Only this stage." not in in_second and "For the run." in in_second


def test_the_injected_words_use_none_of_the_banned_ones(tmp_path):
    steering.add(tmp_path, "Keep it simple.", "owner")

    assert not BANNED.search(steering.as_instructions(tmp_path, "s", "r"))


def test_the_run_s_figures_count_the_notes_that_reached_a_call(tmp_path):
    from app.observability.run_kpis import kpis

    steering.add(tmp_path, "Keep the sign-in page.", "owner")
    steering.add(tmp_path, "Only this stage.", "owner", scope="next_stage")
    steering.as_instructions(tmp_path, "defect_fix_1", "run-s")
    steering.as_instructions(tmp_path, "defect_fix_2", "run-s")

    assert kpis(transcript.read_transcript("run-s"))["steering_notes"] == 2


def test_a_stage_s_model_call_reads_the_note_as_that_stage_of_that_run(tmp_path, monkeypatch):
    from a_role_agent import the_first_request

    from app.tracing import APP_RUN_ID_KEY, APP_STAGE_KEY

    steering.add(tmp_path, "Keep the sign-in page.", "owner")

    sent = the_first_request(
        tmp_path, monkeypatch, configurable={APP_RUN_ID_KEY: "run-s", APP_STAGE_KEY: "defect_fix_2_9"},
    )

    assert "Keep the sign-in page." in sent[0].text
    [applied] = transcript.read_transcript("run-s", {"steering_applied"})
    assert (applied["note_id"], applied["stage"]) == ("N-1", "defect_fix_2_9")
