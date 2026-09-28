"""The repeated-read ladder must count the stage it says it counts.

Reading a file that has not changed since this stage last read it gets a ladder
of four rungs: a notice at 2, the content withheld at 3, the two ways out of the
stage named at 6, and the read refused at 12. The first two read their counts out
of `stage_memory`. The upper two read a plain attribute on the backend object,
while their own words say "the {n}th time this stage has asked for content it
already has".

Measured on one run. 110 reads had their content withheld and the two upper
rungs fired zero times - not once in a run of 262 tool calls. Every withholding
calls `_the_way_out`, which returns text as soon as the tally reaches 6, so the
tally was under 6 on all 110 occasions. `specialist_testing_2` alone read one
`package.json` fifteen times, byte-identical, with the same offset and limit, and
was withheld thirteen of them; a tally that survived those thirteen would have
passed 6 and then 12. It never passed 5.

The backend is constructed with the agent, so an attribute on it does not live as
long as the stage. The digest maps beside it already go through `store` for
exactly this reason. Now the tally does too, and the upper rungs are reachable.

Not a change to any threshold. The thresholds were chosen against measured runs;
what was broken was the counter they read.
"""

from __future__ import annotations

import tempfile

import pytest

from app.agents import stage_memory
from app.agents.workspace_backend import (
    REPEATED_READS_BEFORE_NAMING_THE_EXIT,
    REPEATED_READS_BEFORE_REFUSING,
    WorkspaceBackend,
)


@pytest.fixture
def a_root():
    return tempfile.mkdtemp()


@pytest.fixture
def in_one_stage(monkeypatch):
    """Pin `current_stage_key`, as a graph run does."""
    monkeypatch.setattr(
        stage_memory, "current_stage_key", lambda: ("thread-1", "specialist_testing_2")
    )


def _backend(root):
    return WorkspaceBackend(root_dir=root, virtual_mode=True)


class TestTheTallySurvivesTheBackend:
    def test_a_rebuilt_backend_keeps_this_stage_s_count(self, a_root, in_one_stage):
        """The whole fault: the object is rebuilt and the stage is not."""
        first = _backend(a_root)
        for _ in range(4):
            first._count_a_repeated_read()

        assert _backend(a_root)._repeated_reads_so_far() == 4

    def test_the_exit_rung_becomes_reachable_across_rebuilds(self, a_root, in_one_stage):
        """One run's `specialist_testing_2`, in miniature."""
        for _ in range(REPEATED_READS_BEFORE_NAMING_THE_EXIT):
            _backend(a_root)._count_a_repeated_read()

        assert _backend(a_root)._the_way_out() != ""

    def test_the_refusal_rung_becomes_reachable_too(self, a_root, in_one_stage):
        for _ in range(REPEATED_READS_BEFORE_REFUSING):
            _backend(a_root)._count_a_repeated_read()

        refusal = _backend(a_root)._refuse_a_read_that_returns_nothing_new("app.js")

        assert "Refusing to read" in refusal

    def test_the_count_in_the_message_is_the_stage_s_count(self, a_root, in_one_stage):
        """A message naming the object's count would understate the waste."""
        for _ in range(REPEATED_READS_BEFORE_REFUSING + 3):
            _backend(a_root)._count_a_repeated_read()

        refusal = _backend(a_root)._refuse_a_read_that_returns_nothing_new("app.js")

        assert f"{REPEATED_READS_BEFORE_REFUSING + 3}th time" in refusal


class TestStillCountingTheRightThing:
    def test_below_the_threshold_nothing_is_said(self, a_root, in_one_stage):
        for _ in range(REPEATED_READS_BEFORE_NAMING_THE_EXIT - 1):
            _backend(a_root)._count_a_repeated_read()
        backend = _backend(a_root)

        assert backend._the_way_out() == ""
        assert backend._refuse_a_read_that_returns_nothing_new("app.js") == ""

    def test_a_different_stage_starts_at_nothing(self, a_root, monkeypatch):
        """A stage must not inherit the last one's impatience."""
        monkeypatch.setattr(
            stage_memory, "current_stage_key", lambda: ("thread-1", "specialist_ui_ux_0")
        )
        for _ in range(REPEATED_READS_BEFORE_REFUSING):
            _backend(a_root)._count_a_repeated_read()

        monkeypatch.setattr(
            stage_memory, "current_stage_key", lambda: ("thread-1", "specialist_ui_ux_1")
        )

        assert _backend(a_root)._repeated_reads_so_far() == 0

    def test_a_different_thread_starts_at_nothing(self, a_root, monkeypatch):
        """Two runs execute at once in this worker and share the process."""
        monkeypatch.setattr(
            stage_memory, "current_stage_key", lambda: ("thread-A", "specialist_testing_1")
        )
        for _ in range(REPEATED_READS_BEFORE_REFUSING):
            _backend(a_root)._count_a_repeated_read()

        monkeypatch.setattr(
            stage_memory, "current_stage_key", lambda: ("thread-B", "specialist_testing_1")
        )

        assert _backend(a_root)._repeated_reads_so_far() == 0


class TestOutsideAGraphRun:
    def test_one_instance_still_counts_for_itself(self, a_root, monkeypatch):
        """`store` falls back to the instance dict, and that must keep working."""
        monkeypatch.setattr(stage_memory, "current_stage_key", lambda: None)
        backend = _backend(a_root)

        for _ in range(3):
            backend._count_a_repeated_read()

        assert backend._repeated_reads_so_far() == 3

    def test_a_fresh_instance_has_nothing_to_inherit(self, a_root, monkeypatch):
        """With no stage to key on there is nowhere to keep it, which is correct."""
        monkeypatch.setattr(stage_memory, "current_stage_key", lambda: None)
        _backend(a_root)._count_a_repeated_read()

        assert _backend(a_root)._repeated_reads_so_far() == 0


class TestTheThresholdsAreUnchanged:
    def test_the_ladder_still_has_its_measured_rungs(self):
        """The counter was broken, not the thresholds; changing them is a separate
        argument that needs its own evidence."""
        from app.agents.workspace_backend import (
            READS_BEFORE_WITHHOLDING,
            REPEATS_BEFORE_SAYING_SO,
        )

        assert REPEATS_BEFORE_SAYING_SO == 2
        assert READS_BEFORE_WITHHOLDING == 3
        assert REPEATED_READS_BEFORE_NAMING_THE_EXIT == 6
        assert REPEATED_READS_BEFORE_REFUSING == 12

    def test_the_rungs_are_in_order(self):
        """A ladder whose rungs crossed would skip one entirely."""
        from app.agents.workspace_backend import (
            READS_BEFORE_WITHHOLDING,
            REPEATS_BEFORE_SAYING_SO,
        )

        assert (
            REPEATS_BEFORE_SAYING_SO
            <= READS_BEFORE_WITHHOLDING
            < REPEATED_READS_BEFORE_NAMING_THE_EXIT
            < REPEATED_READS_BEFORE_REFUSING
        )
