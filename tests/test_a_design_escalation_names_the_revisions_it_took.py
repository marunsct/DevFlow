"""A design escalation names the number of revisions the run took, not the full limit (harness review D8).

Measured: fast delivery escalates after two revisions, and the escalation said "after 6 revisions" - the full limit -
in every record the owner and the release read.
"""
from __future__ import annotations

import inspect

from app.graph import workflow


def test_the_escalation_counts_the_revisions_it_stopped_at():
    source = inspect.getsource(workflow)
    start = source.index("The architecture reviewer still asked for changes to the specification")
    said = source[start:start + 300]
    assert "{revision_count} revision" in said
    assert "MAX_ARCHITECTURE_REVISIONS" not in said
