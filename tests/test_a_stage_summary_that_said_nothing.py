"""204 of 229 stage summaries on disk held a heading and nothing else.

`_outcome_summary` returns "" for a stage whose schema has neither a status nor
findings, and says in its own docstring that this is "the right amount of
narration for it". That is a decision about the live activity stream, where
publishing nothing is correct.

The same empty string was also written to `docs/stage_summaries/<stage>.md`.
Counted across the stored runs:

    stage                    total  empty
    defect_fix                  57     57
    test_round                  40     40
    specialist_ui_ux            21     21
    specialist_testing          19     19
    specialist_backend          12     12
    principal_architect          9      9
    ...
    architecture_review          9      0
    milestone_review             8      0
    security_review              8      0

Every specialist, every defect fix, every test round: 25 bytes, a heading. Only
the three reviewing stages, which have a status, said anything.

So the stream keeps its silence and the document gets what the stage actually
returned - `SpecialistOutput` already carries changed files, decisions, tests,
documentation, risks, blockers and the commands it ran. A response that really
carries nothing writes no document at all, which is more honest than an empty one.
"""

from __future__ import annotations

import pytest

from app.agents.specialists import SpecialistOutput, VerificationRun
from app.graph.workflow import (
    MOST_ITEMS_IN_A_STAGE_SUMMARY,
    _outcome_summary,
    _what_this_stage_reported,
)


def _the_summary_a_stage_leaves(root, stage_name: str, answer) -> str | None:
    """What the stage runner writes to `docs/stage_summaries/<stage>.md` for a stage answering `answer`, or None."""
    from types import SimpleNamespace

    from app.graph import workflow

    class _Answering:
        def invoke(self, request, config=None):
            return {"structured_response": answer, "messages": []}

    workflow._run_gated_agent(
        {"stage": stage_name, "repository": SimpleNamespace(root_path=str(root))},
        {"configurable": {"thread_id": "thread-outer"}},
        stage_name=stage_name, agent=_Answering(),
        initial_request={"messages": [{"role": "user", "content": "Do the work."}]},
        output_key="answer", next_stage="next",
    )
    path = root / "docs" / "stage_summaries" / f"{stage_name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


class TestTheSummaryASpecialistNowGets:
    def test_it_names_the_files_that_changed(self):
        body = _what_this_stage_reported(
            SpecialistOutput(changed_files=["task-manager/app.js", "task-manager/index.html"])
        )

        assert "Files changed (2):" in body
        assert "- task-manager/app.js" in body

    def test_it_records_the_decisions(self):
        body = _what_this_stage_reported(
            SpecialistOutput(decisions=["Used focusout instead of blur"])
        )

        assert "Decisions (1):" in body
        assert "focusout" in body

    @pytest.mark.parametrize(
        "field,label",
        [
            ("tests", "Tests"),
            ("documentation", "Documentation"),
            ("risks", "Risks"),
            ("blockers", "Blockers"),
        ],
    )
    def test_every_field_worth_recording(self, field, label):
        body = _what_this_stage_reported(SpecialistOutput(**{field: ["something"]}))

        assert f"{label} (1):" in body

    def test_the_commands_it_ran_are_listed(self):
        body = _what_this_stage_reported(
            SpecialistOutput(
                verification=[VerificationRun(command="npm test", exit_code=0)]
            )
        )

        assert "Commands run (1):" in body
        assert "npm test" in body

    def test_a_long_list_is_capped_and_counted(self):
        many = [f"file{index}.js" for index in range(MOST_ITEMS_IN_A_STAGE_SUMMARY + 4)]

        body = _what_this_stage_reported(SpecialistOutput(changed_files=many))

        assert f"Files changed ({len(many)}):" in body
        assert "and 4 more" in body

    def test_the_order_puts_what_changed_first(self):
        body = _what_this_stage_reported(
            SpecialistOutput(
                changed_files=["a.js"], decisions=["d"], blockers=["b"]
            )
        )

        assert body.index("Files changed") < body.index("Decisions") < body.index("Blockers")


class TestNothingIsWrittenWhenThereIsNothing:
    def test_an_empty_response_produces_no_body(self):
        assert _what_this_stage_reported(SpecialistOutput()) == ""

    def test_blank_items_do_not_count(self):
        assert _what_this_stage_reported(SpecialistOutput(decisions=["", "   "])) == ""

    def test_the_document_is_skipped_rather_than_written_empty(self, tmp_path):
        """A file that exists and says nothing is worse than no file."""
        assert _the_summary_a_stage_leaves(tmp_path, "specialist_backend_0", SpecialistOutput()) is None

        written = _the_summary_a_stage_leaves(tmp_path, "specialist_backend_1", SpecialistOutput(decisions=["Kept the list sorted"]))
        assert "- Kept the list sorted" in written

    def test_an_object_with_none_of_the_fields_does_not_raise(self):
        class Bare:
            pass

        assert _what_this_stage_reported(Bare()) == ""


class TestTheStreamIsUnchanged:
    def test_a_specialist_still_publishes_nothing(self):
        """Its silence is a decision `_outcome_summary` documents, and it stands."""
        assert _outcome_summary(SpecialistOutput(changed_files=["a.js"])) == ""

    def test_a_reviewing_stage_still_leads_with_its_verdict(self):
        class Review:
            status = "approved"
            findings = []

        assert _outcome_summary(Review()).startswith("Outcome: approved")

    def test_a_reviewing_stage_keeps_its_own_summary(self, tmp_path):
        """The verdict is the whole story for it, so the fallback must not replace it."""
        from app.agents.milestone_reviewer import MilestoneReviewOutput

        review = MilestoneReviewOutput.model_validate({
            "status": "changes_required", "acceptance_evidence": "read", "documentation_reviewed": True,
            "tests_reviewed": True, "findings": [{"category": "testing", "severity": "major",
                                                  "description": "The count is wrong", "required_remediation": "r",
                                                  "affected_files": []}],
        })

        written = _the_summary_a_stage_leaves(tmp_path, "milestone_review", review)

        assert "Outcome: changes_required" in written and "The count is wrong" in written
