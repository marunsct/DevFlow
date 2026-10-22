"""Run metrics reduced from the transcript, not held in a second table.

Item 4 of Part III of the hardening plan (`docs/improvement-plan.md §E1`). Part I's §3.5 proposes a
`run_metrics` table holding tool calls by kind, failure rate, repeat rate and
latency. All of it is already in `DATA_DIR/transcripts/<run_id>.jsonl`, which
is written post-middleware, never raises, and is the one observability
component in this repository that has always worked.

A table would give the harness two records of the same facts and no way to tell
which is right when they disagree - the two-copies-drift mistake the codebase
already made with run state.

The classification matters more than the counts. A refusal is the harness
stopping something bad, and counting it as a failure makes the number this
exists to drive down rise whenever a guard works. `scripts/audit_run.py` had
exactly that defect: six of one run's eight "costly failures" were guards,
and correcting it moved that run from 1.2% to 0.3%.
"""

from __future__ import annotations

import json

import pytest

from app.observability.transcript_metrics import (
    PREVENTED_DAMAGE,
    transcript_metrics,
)

ROWS = [
    {"kind": "model_request", "stage": "specialist_ui_ux_0"},
    {"kind": "tool_call", "stage": "specialist_ui_ux_0", "tool": "read_file",
     "call_id": "a", "args": {"file_path": "app.js"}},
    {"kind": "tool_result", "call_id": "a", "content": "contents"},
    # A repeat: same stage, same tool, same arguments.
    {"kind": "tool_call", "stage": "specialist_ui_ux_0", "tool": "read_file",
     "call_id": "b", "args": {"file_path": "app.js"}},
    {"kind": "tool_result", "call_id": "b", "content": "contents"},
    # A guard firing. Prevented damage, never a cost.
    {"kind": "tool_call", "stage": "specialist_ui_ux_0", "tool": "write_artifact",
     "call_id": "c", "args": {}},
    {"kind": "tool_result", "call_id": "c",
     "content": '{"error": "Refusing to write \'a.mjs\': Node cannot parse this file"}'},
    # A genuine failure.
    {"kind": "model_request", "stage": "test_round_0"},
    {"kind": "tool_call", "stage": "test_round_0", "tool": "edit_artifact",
     "call_id": "d", "args": {}},
    {"kind": "tool_result", "call_id": "d",
     "content": '{"error": "Could not find that text in \'app.js\'."}'},
]


@pytest.fixture
def metrics(monkeypatch):
    monkeypatch.setattr(
        "app.observability.transcript.read_transcript",
        lambda run_id, kinds=None: ROWS,
    )
    return transcript_metrics("run-1")


def test_it_counts_what_ran(metrics):
    assert metrics["model_calls"] == 2
    assert metrics["tool_calls"] == 4
    assert metrics["tool_calls_by_kind"] == {
        "read_file": 2, "write_artifact": 1, "edit_artifact": 1
    }


def test_a_guard_is_prevented_damage_and_not_a_failure(metrics):
    assert metrics["refusals_that_prevented_damage"] == 1
    assert metrics["failures_that_cost_the_run"] == 1
    assert metrics["failure_rate"] == 0.25


def test_an_identical_call_in_one_stage_is_a_repeat(metrics):
    assert metrics["identical_repeats_in_a_stage"] == 1


def test_the_same_call_in_two_stages_is_not_a_repeat(monkeypatch):
    rows = [
        {"kind": "tool_call", "stage": "one", "tool": "ls", "call_id": "x", "args": {}},
        {"kind": "tool_call", "stage": "two", "tool": "ls", "call_id": "y", "args": {}},
    ]
    monkeypatch.setattr(
        "app.observability.transcript.read_transcript", lambda r, kinds=None: rows
    )
    assert transcript_metrics("run-1")["identical_repeats_in_a_stage"] == 0


def test_the_costly_shapes_are_named_with_numbers_generalised(metrics):
    shapes = metrics["costly_failure_shapes"]
    assert len(shapes) == 1
    assert shapes[0]["tool"] == "edit_artifact"
    assert shapes[0]["count"] == 1


def test_stages_are_counted_from_model_calls(metrics):
    assert metrics["stages"] == 2
    assert metrics["model_calls_by_stage"]["specialist_ui_ux_0"] == 1


class TestItNeverFailsTheRunItMeasures:
    def test_a_missing_transcript_gives_zeros(self, monkeypatch):
        def explode(*args, **kwargs):
            raise FileNotFoundError("no transcript")

        monkeypatch.setattr("app.observability.transcript.read_transcript", explode)

        out = transcript_metrics("run-nothing")

        assert out["model_calls"] == 0
        assert out["failure_rate"] == 0.0
        assert out["run_id"] == "run-nothing"

    def test_an_empty_transcript_does_not_divide_by_zero(self, monkeypatch):
        monkeypatch.setattr(
            "app.observability.transcript.read_transcript", lambda r, kinds=None: []
        )
        out = transcript_metrics("run-empty")
        assert out["failure_rate"] == 0.0 and out["repeat_rate"] == 0.0


class TestTheMarkersAreRealPhrases:
    """A fragment that stops matching moves a guard into the cost column."""

    def test_every_marker_is_emitted_by_a_tool(self):
        import inspect
        import re

        from app.analysis import javascript_parse
        from app.tools import repository, sandbox

        source = "".join(
            inspect.getsource(m) for m in (repository, sandbox, javascript_parse)
        )
        joined = re.sub(r'"\s*\n\s*"', "", source)

        missing = [mark for mark in PREVENTED_DAMAGE if mark not in joined]
        assert not missing, f"no tool emits these any more: {missing}"

    def test_the_sandbox_refusals_are_covered(self):
        for fragment in (
            "Not running this again",
            "it runs until it is stopped",
            "installs system packages as root",
        ):
            assert fragment in PREVENTED_DAMAGE


def test_it_reduces_a_real_transcript(tmp_path, monkeypatch):
    """End to end over a file, in the shape the harness actually writes."""
    path = tmp_path / "run-real.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in ROWS) + "\n")
    monkeypatch.setenv("DATA_DIR", str(tmp_path.parent))
    monkeypatch.setattr(
        "app.observability.transcript.transcript_path", lambda run_id: path
    )

    out = transcript_metrics("run-real")

    assert out["tool_calls"] == 4
    assert out["refusals_that_prevented_damage"] == 1
