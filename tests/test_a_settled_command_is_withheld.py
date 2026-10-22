"""A command that has already passed three times is withheld, not run again.

`succeeded_this_way_before` has appended a note since the leak it documents was
first measured. This run showed the note is not enough on its own.

`defect_fix_1_0`, live on 2026-09-21, ran::

    wc -l task-manager/index.html task-manager/style.css task-manager/app.js

eleven times, with exactly one write before the first of them. The note fired
correctly on calls four through eleven and counted up as it went - "already
passed 1 time(s)", "2 time(s)", ... "8 time(s)" - and the stage ran the command
again after each one. Eight notices, eight ignored.

So it escalates the way `aeb1e3a` escalated a repeated *read*: notice first,
withhold when the notice is not heeded. A write re-arms the command, which is
what keeps a genuine edit-test loop working.
"""

from __future__ import annotations

import json

import pytest

from app.tools.sandbox import SUCCESSES_BEFORE_WITHHOLDING


def test_three_is_the_threshold_reads_use():
    """Kept in step with the read path deliberately; drifting apart is confusing."""
    assert SUCCESSES_BEFORE_WITHHOLDING == 3


class TestTheWithholdingIsWired:
    def test_the_executor_checks_before_running(self):
        """After the fact it is a note; the point is to not run the command."""
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        withhold = source.index("SUCCESSES_BEFORE_WITHHOLDING and not")
        run_call = source.index("outcome = cls._run(")
        assert withhold < run_call, "the check must come before the command runs"

    def test_it_says_how_many_times_and_why(self):
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        block = source[source.index("Not running this again. It has already passed"):][:900]
        assert "nothing has been written since" in block, "name the guard"
        assert "change a file first" in block, "name the way out"

    def test_it_names_that_the_notice_was_ignored(self):
        """An agent that ignored eight notices needs to know why this is different."""
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        block = source[source.index("Not running this again. It has already passed"):][:900]
        assert "withheld rather than repeated" in block


class TestItDoesNotBreakLegitimateLoops:
    def test_a_search_command_is_excluded(self):
        """`_ran_and_answered` marks a grep whose exit 1 means "no match".

        Those already have their own note, and withholding a search would be a
        different and worse behaviour.
        """
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        assert "_ran_and_answered(" in source[
            source.index("SUCCESSES_BEFORE_WITHHOLDING and not") :
        ][:200]

    def test_the_guard_is_written_since_not_a_raw_count(self):
        """A write must re-arm the command, or an edit-test loop would stall.

        `succeeded_this_way_before` is the function that carries the
        "nothing written since" rule; the threshold is applied to its result
        rather than to a naive tally kept here.
        """
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        line = next(
            l for l in source.splitlines() if "settled = " in l and "succeeded_this_way_before" in l
        )
        assert "succeeded_this_way_before" in line


class TestTheRefusalIsRecorded:
    def test_a_withheld_command_still_reaches_the_ledger(self):
        """A stage that was stopped is different from one that never tried.

        The ledger is what `refused_this_way_before` and the audit script read;
        a withheld command that left no trace would be invisible to both.
        """
        import inspect

        from app.tools import sandbox

        source = inspect.getsource(sandbox)
        block = source[source.index("withheld rather than repeated") :][:600]
        assert "_record_execution(" in block
