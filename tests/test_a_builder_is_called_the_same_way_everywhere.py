"""A builder called from two places must be called the same way from both.

`build_specialist_task_request` has two call sites: `specialist_node`, which runs
delegated tasks one at a time, and `specialist_worker_node`, the parallel path.
The shared-file note added earlier was wired into the first and not the second -
and parallel is the mode that is enabled, and the mode where specialists really
do run at once, so it is the one where a file two tasks share matters most.

The note therefore never fired in production. Found by auditing one run:
its plan named `app.js` in four of six delegated tasks, five stages wrote
`app.js`, and not one brief mentioned the overlap. The helper had passed its own
tests the whole time, because they called it directly.

This is the general form. Two call sites of one builder that disagree about
their keyword arguments is a fix that works down one path and not the other,
which is invisible from either the unit tests or the diff.

A genuine difference is allowed by naming it below, so the escape hatch is
explicit rather than silent.
"""

from __future__ import annotations

import ast
import collections
import inspect
import pathlib

import pytest

#: Builders whose call sites legitimately differ, with the reason. Empty is the
#: state to keep: an entry here is a claim that two paths should behave
#: differently, and it should be hard to add.
_ALLOWED_TO_DIFFER: dict[str, str] = {}


def _call_sites():
    source = pathlib.Path(
        inspect.getsourcefile(__import__("app.graph.workflow", fromlist=["x"]))
    ).read_text()
    tree = ast.parse(source)
    sites = collections.defaultdict(list)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", "")
        if not name.startswith("build_"):
            continue
        sites[name].append(
            (node.lineno, tuple(sorted(k.arg for k in node.keywords if k.arg)))
        )
    return sites


class TestEveryBuilderIsCalledConsistently:
    def test_no_two_call_sites_disagree(self):
        offenders = []
        for name, rows in _call_sites().items():
            if len(rows) < 2 or name in _ALLOWED_TO_DIFFER:
                continue
            shapes = {keywords for _, keywords in rows}
            if len(shapes) > 1:
                offenders.append((name, rows))

        assert not offenders, "\n".join(
            f"{name} is called differently from "
            + ", ".join(f"line {line} with {list(kw)}" for line, kw in rows)
            for name, rows in offenders
        )

    def test_the_specialist_builder_has_two_sites_and_both_pass_the_siblings(self):
        """The case this was written for, pinned by name."""
        rows = _call_sites()["build_specialist_task_request"]

        assert len(rows) == 2, rows
        for _, keywords in rows:
            assert "other_tasks" in keywords

    def test_the_allowance_list_is_empty(self):
        """An entry is a claim that two paths should behave differently."""
        assert _ALLOWED_TO_DIFFER == {}, _ALLOWED_TO_DIFFER

    def test_the_check_can_see_the_call_sites(self):
        """A parser that finds nothing would pass every assertion above."""
        sites = _call_sites()

        assert sites, "no build_* call sites found - the parser is looking in the wrong place"
        assert "build_specialist_task_request" in sites
