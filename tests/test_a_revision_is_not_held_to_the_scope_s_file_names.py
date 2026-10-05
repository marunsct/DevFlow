"""A revision plan is not sent back for a file name the sprint's first plan built under another name.

One run's sprint scope named `pure-functions.mjs`; the first plan built that
logic as `app.mjs`. The revision after the milestone review, answering an XSS
finding, was sent back twice for not listing `pure-functions.mjs`.
"""

from __future__ import annotations

import inspect

from app.graph import workflow


def test_the_scope_check_applies_to_a_sprint_s_first_plan_only() -> None:
    source = inspect.getsource(workflow)
    call = source[source.index("problems = readiness_problems("):]
    call = call[: call.index(")\n")]
    assert 'sprint_scope="" if revising else _what_this_sprint_builds(state)' in call


def test_an_empty_scope_names_no_file(tmp_path) -> None:
    from app.analysis.work_orders import _files_the_sprint_names_and_nobody_is_given

    assert _files_the_sprint_names_and_nobody_is_given("", [], tmp_path, "") == []
