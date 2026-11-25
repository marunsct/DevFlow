"""Each sprint, the consulted specialists also review the changed files in their own domain (plan SP.3).

Measured on one medium run (a service and a page): a lookup by name through a primary-key fetch, another user's record
refused with an exception that became a server error, a filter accepted and ignored, a rate limiter that never recorded
an attempt and every origin allowed with credentials passed every specialist - each was asked only which of its adopted
items were not built. Behind `SPECIALIST_DOMAIN_REVIEW`, in the same call, each also reports defects in its own domain
with a file, a line and the failure a user meets; a blocking or major one is a gating finding the milestone reviewer
weighs, the rest one note carried to the next sprint.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.agents.advice_review import AdviceReview, findings_block, findings_from, roles_to_review
from app.graph import workflow as workflow_module
from app.graph.workflow import start_workflow
from test_graph_routing import (  # noqa: F401 - `agents` is a fixture
    _approved_review,
    _document,
    _graph,
    _repository,
    _script_through_sprint,
    _spec,
    agents,
    responds_with,
)

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _defect(severity: str, file: str = "api/notes.py", line: int | None = 42, defect: str = "looks a tag up by name "
            "through a fetch by primary key", failure: str = "a second note with a reused tag name answers 500"):
    from app.agents.specialist_domain_review import DomainDefect

    return DomainDefect(severity=severity, file=file, line=line, defect=defect, failure=failure)


def _answer(*defects, not_built=()):
    from app.agents.specialist_domain_review import AdviceAndDomainReview

    return AdviceAndDomainReview(not_built=list(not_built), domain_defects=list(defects))


class TestWhatTheyReport:
    def test_a_defect_names_the_specialist_the_file_line_and_the_failure(self) -> None:
        assert findings_from("backend", _answer(_defect("major"))) == [
            "[backend specialist] defect (major) at api/notes.py:42: looks a tag up by name through a fetch by primary "
            "key - fails: a second note with a reused tag name answers 500",
        ]

    def test_a_severity_in_another_vocabulary_is_read_into_the_review_s(self) -> None:
        """Four schemas name severity and no two agree (`app.agents.severity`): `High` is not refused."""
        assert _defect("High").severity == "major" and _defect("critical").severity == "blocking"

    def test_at_most_five_a_role_are_kept_the_most_severe_first(self) -> None:
        answer = _answer(*[_defect("minor", file=f"a{n}.py") for n in range(5)], _defect("blocking", file="b.py"))

        lines = findings_from("database", answer)

        assert len(lines) == 5 and "defect (blocking) at b.py:42" in lines[0]

    def test_a_defect_naming_no_file_cannot_be_checked_and_is_left_out(self) -> None:
        assert findings_from("database", _answer(_defect("major", file=" "))) == []

    def test_its_advice_lines_are_kept_beside_them(self) -> None:
        lines = findings_from("database", _answer(_defect("minor"), not_built=["DB-1: no index on tag name"]))

        assert lines[0] == "[database specialist] not built: DB-1: no index on tag name"
        assert lines[1].startswith("[database specialist] defect (minor) at api/notes.py:42")


class TestWhatBecomesOfThem:
    def test_a_major_defect_is_a_gating_finding_of_the_sprint_and_a_minor_one_a_note(self) -> None:
        from app.agents.specialist_domain_review import sprint_findings

        lines = findings_from("security_reliability", _answer(
            _defect("major", file="api/app.py", line=9, defect="allows every origin with credentials",
                    failure="any site can read a signed-in user's notes"),
            _defect("minor", file="api/auth.py", line=30, defect="the session cookie has no SameSite",
                    failure="the cookie is sent on requests from other sites"),
        ))

        found = sprint_findings(lines, 2)

        gating = [f for f in found if f["gating"]]
        notes = [f for f in found if not f["gating"]]
        assert [(f["severity"], f["source"], f["round"]) for f in gating] == [("major", "specialist", 2)]
        assert "api/app.py:9" in gating[0]["description"] and "any site can read" in gating[0]["description"]
        assert len(notes) == 1 and "api/auth.py:30" in notes[0]["description"]

    def test_the_advice_not_built_is_still_one_record_of_its_own(self) -> None:
        from app.agents.specialist_domain_review import sprint_findings

        found = sprint_findings(findings_from("database", _answer(not_built=["DB-1: no index"])), 1)

        assert [f["source"] for f in found] == ["advice"]

    def test_the_milestone_reviewer_is_shown_them_apart_from_the_advice_not_built(self) -> None:
        block = findings_block({"backend": findings_from("backend", _answer(_defect("major"), not_built=["BE-1: x"]))})

        advice, _, domain = block.partition("in their own domains")
        assert "[backend specialist] not built: BE-1: x" in advice and "api/notes.py:42" not in advice
        assert "api/notes.py:42" in domain and "a reused tag name answers 500" in domain

    def test_defects_alone_still_reach_the_milestone_reviewer(self) -> None:
        block = findings_block({"backend": findings_from("backend", _answer(_defect("blocking")))})

        assert "api/notes.py:42" in block and "adopted advice not built" not in block


class TestWhoReviews:
    ADVICE = {"database": ["Give every record a generated id."], "backend": ["Answer 404 for a missing note."]}
    ALL_DECLINED = SimpleNamespace(specialist_advice_decisions=["DB-1: declined - ids exist", "BE-1: declined - x"])

    def test_with_the_switch_on_a_consulted_role_reviews_its_domain_with_no_advice_adopted(self, monkeypatch) -> None:
        monkeypatch.setenv("SPECIALIST_DOMAIN_REVIEW", "on")

        assert roles_to_review(self.ADVICE, self.ALL_DECLINED) == ["database", "backend"]

    def test_with_it_off_only_adopted_advice_is_checked(self, monkeypatch) -> None:
        monkeypatch.setenv("SPECIALIST_DOMAIN_REVIEW", "off")

        assert roles_to_review(self.ADVICE, self.ALL_DECLINED) == []


class TestThroughTheGraph:
    @staticmethod
    def _run(agents, monkeypatch, tmp_path, answer):
        from test_the_specialists_advise_before_the_specification import TestThroughTheGraph as Consulting

        from app.agents.specialist_advice import SpecialistAdvice

        Consulting._consulting(monkeypatch, agents, ["backend"], reviewing=True)
        Consulting._script_the_stack(agents)
        monkeypatch.setattr(
            workflow_module, "create_advice_reviewer_agent",
            lambda role, *args, **kwargs: agents.agent(f"advice_reviewer_{role}"),
        )
        agents.script("advisor_backend", [responds_with(SpecialistAdvice(recommendations=["Answer 404 for a missing note."]))])
        agents.script("principal_architect", [responds_with(_spec(
            api_and_event_contracts=["GET /notes?tag=x -> 200, only the notes with that tag"],
            specialist_advice_decisions=["BE-1: adopted - api_and_event_contracts"],
        ))])
        agents.script("architecture_review", [responds_with(_approved_review())])
        agents.script("advice_reviewer_backend", [responds_with(answer)])
        _script_through_sprint(agents, advice=["BE-1"])  # the plan places the adopted item (SP.2)
        return start_workflow(_graph(), _document(), _repository(tmp_path), "run-domain-review")

    def test_the_specialist_is_asked_to_review_its_domain_against_the_specification(self, agents, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("SPECIALIST_DOMAIN_REVIEW", "on")

        self._run(agents, monkeypatch, tmp_path, AdviceReview())

        asked = agents.last_request_text("advice_reviewer_backend")
        assert "status code" in asked and "accepted and then ignored" in asked
        assert "GET /notes?tag=x -> 200, only the notes with that tag" in asked

    def test_with_the_switch_off_the_request_is_the_advice_check_alone(self, agents, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("SPECIALIST_DOMAIN_REVIEW", "off")

        self._run(agents, monkeypatch, tmp_path, AdviceReview())

        assert "accepted and then ignored" not in agents.last_request_text("advice_reviewer_backend")

    def test_a_major_defect_reaches_the_milestone_reviewer_and_the_sprint_record_as_gating(self, agents, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("SPECIALIST_DOMAIN_REVIEW", "on")

        state = self._run(agents, monkeypatch, tmp_path, _answer(_defect(
            "major", file="api/notes.py", line=17, defect="the tag filter is read and never applied",
            failure="GET /notes?tag=work answers every note")))

        asked = agents.last_request_text("milestone_reviewer")
        assert "api/notes.py:17" in asked and "GET /notes?tag=work answers every note" in asked
        recorded = [f for attempt in state.get("sprint_attempts") or [] for f in attempt.get("findings") or []]
        assert any(f["source"] == "specialist" and f["gating"] and "api/notes.py:17" in f["description"] for f in recorded)


@pytest.mark.parametrize("role", ["database", "backend", "security_reliability", "ui_ux"])
def test_each_checklist_and_rule_names_no_product_and_no_control(role) -> None:
    from app.agents import specialist_domain_review as domain

    text = (domain.DOMAIN_RULE + domain.section(role) + domain.block(
        {role: ["[x] defect (major) at a.py:1: y - fails: z"]}, [role])).lower()
    text += " ".join(str(field.description) for field in domain.AdviceAndDomainReview.model_fields.values()).lower()
    text += " ".join(str(field.description) for field in domain.DomainDefect.model_fields.values()).lower()
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", text), word
