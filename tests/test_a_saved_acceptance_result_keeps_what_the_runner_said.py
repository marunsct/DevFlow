"""A suite run that wrote no report is saved with what its runner said.

Measured live: the saved result read "the runner wrote no report; its output is
below" and held no output - the cause, Node failing to start its worker threads,
was found only by running the command again by hand.
"""
from __future__ import annotations

import json

from app.acceptance import suite
from app.acceptance.junit import Report


def test_the_saved_result_carries_the_runner_s_output(tmp_path):
    result = suite.AcceptanceResult(
        ran=False, exit_code=133, command="npm run test:acceptance", report=Report(),
        output="# Fatal process out of memory: Failed to reserve virtual memory for CodeRange",
        problem="the runner wrote no report; its output is below",
    )

    saved = json.loads(json.dumps(result.as_dict()))

    assert "Failed to reserve virtual memory for CodeRange" in saved["output"]
