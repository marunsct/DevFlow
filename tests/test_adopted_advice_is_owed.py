"""Adopted specialist advice is owed work: scheduled in a sprint, checked when due, sent back once, then a gap.

Measured on one medium run (three sprints, thorough delivery). Sprint 2's database specialist found eight adopted
items not built and its security specialist three; each was recorded as a minor finding, the milestone review
accepted the sprint, the items were carried to the next lead, and the product shipped without them (SP.1). And the
UI/UX specialist found nothing in any sprint because none of its ten adopted items was ever due: every sprint put
the interface out of scope, and nothing checked that each adopted item was placed in some sprint (SP.2).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.agents.advice_review import (
    AdviceReview,
    as_sprint_findings,
    build_advice_review_request,
    findings_from,
    items_due,
    owed_and_not_built,
)
from app.agents.scrum_master import (
    SprintDefinition,
    SprintPlanOutput,
    advice_not_scheduled,
    build_sprint_planning_request,
    with_the_advice_scheduled,
)
from app.completion_verdict import is_blocking
from app.graph import workflow as workflow_module
from app.graph.workflow import start_workflow
from app.sprint.record import carried_from, with_dispositions
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _milestone,
    _milestone_review,
    _repository,
    _security_review,
    _spec,
    _specialist,
    agents,
    responds_with,
)

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")

ADVICE = {
    "ui_ux": ["Stack the form above the list below 600px.", "Confirm each change in a status line."],
    "database": ["Give every record a generated id."],
}
DECISIONS = ["UX-1: adopted - interface_design", "UX-2: adopted - interface_design", "DB-1: adopted - data_model"]
DB_1 = "[database specialist] not built: DB-1: notes are keyed by their position in the list"


def _plan(*placed: list[str], declined: list[str] | None = None) -> SprintPlanOutput:
    return SprintPlanOutput(
        sprints=[SprintDefinition(goal=f"Sprint {n}", user_value="v", advice=ids) for n, ids in enumerate(placed, 1)],
        advice_declined=declined or [],
    )


def _no_banned_word(text: str) -> None:
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", text.lower()), word


class TestAnItemFoundNotBuiltIsAGatingFinding:
    """SP.1: the Sprint Record held each specialist's items as one minor finding, carried and declinable."""

    def test_an_owed_item_is_major_and_gates_and_is_not_carried(self) -> None:
        findings = as_sprint_findings([DB_1], 1)

        [finding] = findings
        assert finding["severity"] == "major" and finding["gating"] is True
        assert "DB-1: notes are keyed by their position in the list" in finding["description"]
        assert with_dispositions(findings, completed=True, more_sprints=True)[0]["disposition"] == "open"
        assert carried_from(findings, 1) == []

    def test_a_design_line_beside_it_stays_minor_and_carried(self) -> None:
        findings = as_sprint_findings([DB_1, "[database specialist] design: the list reads poorly"], 1)

        assert [(f["severity"], f["gating"]) for f in findings] == [("major", True), ("minor", False)]

    def test_a_line_naming_an_item_not_due_is_left_out(self) -> None:
        answer = AdviceReview(not_built=["UX-2: no status line", "UX-1: no rule below 600px", "the page has no title"])

        assert findings_from("ui_ux", answer, ["UX-1"]) == [
            "[UI/UX specialist] not built: UX-1: no rule below 600px",
            "[UI/UX specialist] not built: the page has no title",
        ]


class TestEachItemIsSentBackOnce:
    def test_items_not_yet_sent_back_are_owed_now_and_the_rest_are_still_not_built(self) -> None:
        found = {
            "ui_ux": ["[UI/UX specialist] not built: UX-1: no rule below 600px",
                      "[UI/UX specialist] design: the phone screenshot scrolls sideways"],
            "database": [DB_1, "[database specialist] not built: DB-1: said again"],
        }

        now, still = owed_and_not_built(found, sent_back=["DB-1"])

        assert now == ["[UI/UX specialist] not built: UX-1: no rule below 600px"]
        assert still == [DB_1]

    def test_an_item_the_lead_declined_is_neither(self) -> None:
        assert owed_and_not_built({"database": [DB_1]}, declined=["DB-1"]) == ([], [])


def _accepted_with(monkeypatch, tmp_path, found: list[str], **state):
    from workflow_node_stubs import run_a_milestone_review

    return run_a_milestone_review(
        monkeypatch, tmp_path, sprint_plan=SimpleNamespace(sprints=[1, 2]),
        advice_review_cycle=f"0:{state.get('milestone_revision_count', 0)}", advice_findings={"database": found},
        overrides={
            "app.graph.workflow._a_red_suite_the_review_called_green": lambda state: "",
            "app.sprint.record.definition_of_done_gaps": lambda *a, **k: [],
            "app.tools.version_control.commit_milestone": lambda *a, **k: None,
        },
        **state,
    ).update


class TestTheMilestone:
    def test_an_accepted_sprint_with_an_owed_item_goes_back_to_the_lead_naming_it(self, monkeypatch, tmp_path) -> None:
        update = _accepted_with(monkeypatch, tmp_path, [DB_1])

        assert update["stage"] == "technical_lead" and update["milestone_revision_count"] == 1
        assert "DB-1: notes are keyed by their position in the list" in update["revision_comments"][-1]
        assert update["advice_sent_back"] == ["DB-1"]

    def test_found_again_after_its_send_back_it_is_an_open_gap_and_the_sprint_goes_on(self, monkeypatch, tmp_path) -> None:
        update = _accepted_with(monkeypatch, tmp_path, [DB_1], advice_sent_back=["DB-1"], milestone_revision_count=1)

        assert update["stage"] == "sprint_advance"
        [gap] = update["advice_open_gaps"]
        assert "(sprint 1)" in gap and "DB-1: notes are keyed by their position in the list" in gap
        recorded = [d for d in update["decisions"] if d["decision"] == "go on, recorded as an open gap"]
        assert len(recorded) == 1 and "DB-1: notes are keyed" in recorded[0]["rationale"]

    def test_with_no_revision_left_it_is_an_open_gap_rather_than_a_stop(self, monkeypatch, tmp_path) -> None:
        from app.graph.workflow import MAX_MILESTONE_REVISIONS

        update = _accepted_with(monkeypatch, tmp_path, [DB_1], milestone_revision_count=MAX_MILESTONE_REVISIONS - 1)

        assert update["stage"] == "sprint_advance" and len(update["advice_open_gaps"]) == 1

    def test_a_decline_with_a_reason_is_a_change_to_the_specification(self, monkeypatch, tmp_path) -> None:
        plan = SimpleNamespace(selected_sprint_goal="g", delegated_tasks=[], carried_forward_decisions=[],
                               review_task_assignments=["DB-1 -> declined: the brief numbers each note itself"])

        update = _accepted_with(monkeypatch, tmp_path, [DB_1], advice_sent_back=["DB-1"], milestone_revision_count=1,
                                milestone_plan=plan)

        assert update["stage"] == "sprint_advance" and not update.get("advice_open_gaps")
        assert list(update["advice_declined"]) == ["DB-1"]
        [change] = [d for d in update["decisions"] if d["decision"].startswith("decline ")]
        assert change["point"] == "technical_specification" and change["decision"] == "decline DB-1" and "the brief numbers each note itself" in change["rationale"]

    def test_a_decline_because_no_test_needs_it_declines_nothing(self, monkeypatch, tmp_path) -> None:
        plan = SimpleNamespace(selected_sprint_goal="g", delegated_tasks=[], carried_forward_decisions=[],
                               review_task_assignments=["DB-1 -> declined: not required by current sprint tests"])

        update = _accepted_with(monkeypatch, tmp_path, [DB_1], advice_sent_back=["DB-1"], milestone_revision_count=1,
                                milestone_plan=plan)

        assert not update.get("advice_declined") and len(update["advice_open_gaps"]) == 1

    def test_the_send_back_names_no_product(self, monkeypatch, tmp_path) -> None:
        _no_banned_word(_accepted_with(monkeypatch, tmp_path, [DB_1])["revision_comments"][-1])


def test_an_open_gap_reaches_the_release_as_a_note(tmp_path, monkeypatch) -> None:
    from app.analysis import integration_checks
    from app.graph import delivery

    monkeypatch.setattr(integration_checks, "problems_that_break_the_product", lambda root, stack=None, brief="": [])
    gap = "Adopted specialist advice still not built after its one send-back (sprint 2): " + DB_1

    update = delivery.release(
        {"repository": SimpleNamespace(root_path=str(tmp_path)), "advice_open_gaps": [gap]}, {"configurable": {}},
        SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(tmp_path), allow_subdirectories=True),
    )

    assert gap in update["completion_gaps"] and not is_blocking(gap)


class TestEveryAdoptedItemIsScheduled:
    """SP.2."""

    def test_an_item_in_no_sprint_and_not_declined_is_named(self) -> None:
        plan = _plan(["UX-1"], [], declined=["DB-1: declined - the brief numbers each note itself"])

        assert advice_not_scheduled(plan, ["UX-1", "UX-2", "DB-1"]) == ["UX-2"]

    def test_an_item_a_sprint_s_scope_names_is_placed(self) -> None:
        plan = SprintPlanOutput(sprints=[SprintDefinition(goal="g", user_value="v", in_scope=["Status line (UX-2)"])])

        assert advice_not_scheduled(plan, ["UX-2"]) == []

    def test_a_decline_with_no_reason_or_for_want_of_a_test_does_not_count(self) -> None:
        plan = _plan([], declined=["UX-1: declined", "UX-2: declined - not required by any test"])

        assert advice_not_scheduled(plan, ["UX-1", "UX-2"]) == ["UX-1", "UX-2"]

    def test_what_is_still_unplaced_goes_to_the_last_sprint(self) -> None:
        plan, notes = with_the_advice_scheduled(_plan(["UX-1"], ["DB-1"]), ["UX-2"])

        assert [s.advice for s in plan.sprints] == [["UX-1"], ["DB-1", "UX-2"]]
        assert notes and "UX-2" in notes[0]


class TestWhatIsDue:
    SPEC = SimpleNamespace(specialist_advice_decisions=DECISIONS)

    def test_by_a_sprint_the_items_placed_in_it_or_earlier(self) -> None:
        due, because = items_due(ADVICE, self.SPEC, "ui_ux", _plan(["UX-2"], ["UX-1"], []), 0)

        assert due == ["UX-2: Confirm each change in a status line."] and because

    def test_in_the_last_sprint_every_adopted_item_not_declined(self) -> None:
        due, _ = items_due(ADVICE, self.SPEC, "ui_ux", _plan(["UX-2"], [], []), 2, declined=["UX-2"])

        assert due == ["UX-1: Stack the form above the list below 600px."]

    def test_a_plan_that_places_none_leaves_the_specialist_to_judge(self) -> None:
        due, because = items_due(ADVICE, self.SPEC, "ui_ux", _plan([], []), 0)

        assert len(due) == 2 and because == ""

    def test_the_specialist_is_told_each_listed_item_is_due(self) -> None:
        text = build_advice_review_request("ui_ux", ["UX-2: x"], "g", "", [], due_because="the plan says so")[
            "messages"][0]["content"]

        assert "due now: the plan says so" in text and "each one is due now" in text


class TestThroughTheGraph:
    @staticmethod
    def _advised(agents, monkeypatch, *, reviewing: bool) -> None:
        from test_the_specialists_advise_before_the_specification import TestThroughTheGraph as Consulting

        from app.agents.specialist_advice import SpecialistAdvice

        Consulting._consulting(monkeypatch, agents, ["ui_ux"], reviewing=reviewing)
        Consulting._script_the_stack(agents)
        monkeypatch.setattr(workflow_module, "create_advice_reviewer_agent",
                            lambda role, *args, **kwargs: agents.agent(f"advice_reviewer_{role}"))
        agents.script("advisor_ui_ux", [responds_with(SpecialistAdvice(recommendations=ADVICE["ui_ux"]))])
        agents.script("principal_architect", [responds_with(_spec(
            interface_design=["Below 600px the form sits above the list."], specialist_advice_decisions=DECISIONS[:2],
        ))])
        agents.script("architecture_review", [responds_with(_approved_review())])
        agents.script("technical_lead", [responds_with(_milestone("testing"))] * 2)
        agents.script("specialist_testing", [responds_with(_specialist())] * 4)
        agents.script("milestone_reviewer", [responds_with(_milestone_review())] * 2)
        agents.script("security_reviewer", [responds_with(_security_review())] * 2)

    def test_a_plan_that_places_an_item_nowhere_is_sent_back_once_then_the_last_sprint_holds_it(
        self, agents, monkeypatch, tmp_path,
    ) -> None:
        self._advised(agents, monkeypatch, reviewing=False)
        agents.script("scrum_master", [responds_with(_plan(["UX-1"]))] * 2)

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-unplaced")

        first, again = (r["messages"][-1]["content"] for r in agents.requests["scrum_master"])
        assert "UX-2: Confirm each change in a status line." in first
        assert "YOUR LAST PLAN PLACED THESE IN NO SPRINT AND DECLINED NONE OF THEM: UX-2." in again
        assert state["sprint_plan"].sprints[-1].advice == ["UX-1", "UX-2"]
        assert "UX-2: Confirm each change in a status line." in agents.last_request_text("technical_lead")
        assert state["stage"] == "complete"

    def test_a_plan_s_decline_is_a_change_to_the_specification(self, agents, monkeypatch, tmp_path) -> None:
        self._advised(agents, monkeypatch, reviewing=False)
        agents.script("scrum_master", [responds_with(_plan(
            ["UX-1"], declined=["UX-2: declined - the brief asks for no message after a change"],
        ))])

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-declined-in-plan")

        [change] = [d for d in state["decisions"] if d["decision"].startswith("decline ")]
        assert change["point"] == "technical_specification" and change["decision"] == "decline UX-2"
        assert "no message after a change" in change["rationale"]
        assert list(state["advice_declined"]) == ["UX-2"] and len(agents.requests["scrum_master"]) == 1
        assert state["stage"] == "complete"

    def test_no_specialist_checks_before_an_item_of_its_is_due(self, agents, monkeypatch, tmp_path) -> None:
        """Sprint 1 places nothing of the UI/UX specialist's, so it is not asked; sprint 2, the last, owes both."""
        self._advised(agents, monkeypatch, reviewing=True)
        agents.script("scrum_master", [responds_with(_plan([], ["UX-1", "UX-2"]))])
        agents.script("advice_reviewer_ui_ux", [responds_with(AdviceReview())])
        from app.graph import acceptance_nodes

        monkeypatch.setattr(acceptance_nodes, "sprint_already_done", lambda state: "")

        state = start_workflow(_graph(), _document(), _repository(tmp_path), "run-advice-due-later")

        assert len(agents.requests["advice_reviewer_ui_ux"]) == 1
        assert "every adopted item is built by its end" in agents.last_request_text("advice_reviewer_ui_ux")
        assert state["stage"] == "complete"


@pytest.mark.parametrize("text", [
    "section",
    "lead",
    "request",
])
def test_the_new_text_a_model_reads_names_no_product(text) -> None:
    from app.agents import advice_review
    from app.agents.advice_review import advice_for_the_lead, send_back_text

    import os

    with_it = build_sprint_planning_request("spec", "/", adopted_advice=["UX-1: x"], unscheduled_advice=["UX-1"])[
        "messages"][0]["content"]
    without = build_sprint_planning_request("spec", "/")["messages"][0]["content"]
    head = len(os.path.commonprefix([with_it, without]))
    tail = len(os.path.commonprefix([with_it[::-1], without[::-1]]))
    texts = {
        "section": with_it[head:len(with_it) - tail],
        "lead": advice_for_the_lead(["UX-1: x"]) + send_back_text([DB_1]),
        "request": advice_review._SYSTEM_PROMPT + build_advice_review_request(
            "ui_ux", ["UX-1: x"], "g", "", [], due_because="the sprint plan places each here")["messages"][0]["content"],
    }

    _no_banned_word(texts[text])
