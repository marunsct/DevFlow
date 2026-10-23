"""`loop.sh scan` names a stage that spends far more than the recent runs did, so a suggestion comes without a failure.

Measured on one run: the acceptance author wrote its suite in 14 calls of 17,000 tokens where earlier
runs used 1,000-2,000 a call, and two audits filed it as the model's behaviour because nothing failed.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("scan_under_test", ROOT / "scripts" / "loop" / "scan.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)

START = datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc)


def _run(directory: Path, name: str, stages: dict[str, tuple[int, int]], minutes_each: int = 5) -> str:
    """A transcript: stage -> (calls, output tokens a call)."""
    path = directory / f"{name}.jsonl"
    moment, lines = START, []
    for stage, (calls, tokens) in stages.items():
        for _ in range(calls):
            moment += timedelta(minutes=minutes_each)
            lines.append(json.dumps({"at": moment.isoformat(), "stage": stage, "kind": "model_response",
                                     "usage": {"output_tokens": tokens}}))
    path.write_text("\n".join(lines))
    return str(path)


def test_a_stage_far_over_the_recent_runs_is_named_with_what_to_try(tmp_path):
    paths = [_run(tmp_path, f"run-old{n}", {"acceptance_author_0": (20, 1500), "principal_architect": (10, 6000)}) for n in range(3)]
    paths.append(_run(tmp_path, "run-now", {"acceptance_author_0": (14, 17_000), "principal_architect": (10, 6500)}))

    lines = scan.scan(paths, "run-now")

    assert len(lines) == 1
    assert lines[0].startswith("IMPROVEMENT acceptance_author: 17,000 tokens a call against 1,500 in 3 recent run(s)")
    assert "WB.2" in lines[0]


def test_a_run_like_the_recent_ones_has_nothing_to_report(tmp_path):
    paths = [_run(tmp_path, f"run-old{n}", {"principal_architect": (10, 6000)}) for n in range(3)]
    paths.append(_run(tmp_path, "run-now", {"principal_architect": (10, 7000)}))

    assert scan.scan(paths, "run-now") == []


def test_a_very_long_reply_is_named_even_with_nothing_to_compare(tmp_path):
    paths = [_run(tmp_path, "run-now", {"stack_setup_0": (3, 45_000)})]

    lines = scan.scan(paths, "run-now")

    assert len(lines) == 1 and "longest reply 45,000 tokens" in lines[0] and "ask what in the request" in lines[0]


def test_a_small_run_is_no_baseline(tmp_path):
    paths = [_run(tmp_path, "run-tiny", {"acceptance_author_0": (3, 100)}),
             _run(tmp_path, "run-now", {"acceptance_author_0": (5, 9_000)})]

    assert scan.scan(paths, "run-now") == []
