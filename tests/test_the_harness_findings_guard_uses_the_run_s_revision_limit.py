"""A harness finding's revision guard uses the run's own revision limit (harness review HR2.D.4).

The guards compared with the full limit (6) while fast delivery escalates at two, so a harness finding first raised
on fast delivery's last revision passed its guard and escalated unrevised.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph import workflow


def test_in_fast_delivery_the_last_revision_raises_no_new_harness_finding(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_fast_delivery", lambda: True)
    state = {"architecture_revision_count": 1,
             "product_intake": SimpleNamespace(success_measures=["A person can export every note as a file"])}
    assert workflow._a_success_measure_the_specification_drops(state, "A notes service.") is None


def test_the_full_limit_still_holds_outside_fast_delivery(monkeypatch) -> None:
    monkeypatch.setattr(workflow, "_fast_delivery", lambda: False)
    assert workflow._the_revision_limit() == workflow.MAX_ARCHITECTURE_REVISIONS


class _Read(dict):
    """A state that records every key a check reads."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read: set[str] = set()

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)


@pytest.mark.parametrize("check", [
    lambda state: workflow._a_success_measure_the_specification_drops(state, "A notes service."),
    # Two lines of one command whose results differ by the order of its options: raised past its guard.
    lambda state: workflow._the_same_command_in_another_order(state, (
        "- AC-4 command python -m wordstats <file> --top N --json -> stdout {}, exit 0\n"
        "- AC-9 command python -m wordstats <file> --json --top N -> stdout [], exit 0\n")),
    lambda state: workflow._contract_lines_nothing_can_read(state),
    lambda state: workflow._a_brief_feature_the_specification_defers(state, "A notes service."),
    lambda state: workflow._behaviour_the_specification_gives_kept_files(state, "A notes service."),
], ids=["coverage", "command-order", "contract-lines", "deferrals", "kept-files"])
def test_no_guard_compares_with_the_full_limit_directly(check, monkeypatch) -> None:
    """On fast delivery's last revision every harness finding stops at its guard, before it reads the work."""
    from app.acceptance import interface_contract

    monkeypatch.setattr(workflow, "_fast_delivery", lambda: True)
    monkeypatch.setattr(interface_contract.unread_at_review_switch, "enabled", lambda: True)
    state = _Read(architecture_revision_count=1)

    assert check(state) is None
    assert state.read <= {"architecture_revision_count"} | {k for k in state.read if k.endswith("_checked")}, state.read
