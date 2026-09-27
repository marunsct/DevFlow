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

    def test_the_document_is_skipped_rather_than_written_empty(self):
        """A file that exists and says nothing is worse than no file."""
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow)
        at = source.index("recorded = outcome_text or _what_this_stage_reported")
        block = source[at : at + 420]

        assert "if recorded:" in block

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

    def test_a_reviewing_stage_keeps_its_own_summary(self):
        """The verdict is the whole story for it, so the fallback must not replace it."""
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow)

        assert "outcome_text or _what_this_stage_reported" in source
