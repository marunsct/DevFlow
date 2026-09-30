"""An intake may not defer what the brief's acceptance criteria require.

One run's brief said, under `## Acceptance Criteria`, "Users can add, edit,
delete tasks". The intake's success measures paraphrased it as "create, read,
update, and delete", which a workflow "Update task status" satisfies; its
deferred scope listed "Task editing (beyond status)"; and the specification's
scope then excluded editing. No check objected, because none of them saw the
word "edit" again - and the brief's line has no "and", so it was not read as a
list at all.

So the brief's acceptance criteria join the success measures verbatim, a list
without a conjunction is a list, and a deferred item naming a capability a
measure requires is removed with the reason written into the intake. Nothing
here names a language, a framework or a kind of product.
"""
from __future__ import annotations

from app.agents.brief_constraints import acceptance_lines
from app.agents.product_manager import (
    ProductManagerOutput,
    with_the_measures_the_brief_states,
    without_deferring_what_the_measures_require,
)
from app.agents.success_measures import capabilities_never_named, enumerations

BRIEF = """# Product Brief: Something

## Requirements
1. **Features**:
   - Import records from a file

## Acceptance Criteria
- Operators can create, rename, archive projects
2. Reports export correctly
"""


class TestAListWithoutAConjunction:
    def test_is_read_as_a_list_of_required_items(self) -> None:
        assert enumerations("Users can add, edit, delete tasks") == [(True, ["add", "edit", "delete"])]

    def test_a_list_with_a_conjunction_is_read_once(self) -> None:
        assert enumerations("create, read, update, and delete records") == [
            (True, ["create", "read", "update", "delete"])
        ]

    def test_two_words_and_a_comma_are_not_a_list(self) -> None:
        assert enumerations("Yes, exports work") == []

    def test_a_document_that_skips_an_item_is_caught(self) -> None:
        missing = capabilities_never_named("Create a project. Archive it.", ["Operators can create, rename, archive"])
        assert missing == {1: ["rename"]}


class TestTheBriefsCriteria:
    def test_are_read_from_its_heading_verbatim(self) -> None:
        assert acceptance_lines(BRIEF) == [
            "Operators can create, rename, archive projects",
            "Reports export correctly",
        ]

    def test_join_the_measures_after_the_model_s_own(self) -> None:
        out = with_the_measures_the_brief_states(
            ProductManagerOutput(product_name="p", success_measures=["Reports export correctly"]), BRIEF
        )
        assert out.success_measures == ["Reports export correctly", "Operators can create, rename, archive projects"]

    def test_a_brief_without_them_changes_nothing(self) -> None:
        intake = ProductManagerOutput(product_name="p", success_measures=["x"])
        assert with_the_measures_the_brief_states(intake, "# Brief\n\nNo criteria here.") is intake


class TestDeferredScope:
    def _intake(self, deferred: list[str], questions: list[str] = ()) -> ProductManagerOutput:
        return ProductManagerOutput(
            product_name="p",
            success_measures=["Operators can create, rename, archive projects"],
            deferred_scope=deferred,
            open_questions=list(questions),
        )

    def test_an_item_naming_a_required_capability_is_not_deferred(self) -> None:
        out = without_deferring_what_the_measures_require(
            self._intake(["Renaming projects later", "Scheduled exports"],
                         ["Should renaming keep the old name?", "How often are exports run?"])
        )
        assert out.deferred_scope == ["Scheduled exports"]
        assert out.evidence_vs_assumptions == [
            'Evidence: "Renaming projects later" is not deferred - the success measure '
            '"Operators can create, rename, archive projects" requires rename'
        ]
        assert out.open_questions[0].endswith('(the success measure "Operators can create, rename, archive projects" bears on this)')
        assert out.open_questions[1] == "How often are exports run?"

    def test_an_intake_with_no_conflict_is_returned_unchanged(self) -> None:
        intake = self._intake(["Scheduled exports"], ["Should creation be audited?"])
        assert without_deferring_what_the_measures_require(intake) is intake

    def test_an_or_list_requires_no_single_item(self) -> None:
        intake = ProductManagerOutput(
            product_name="p", success_measures=["Data is kept in a file or a database"],
            deferred_scope=["A hosted database"],
        )
        assert without_deferring_what_the_measures_require(intake) is intake
