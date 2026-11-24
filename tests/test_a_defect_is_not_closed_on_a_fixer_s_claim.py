"""A defect is fixed only on a measurement; a fix that changed nothing is never fixed (LF.1260, review item 1.3).

Measured on one 24-hour run: all nine defects closed as "fixed" carried "(no passing command recorded)"; seven were
about routes that answered 404 the whole time; one was closed with "changed routers/users.py" from a fixer that made
no write, with nothing committed. That phantom "fixed" ended the start-break note, so the nine fixers after it were
not told which change stops the product starting, and the tenth made it again and was reverted the same way.

Each test drives the fix stage through its node, with only the agent and the product's measurement (which runs the
product) stood in for; the workspace's history is real.
"""
from __future__ import annotations

import re

import pytest

from app import ci
from app.agents import start_breaks
from app.agents.shared_facts import the_facts_section
from app.agents.specialists import SpecialistOutput
from app.graph import engineering
from app.observability import defect_ledger

THE_START_ERROR = "The product did not start ... TypeError: responder must be async"
AC_3_PASSES = {f"tests/acceptance/ac-3.spec.ts{ci.WHERE}AC-3 signs a user up": "passed"}
#: The fix stage's own `after_a_fix`, captured before `a_fix_stage` stands it in for.
REAL_AFTER_A_FIX = engineering.after_a_fix


@pytest.fixture
def ledger(monkeypatch):
    noted: list[tuple[str, str]] = []
    monkeypatch.setattr(defect_ledger, "note", lambda event, stage, **kw: noted.append((event, kw.get("detail", ""))))
    return noted


def _the_fix_stage(tmp_path, monkeypatch, defect, *, writes: bool, acceptance: dict[str, str] | None = None,
                   said: list[str] = ("app/users.py",)):
    """`defect_remediation` on `defect`: the fixer says it changed `said`; `writes` is whether a file really changed;
    the measurement after the fix has the product starting, with `acceptance` as its suite's outcomes."""
    from workflow_nodes import a_fix_stage

    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "users.py").write_text("ROUTES = []\n")
    base = ci.commit(tmp_path, "base")
    ci.save(tmp_path, ci.Snapshot(label="before defect_fix_2_0", commit=base))
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "take", lambda root, label, **kw: ci.Snapshot(
        label=label, acceptance=dict(acceptance or {}), acceptance_ran=bool(acceptance)))
    if writes:
        (tmp_path / "app" / "users.py").write_text("ROUTES = ['/users']\n")
    update, _ = a_fix_stage(
        tmp_path, [defect], answer=SpecialistOutput(changed_files=list(said), tests=["tests/users.test.js"]),
        patches={"app.graph.engineering.before_a_fix": lambda *args: base,
                 "app.graph.engineering.after_a_fix": REAL_AFTER_A_FIX},
    )
    return update["remediation"].defects[0]


def _a_route_defect():
    from workflow_nodes import a_defect

    return a_defect("The users route answers 404", affected_files=["app/users.py"])


def _a_criterion_defect():
    from workflow_nodes import a_defect

    return a_defect("[AC-3] Signing up answers 404", affected_files=["app/users.py"], failing_criteria=["AC-3"])


def test_a_fix_nothing_measures_is_left_open_as_unverified(tmp_path, monkeypatch, ledger):
    defect = _the_fix_stage(tmp_path, monkeypatch, _a_route_defect(), writes=True)

    assert defect.status == "open"
    assert defect.attempts[-1]["outcome"].startswith("unverified")
    assert [event for event, _ in ledger if event in ("fixed", "unverified")] == ["unverified"]


def test_a_fix_stage_that_changed_no_file_is_left_open_whatever_it_says_it_changed(tmp_path, monkeypatch, ledger):
    defect = _the_fix_stage(tmp_path, monkeypatch, _a_criterion_defect(), writes=False, acceptance=AC_3_PASSES)

    assert defect.status == "open"
    assert defect.attempts[-1]["outcome"] == "left open: nothing was changed"
    (detail,) = [detail for event, detail in ledger if event == "left open"]
    assert "nothing was changed" in detail and "app/users.py" in detail


def test_a_defect_whose_own_tests_pass_after_a_change_is_fixed_as_before(tmp_path, monkeypatch, ledger):
    defect = _the_fix_stage(tmp_path, monkeypatch, _a_criterion_defect(), writes=True, acceptance=AC_3_PASSES)

    assert defect.status == "fixed"
    assert defect.attempts[-1]["outcome"] == "fixed"


@pytest.mark.parametrize("defect, writes, acceptance", [
    (_a_route_defect, True, None),               # unverified: nothing measures it
    (_a_criterion_defect, False, AC_3_PASSES),   # changed nothing
], ids=["unverified", "changed nothing"])
def test_the_start_break_note_outlives_a_fix_that_was_not_measured_or_changed_nothing(
        tmp_path, monkeypatch, ledger, defect, writes, acceptance):
    start_breaks.record(tmp_path, "defect_fix_1_0", THE_START_ERROR)

    _the_fix_stage(tmp_path, monkeypatch, defect(), writes=writes, acceptance=acceptance)

    assert "TypeError: responder must be async" in the_facts_section(tmp_path)


def test_a_kept_fix_measured_with_the_product_starting_ends_the_start_break_note(tmp_path, monkeypatch, ledger):
    start_breaks.record(tmp_path, "defect_fix_1_0", THE_START_ERROR)

    _the_fix_stage(tmp_path, monkeypatch, _a_criterion_defect(), writes=True, acceptance=AC_3_PASSES)

    assert the_facts_section(tmp_path) == ""


def _an_unverified_defect():
    from workflow_nodes import a_defect

    return a_defect("The users route answers 404", attempts=[
        {"stage": "defect_fix_1_0", "files": ["app/users.py"], "did": "", "outcome":
         "unverified: nothing the harness measures shows it gone; the next test round decides"}])


def test_a_test_round_that_finds_nothing_wrong_closes_an_unverified_defect(tmp_path, ledger):
    from workflow_nodes import a_test_round

    from app.sprint import RemediationCycle

    update, _ = a_test_round(tmp_path, (), state={
        "remediation": RemediationCycle(sprint_goal="g", defects=[_an_unverified_defect()])})

    assert update["remediation"].defects[0].status == "fixed"
    assert "closed by the round's measurement" in [event for event, _ in ledger]


def test_a_test_round_that_finds_something_leaves_an_unverified_defect_open(tmp_path, ledger):
    from workflow_nodes import a_test_round, reported

    from app.sprint import RemediationCycle

    update, _ = a_test_round(tmp_path, [reported("Deleting a note answers 500")], state={
        "remediation": RemediationCycle(sprint_goal="g", defects=[_an_unverified_defect()])})

    assert update["remediation"].defects[0].status == "open"


def test_what_the_next_fixer_reads_of_such_an_attempt_avoids_the_banned_words():
    """The attempt's outcome is shown to the next fixer (`ledger.earlier_attempts`)."""
    from app.sprint import NOTHING_WAS_CHANGED, UNVERIFIED

    for text in (UNVERIFIED, NOTHING_WAS_CHANGED):
        for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
            assert not re.search(rf"\b{re.escape(word)}\b", text, re.I)
