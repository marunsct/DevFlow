"""A later sprint undid fixes earlier sprints had made, by building to the specification.

Measured on one run: sprint 1 darkened three colours the specification gave,
for contrast. Sprint 3's restyle wrote one back; sprint 4's work order - "fix
all responsive and styling issues in styles.css to match the technical
specification" - wrote all three back. Each time the regression check, the test
round, code review and the page check raised the same failures again and fixers
made the same changes again. Nothing told a builder, or the lead writing its
work order, that the specification's values had been found wanting.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents.specialists import build_specialist_task_request, fixes_to_keep_section
from app.sprint.record import MAX_FIXES_TO_KEEP, fixes_to_keep

STYLES = "simple-app/styles.css"


def _row(description: str, *, state: str = "fixed, verified", files=(STYLES,), owner: str = "ui_ux",
         resolution: str = "Changed the colour from #999999 to #555555") -> dict:
    return {"description": description, "state": state, "files": list(files), "owner": owner, "resolution": resolution}


def _attempts(*rows: dict) -> list[dict]:
    return [{"sprint_index": 0, "defect_log": list(rows)}]


class TestWhichFixesAreKept:
    def test_a_fix_in_the_work_order_s_files(self):
        kept = fixes_to_keep(_attempts(_row("The empty state's text fails contrast")), files=["styles.css"], role="backend")

        assert kept == ["The empty state's text fails contrast - fixed: Changed the colour from #999999 to #555555"]

    def test_a_fix_in_other_files_is_not_this_work_order_s(self):
        kept = fixes_to_keep(_attempts(_row("x", files=["simple-app/app.js"])), files=[STYLES], role="ui_ux")

        assert kept == []

    def test_a_fix_naming_no_file_goes_to_its_owner_s_role(self):
        rows = _attempts(_row("for ui", files=()), _row("for backend", files=(), owner="backend"))

        assert fixes_to_keep(rows, files=["index.html"], role="ui_ux") == [
            "for ui - fixed: Changed the colour from #999999 to #555555"
        ]

    def test_an_open_defect_is_no_fix(self):
        assert fixes_to_keep(_attempts(_row("x", state="open"))) == []

    def test_the_same_defect_twice_is_listed_once(self):
        assert len(fixes_to_keep(_attempts(_row("x"), _row("x")))) == 1

    def test_without_files_or_role_every_fix_is_kept(self):
        rows = _attempts(_row("a"), _row("b", files=["simple-app/app.js"], owner="backend"))

        assert len(fixes_to_keep(rows)) == 2

    def test_the_latest_are_kept_when_there_are_many(self):
        rows = _attempts(*(_row(f"defect {n}") for n in range(MAX_FIXES_TO_KEEP + 3)))

        kept = fixes_to_keep(rows)

        assert len(kept) == MAX_FIXES_TO_KEEP
        assert kept[-1].startswith(f"defect {MAX_FIXES_TO_KEEP + 2}")


class TestWhatTheBuilderIsTold:
    def test_the_fix_outranks_the_specification(self):
        text = fixes_to_keep_section(["The empty state fails contrast - fixed: #555555"])

        assert "--- Fixed earlier - keep these fixes ---" in text
        assert "Where the specification or your work order says otherwise, the fix stands" in text
        assert "- The empty state fails contrast - fixed: #555555" in text

    def test_nothing_fixed_says_nothing(self):
        assert fixes_to_keep_section([]) == ""

    def test_it_reaches_the_request(self, tmp_path):
        request = build_specialist_task_request(
            "Restyle the page for phones", ["AC-16: works on phones"], str(tmp_path),
            earlier_fixes=["The empty state fails contrast - fixed: #555555"],
        )

        assert "--- Fixed earlier - keep these fixes ---" in request["messages"][0]["content"]

    def test_the_words_name_no_product(self):
        text = fixes_to_keep_section(["x"]).lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text), word


class TestTheWorkflowReadsTheRecord:
    def test_a_work_order_gets_the_fixes_in_its_files(self):
        from app.graph.workflow import _the_fixes_to_keep

        state = {"sprint_attempts": _attempts(_row("The empty state fails contrast"))}
        order = SimpleNamespace(files=[STYLES], specialist_role="ui_ux")

        assert _the_fixes_to_keep(state, order) == [
            "The empty state fails contrast - fixed: Changed the colour from #999999 to #555555"
        ]

    def test_the_lead_gets_them_all(self):
        from app.graph.workflow import _the_fixes_to_keep

        state = {"sprint_attempts": _attempts(_row("a"), _row("b", files=["x.js"], owner="backend"))}

        assert len(_the_fixes_to_keep(state)) == 2

    def test_a_run_with_no_record_has_none(self):
        from app.graph.workflow import _the_fixes_to_keep

        assert _the_fixes_to_keep({}, SimpleNamespace(files=[STYLES], specialist_role="ui_ux")) == []


class TestWhatAReviewIsTold:
    """With builders and the lead told, the fixes survived a revision - and the UI
    advice review reported both as departures from the adopted advice, which the
    milestone review carried as findings."""

    def test_a_difference_a_fix_made_is_no_finding(self):
        from app.graph.workflow import _fixes_a_review_must_not_undo

        text = _fixes_a_review_must_not_undo({"sprint_attempts": _attempts(_row("The empty state fails contrast"))})

        assert "--- Fixed earlier - keep these fixes ---" in text
        assert "A difference from the specification or from adopted advice that one of these fixes made is not a finding" in text

    def test_nothing_fixed_says_nothing(self):
        from app.graph.workflow import _fixes_a_review_must_not_undo

        assert _fixes_a_review_must_not_undo({}) == ""

    def test_the_words_name_no_product(self):
        from app.graph.workflow import _fixes_a_review_must_not_undo

        text = _fixes_a_review_must_not_undo({"sprint_attempts": _attempts(_row("x"))}).lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text), word
