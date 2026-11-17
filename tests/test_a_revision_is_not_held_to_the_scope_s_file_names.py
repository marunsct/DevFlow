"""A revision plan is not sent back for a file name the sprint's first plan built under another name.

One run's sprint scope named `pure-functions.mjs`; the first plan built that
logic as `app.mjs`. The revision after the milestone review, answering an XSS
finding, was sent back twice for not listing `pure-functions.mjs`.
"""

from __future__ import annotations



def test_the_scope_check_applies_to_a_sprint_s_first_plan_only(tmp_path) -> None:
    from workflow_nodes import a_lead, a_plan, a_work_order

    plan = a_plan(a_work_order("frontend", "build the page", ["app.mjs"]))

    _, first = a_lead(tmp_path, plan)
    _, revision = a_lead(tmp_path, plan, state={"milestone_plan": plan,
                                               "revision_comments": ["Escape the note's title before showing it."]})

    assert "Add a note" in first["readiness"][0]["sprint_scope"]
    assert revision["readiness"][0]["sprint_scope"] == ""


def test_an_empty_scope_names_no_file(tmp_path) -> None:
    from app.analysis.work_orders import _files_the_sprint_names_and_nobody_is_given

    assert _files_the_sprint_names_and_nobody_is_given("", [], tmp_path, "") == []
