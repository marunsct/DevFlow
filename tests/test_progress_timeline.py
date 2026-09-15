"""The progress panel must describe the run that happened.

Three defects, all visible in one screenshot of a real run:

- It showed 8 of 17 stages. `stage_change` is published once per approval gate,
  so only gated stages appeared and all the planning and review were missing.
- It showed each gated stage twice, because `stage_change` carries the
  `awaiting_approval:` prefix and the UI strips it for display.
- It said "retried 66 times" for a run whose authoritative retry count was 2.
  A gated stage returns to itself after every approval, and each return was
  counted as a retry.

Stage names also recur every sprint, so an entry is only identifiable by
`(sprint, name)` - the same collision that inflated three separate measurements
of these runs before it was noticed here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.server.runs import _derive_stages


def _event(stage, kind="tool_call", at="2026-09-15T10:00:00+00:00", message=None):
    return SimpleNamespace(
        event_type=kind, stage=stage, message=message, timestamp=at, metadata={}
    )


def _at(second: int) -> str:
    return f"2026-09-15T10:{second // 60:02d}:{second % 60:02d}+00:00"


def test_every_stage_appears_not_only_the_gated_ones():
    """Planning and review emit no approvals and were invisible."""
    events = [
        _event("product_manager", at=_at(0)),
        _event("principal_architect", at=_at(10)),
        _event("technical_lead", at=_at(20)),
        _event("specialist_ui_ux_0", at=_at(30)),
        _event("milestone_review", at=_at(40)),
    ]

    names = [s["name"] for s in _derive_stages(events, None)]

    assert names == [
        "product_manager", "principal_architect", "technical_lead",
        "specialist_ui_ux_0", "milestone_review",
    ]


def test_a_pause_is_folded_into_the_stage_it_pauses():
    """Otherwise every gated stage renders twice under the same title."""
    events = [
        _event("specialist_ui_ux_1", at=_at(0)),
        _event("awaiting_approval:specialist_ui_ux_1", "stage_change", _at(1)),
        _event("awaiting_approval:specialist_ui_ux_1", "approval_auto", _at(2)),
        _event("specialist_ui_ux_1", at=_at(3)),
    ]

    stages = _derive_stages(events, None)

    assert len(stages) == 1
    assert stages[0]["name"] == "specialist_ui_ux_1"


def test_an_approval_is_not_a_retry():
    """The defect the screenshot showed: 66 approvals reported as 66 retries."""
    events = [_event("test_round_0", at=_at(0))]
    for n in range(1, 36):
        events.append(_event("awaiting_approval:test_round_0", "approval_auto", _at(n)))
        events.append(_event("test_round_0", at=_at(n)))

    stage = _derive_stages(events, None)[0]

    assert stage["approval_count"] == 35
    assert stage["retry_count"] == 0


def test_a_stage_re_entered_after_another_ran_is_a_retry():
    """The remediation loop: a test round that comes back after a defect fix."""
    events = [
        _event("test_round_0", at=_at(0)),
        _event("defect_fix_1_0", at=_at(10)),
        _event("test_round_0", at=_at(20)),
    ]

    rounds = [s for s in _derive_stages(events, None) if s["name"] == "test_round_0"]

    assert len(rounds) == 1
    assert rounds[0]["retry_count"] == 1


def test_stages_are_grouped_by_sprint():
    """`technical_lead` opens each sprint; what precedes the first is planning."""
    events = [
        _event("product_manager", at=_at(0)),
        _event("technical_lead", at=_at(10)),
        _event("specialist_backend_0", at=_at(20)),
        _event("milestone_review", at=_at(30)),
        _event("technical_lead", at=_at(40)),
        _event("specialist_backend_0", at=_at(50)),
    ]

    stages = _derive_stages(events, None)

    assert [(s["sprint"], s["name"]) for s in stages] == [
        (0, "product_manager"),
        (1, "technical_lead"),
        (1, "specialist_backend_0"),
        (1, "milestone_review"),
        (2, "technical_lead"),
        (2, "specialist_backend_0"),
    ]


def test_the_same_stage_in_two_sprints_is_two_rows():
    """Keyed by name alone they collapsed into one row whose duration and counts
    summed across sprints - the collision that inflated three separate
    measurements of these runs."""
    events = [
        _event("technical_lead", at=_at(0)),
        _event("test_round_0", at=_at(10)),
        _event("technical_lead", at=_at(20)),
        _event("test_round_0", at=_at(30)),
    ]

    rounds = [s for s in _derive_stages(events, None) if s["name"] == "test_round_0"]

    assert len(rounds) == 2
    assert [r["sprint"] for r in rounds] == [1, 2]
    assert all(r["retry_count"] == 0 for r in rounds), "a new sprint is not a retry"


def test_a_stage_ends_when_the_next_one_begins():
    events = [_event("product_manager", at=_at(0)), _event("tools_models", at=_at(90))]

    stages = _derive_stages(events, None)

    assert stages[0]["duration_seconds"] == 90
    assert stages[0]["status"] == "completed"
    assert stages[-1]["duration_seconds"] is None, "the last stage is still open"


def test_an_event_with_no_stage_is_ignored():
    assert _derive_stages([_event(None), _event("")], None) == []


def test_narration_comes_only_from_a_stage_change():
    """Other events carry tool payloads, which are not a description of the step."""
    events = [
        _event("test_round_0", "tool_call", _at(0), message="read_file: {...}"),
        _event("awaiting_approval:test_round_0", "stage_change", _at(1),
               message="Auto-approving: test_round_0"),
    ]

    assert _derive_stages(events, None)[0]["meaning"] == "Auto-approving: test_round_0"


def test_a_stage_with_no_narration_yet_is_still_valid():
    """`RunStage.meaning` is a string. Returning None for a stage whose first
    event is a tool call failed validation for every such stage and took the
    run-detail endpoint down with a 500."""
    from app.server.models import RunStage

    stages = _derive_stages([_event("product_manager", "tool_call", _at(0))], None)

    assert stages[0]["meaning"] == ""
    RunStage(**stages[0])  # must not raise


def test_narration_arriving_later_is_kept():
    events = [
        _event("test_round_0", "tool_call", _at(0)),
        _event("awaiting_approval:test_round_0", "stage_change", _at(1),
               message="Auto-approving: test_round_0"),
        _event("test_round_0", "tool_call", _at(2)),
    ]

    assert _derive_stages(events, None)[0]["meaning"] == "Auto-approving: test_round_0"


def test_every_derived_stage_validates():
    """The endpoint builds RunStage from each of these; one bad row is a 500."""
    from app.server.models import RunStage

    events = [
        _event("product_manager", "tool_call", _at(0)),
        _event("technical_lead", "agent_message", _at(10)),
        _event("awaiting_approval:test_round_0", "approval_auto", _at(20)),
        _event("test_round_0", "tool_result", _at(30)),
    ]

    for row in _derive_stages(events, None):
        RunStage(**row)
