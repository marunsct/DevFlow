"""`stage_duration_seconds` is labelled with the stage, not with its pause.

Item 2 of plan-part3 wired `record_stage_duration` at "the points that already
know the answer". The point it chose is the gate loop, and the gate loop only
ever sees a *paused* stage value: the graph runs its nodes internally and
returns at an interrupt, so `state["stage"]` there reads
`awaiting_approval:specialist_ui_ux_0`, never `specialist_ui_ux_0`.

Measured live on 2026-09-21, read out of the shared multiprocess store::

    stage_duration_seconds_sum{stage="awaiting_approval:specialist_ui_ux_0"} 78.5

So a dashboard grouping by `stage` gets one series per *pause*, and the names an
operator would search for never appear. `_derive_stages` folds a pause into its
parent for exactly this reason - its docstring opens "A pause is not a stage" -
and the histogram was the one reader that did not.

This also records the gap the fix does **not** close: a stage that never pauses
is never observed at all.
"""

from __future__ import annotations

import pytest

from app.graph.workflow import APPROVAL_PAUSE_PREFIX, REVIEW_PAUSE_PREFIX
from app.server.runner import _the_stage_itself


class TestThePauseIsStripped:
    @pytest.mark.parametrize(
        ("paused", "expected"),
        [
            ("awaiting_approval:specialist_ui_ux_0", "specialist_ui_ux_0"),
            ("awaiting_approval:product_manager", "product_manager"),
            ("awaiting_user_review:test_round_0", "test_round_0"),
        ],
    )
    def test_a_paused_stage_reports_its_own_name(self, paused, expected):
        assert _the_stage_itself(paused) == expected

    def test_it_uses_the_prefixes_the_workflow_defines(self):
        """Hard-coding the strings here would drift from the graph's own."""
        assert _the_stage_itself(f"{APPROVAL_PAUSE_PREFIX}x") == "x"
        assert _the_stage_itself(f"{REVIEW_PAUSE_PREFIX}y") == "y"


class TestEverythingElseIsUntouched:
    @pytest.mark.parametrize(
        "stage", ["technical_lead", "test_round_0", "complete", "failed", ""]
    )
    def test_an_unpaused_stage_passes_through(self, stage):
        assert _the_stage_itself(stage) == stage

    def test_a_stage_whose_name_merely_contains_the_word_is_untouched(self):
        """Only a prefix is a pause; a colon elsewhere is part of the name."""
        assert _the_stage_itself("review:something") == "review:something"


class TestTheRecorderUsesIt:
    def test_the_duration_is_recorded_under_the_stripped_name(self, monkeypatch):
        import app.server.runner as runner_module

        seen: list[tuple[str, float]] = []
        monkeypatch.setattr(
            runner_module.MetricsTracker,
            "record_stage_duration",
            staticmethod(lambda stage, seconds: seen.append((stage, seconds))),
        )
        runner_module._record_stage_duration(
            {"stage": "awaiting_approval:specialist_ui_ux_0", "started_at": 0.0}
        )
        assert seen and seen[0][0] == "specialist_ui_ux_0", seen

    def test_an_empty_timing_records_nothing(self, monkeypatch):
        import app.server.runner as runner_module

        seen: list = []
        monkeypatch.setattr(
            runner_module.MetricsTracker,
            "record_stage_duration",
            staticmethod(lambda stage, seconds: seen.append(stage)),
        )
        runner_module._record_stage_duration({})
        assert seen == []


class TestTheRemainingGapIsRecorded:
    def test_the_docstring_says_what_is_still_not_timed(self):
        """A stage that never pauses is never observed.

        Run 2's `tools_models`, `principal_architect`, `architecture_review`,
        `scrum_master` and `technical_lead` all completed without taking an
        approval, and produced no observation. Someone reading this histogram
        must know it counts gated stages only; a partial measurement presented
        as a complete one is the defect plan-part3 §3.1 is about.
        """
        import re

        flat = re.sub(r"\s+", " ", _the_stage_itself.__doc__ or "")
        assert "never pauses is never observed" in flat
