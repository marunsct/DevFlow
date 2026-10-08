"""A code review finding becomes a defect only when a test or a check shows it.

A reviewer reads a diff and can be wrong. Measured on one run: "the form submit
handler does not sanitize user input" - on a page that renders with
`textContent` - became a defect; its fixer escaped the input before storing it,
and the page then showed "&amp;" where a user typed "&": a real bug made by
fixing an unreal one. Another finding said a test command's flags were in the
wrong order; they were not, and a fix stage was spent finding that out.

What nothing shows is advice for the milestone review, not a defect to fix.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app import ci
from app.graph.engineering import what_shows_it


def _finding(problem: str, file: str = "app/src/app.js", fix: str = ""):
    return SimpleNamespace(problem=problem, fix=fix, file=file, work_order="Build the form", severity="blocking")


def _state(root, **extra):
    return {"repository": SimpleNamespace(root_path=str(root)), **extra}


class TestWhatShowsAFinding:
    def test_nothing_shows_an_opinion(self, tmp_path):
        assert what_shows_it(_state(tmp_path), _finding("The form handler does not sanitize user input")) == ""

    def test_a_failing_test_it_names(self, tmp_path):
        ci.save(tmp_path, ci.Snapshot(label="after the work orders", unit={"t › escapes the heading": "failed"}, unit_ran=True))

        why = what_shows_it(_state(tmp_path), _finding("escapes the heading twice, so `escapes the heading` fails"))

        assert "escapes the heading" in why

    def test_a_passing_test_it_names_shows_nothing(self, tmp_path):
        ci.save(tmp_path, ci.Snapshot(label="after the work orders", unit={"t › escapes the heading": "passed"}, unit_ran=True))

        assert what_shows_it(_state(tmp_path), _finding("`escapes the heading` is wrong")) == ""

    def test_an_underline_in_its_file(self, tmp_path):
        underlined = SimpleNamespace(source="language service", affected_files=["app/src/app.js"])

        why = what_shows_it(_state(tmp_path, review_defects=[underlined]), _finding("uses an undefined helper"))

        assert "underlines" in why

    def test_a_failing_criterion_due_now(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.graph.acceptance_nodes.criteria_due", lambda state: ["AC-2"])
        monkeypatch.setattr("app.graph.acceptance_nodes.criteria_failing_now", lambda state, text: ["AC-2"])

        assert "AC-2" in what_shows_it(_state(tmp_path), _finding("AC-2: removing does nothing"))


class TestTheMilestoneReviewHearsTheAdvice:
    def test_it_is_advice_not_a_defect(self):
        from app.graph.workflow import _the_code_review_s_advice

        text = _the_code_review_s_advice({"review_advice": ["app/src/app.js: does not sanitize input"]})

        assert "--- The code review's advice: no test or check shows these ---" in text
        assert "- app/src/app.js: does not sanitize input" in text
        assert "only if you can name what fails because of it" in text

    def test_no_advice_says_nothing(self):
        from app.graph.workflow import _the_code_review_s_advice

        assert _the_code_review_s_advice({}) == ""

    def test_the_words_name_no_product(self):
        from app.graph.workflow import _the_code_review_s_advice

        text = _the_code_review_s_advice({"review_advice": ["x"]}).lower()

        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text), word
