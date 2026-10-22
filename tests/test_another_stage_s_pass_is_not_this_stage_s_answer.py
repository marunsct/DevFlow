"""A command another stage passed is not withheld from this one.

The refusal says "you already have the answer, N copies of it". That is true of
passes this stage ran and false of passes another stage ran. One run's
`defect_fix_1_1` was told to reproduce its defect, asked for `npm test`, and was
refused because three earlier stages had passed it - output it had never seen.
It spent some twenty calls hunting for that output.
"""

from __future__ import annotations

import pytest

from app.tools import sandbox
from app.tools.sandbox import _record_execution, succeeded_this_way_before

COMMAND = ["npm", "test"]


@pytest.fixture
def running_as(monkeypatch):
    def set_stage(name: str) -> None:
        monkeypatch.setattr(
            "app.observability.transcript._stage_from_config", lambda fallback: name
        )
    return set_stage


def _passes(root, n: int) -> None:
    for _ in range(n):
        _record_execution(str(root), "testing_specialist", COMMAND, {"returncode": 0})


def test_other_stages_passes_do_not_count(tmp_path, running_as):
    running_as("test_round_0")
    _passes(tmp_path, 3)

    running_as("defect_fix_1_1")

    assert succeeded_this_way_before(str(tmp_path), COMMAND) == 0


def test_this_stage_s_own_passes_still_count(tmp_path, running_as):
    """The waste the rule exists for: one stage re-running a green command."""
    running_as("test_round_0")
    _passes(tmp_path, 3)

    assert succeeded_this_way_before(str(tmp_path), COMMAND) == 3


def test_the_stage_is_recorded(tmp_path, running_as):
    running_as("defect_fix_1_1")
    _passes(tmp_path, 1)

    assert sandbox.read_execution_ledger(str(tmp_path))[-1]["stage"] == "defect_fix_1_1"


def test_outside_a_run_every_pass_counts(tmp_path, running_as):
    running_as("")
    _passes(tmp_path, 2)

    assert succeeded_this_way_before(str(tmp_path), COMMAND) == 2
