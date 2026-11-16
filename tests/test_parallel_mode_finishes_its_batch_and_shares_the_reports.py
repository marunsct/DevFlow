"""Parallel mode finishes a fix batch it started, and its builders get the earlier work orders' reports (LR.15).

Found in the launch review: the parallel/linear mode is read at each visit of the fix node, so switching to linear
while a batch was in flight left `fix_batch` set and never cleared, and a later parallel visit re-entered it with old
indices in a new round; and the parallel work-order builder left out what earlier work orders reported about the
files it shares, which the linear builder gives.
"""
from __future__ import annotations

import inspect

from app.graph import workflow


def _graph_source() -> str:
    return inspect.getsource(workflow.build_workflow_graph)


def test_a_batch_in_flight_is_finished_whatever_the_mode_reads_now():
    source = _graph_source()
    at = source.index("return _the_next_fix_batch(state, config)")
    assert 'if _fixes_run_side_by_side() or state.get("fix_batch"):' in source[at - 200:at]


def test_both_builders_give_the_earlier_reports():
    source = _graph_source()
    assert source.count("ledger.with_the_reports(") == 2
    parallel = source[source.index("# What the work orders finished before it reported about its files"):]
    assert parallel.index("ledger.with_the_reports(") < parallel.index("where_things_stand.with_it(")
