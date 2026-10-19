"""The loop rewinds a run to the stage before a bug instead of starting it again (owner, 2026-10-20).

Tonight three gate runs were cancelled and started from scratch for bugs found
after the specification, and one findings run was cancelled 4 hours in; each
restart redid the intake, the consults, the specification and the suite - work
the fix did not touch. The harness could already rewind a run to the start of a
stage with its files as they were; the loop had no way to ask for it.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts" / "loop"

spec = importlib.util.spec_from_file_location("rewind_point", HERE / "rewind_point.py")
rewind_point = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rewind_point)

POINTS = {"points": [
    {"checkpoint_id": "c1", "stage": "principal_architect", "sprint": None, "at": "2026-10-19T21:04:23"},
    {"checkpoint_id": "c2", "stage": "test_and_triage", "sprint": 1, "at": "2026-10-19T22:21:30"},
    {"checkpoint_id": "c3", "stage": "defect_remediation", "sprint": 1, "at": "2026-10-19T22:21:34"},
    {"checkpoint_id": "c4", "stage": "test_and_triage", "sprint": 1, "at": "2026-10-19T22:24:13"},
]}


def test_the_latest_entry_of_the_stage_is_chosen():
    assert rewind_point.the_point(POINTS["points"], "test_and_triage")["checkpoint_id"] == "c4"


def test_a_time_chooses_the_last_entry_before_it():
    assert rewind_point.the_point(POINTS["points"], "test_and_triage", "2026-10-19T22:23")["checkpoint_id"] == "c2"


def test_a_stage_never_entered_has_no_point():
    assert rewind_point.the_point(POINTS["points"], "scaffold") is None


def test_the_script_prints_the_checkpoint_and_fails_loudly_without_one():
    run = lambda *args: subprocess.run([sys.executable, str(HERE / "rewind_point.py"), *args],
                                       input=json.dumps(POINTS), capture_output=True, text=True)
    found = run("principal_architect")
    assert found.returncode == 0 and found.stdout.strip() == "c1"
    missing = run("scaffold")
    assert missing.returncode == 1 and "test_and_triage" in missing.stderr


def test_loop_sh_has_the_command():
    text = (HERE / "loop.sh").read_text()
    assert "\nrewind)" in text and "rewind_point.py" in text and "/rewind-points" in text


def _call(at, stage="defect_fix_1_0"):
    return [
        {"at": at, "stage": stage, "kind": "model_request", "messages": [], "blocks": {}},
        {"at": at.replace(":00", ":05"), "stage": stage, "kind": "model_response", "usage": {"output_tokens": 10}},
    ]


def test_a_rewound_run_s_kpis_leave_out_the_work_the_rewind_discarded():
    """The transcript keeps the abandoned branch; a rewound run measured whole counts
    work twice - the stages done before the bug, and done again after it."""
    from app.observability.run_kpis import kpis, live_branch

    records = [
        *_call("2026-10-20T01:00:00+00:00", "principal_architect"),
        *_call("2026-10-20T02:00:00+00:00", "test_round_0"),
        *_call("2026-10-20T03:00:00+00:00", "defect_fix_1_0"),
        {"at": "2026-10-20T03:30:00+00:00", "stage": "test_and_triage", "kind": "rewound",
         "point_at": "2026-10-20T01:30:00+00:00"},
        *_call("2026-10-20T04:00:00+00:00", "test_round_0"),
    ]

    kept = live_branch(records)

    assert [r["stage"] for r in kept if r["kind"] == "model_request"] == ["principal_architect", "test_round_0"]
    assert kpis(records)["model_calls"] == 2
    assert kpis(records)["rewinds"] == 1


def test_a_run_never_rewound_is_measured_whole():
    from app.observability.run_kpis import live_branch

    records = [*_call("2026-10-20T01:00:00+00:00"), *_call("2026-10-20T02:00:00+00:00")]
    assert live_branch(records) == records


def test_the_loop_s_suite_runs_across_workers_when_it_can():
    """Measured: 64 s on 12 workers against 290 s on one, the same result; every fix waited on it."""
    text = (HERE / "loop.sh").read_text()
    suite = text[text.index("\nsuite)"):]
    assert "import xdist" in suite and '$workers' in suite and "-n ${SUITE_WORKERS:-12}" in suite
    assert "pytest-xdist" in (HERE.parents[1] / "pyproject.toml").read_text()


def test_the_defect_queue_shows_only_the_run_as_it_stands(tmp_path):
    """One gate run's re-plan showed as "attempt 3" while its record held two: the attempt
    a rewind discarded was still counted."""
    def raised(at, index, description):
        return {"at": at, "kind": "defect", "event": "raised", "sprint": 0, "index": index, "round": 0,
                "source": "test round", "owner": "backend", "description": description, "stage": "test_round_0"}

    records = [
        raised("2026-10-20T01:00:00+00:00", 0, "discarded by the rewind"),
        {"at": "2026-10-20T02:00:00+00:00", "kind": "rewound", "stage": "test_and_triage",
         "point_at": "2026-10-20T00:30:00+00:00"},
        raised("2026-10-20T03:00:00+00:00", 0, "the run as it stands"),
    ]
    (tmp_path / "run-x.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    import os

    shown = subprocess.run([sys.executable, str(HERE / "defects.py"), "run-x"], capture_output=True, text=True,
                           env={**os.environ, "TRANSCRIPTS_DIR": str(tmp_path),
                                "PYTHONPATH": str(HERE.parents[1] / "src")}).stdout

    assert "the run as it stands" in shown and "discarded by the rewind" not in shown
    assert "attempt 2" not in shown
