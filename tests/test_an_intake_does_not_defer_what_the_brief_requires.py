"""An intake may not defer what the brief's acceptance criteria require.

One run's brief said, under `## Acceptance Criteria`, "Users can add, edit,
delete tasks". The intake's success measures paraphrased it as "create, read,
update, and delete", which a workflow "Update task status" satisfies; its
deferred scope listed "Task editing (beyond status)"; and the specification's
scope then excluded editing. No check objected, because none of them saw the
word "edit" again - and the brief's line has no "and", so it was not read as a
list at all.

So the brief's acceptance criteria join the success measures verbatim, a list
without a conjunction is a list, and a deferred item naming a capability the
brief's criteria require is marked with that requirement. Nothing
here names a language, a framework or a kind of product.
"""
from __future__ import annotations

from app.agents.brief_constraints import acceptance_lines
from app.agents.product_manager import (
    ProductManagerOutput,
    with_the_measures_the_brief_states,
    with_what_the_brief_requires_marked_in_deferred_scope,
)
from app.agents.success_measures import capabilities_never_named, enumerations, names_the_word

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
    def _intake(self, deferred: list[str], questions: list[str] = (), measures: list[str] = ()) -> ProductManagerOutput:
        return ProductManagerOutput(
            product_name="p",
            success_measures=list(measures),
            deferred_scope=deferred,
            open_questions=list(questions),
        )

    def test_a_deferral_touching_a_required_capability_is_marked_not_removed(self) -> None:
        out = with_what_the_brief_requires_marked_in_deferred_scope(
            self._intake(["Renaming projects later", "Scheduled exports"],
                         ["Should renaming keep the old name?", "How often are exports run?"]),
            BRIEF,
        )
        assert out.deferred_scope == [
            'Renaming projects later (the brief requires rename: "Operators can create, rename, archive '
            'projects" - only what goes beyond that is deferred)',
            "Scheduled exports",
        ]
        assert out.open_questions == [
            'Should renaming keep the old name? (the brief says: "Operators can create, rename, archive projects")',
            "How often are exports run?",
        ]

    def test_only_the_brief_s_criteria_count_not_the_model_s_measures(self) -> None:
        """One run's own measure "ease of use and error-free operations" made
        "use" required, and "User authentication ..." was deleted from scope."""
        intake = self._intake(
            ["User authentication or multi-user sync, notifications"],
            measures=["User satisfaction measured by ease of use and error-free operations."],
        )
        assert with_what_the_brief_requires_marked_in_deferred_scope(intake, BRIEF) is intake

    def test_a_word_is_matched_whole(self) -> None:
        intake = self._intake(["Created-by audit trail", "Archived-item recovery"])
        out = with_what_the_brief_requires_marked_in_deferred_scope(intake, BRIEF)
        assert out.deferred_scope[0] == "Created-by audit trail (the brief requires create: \"Operators can create, rename, archive projects\" - only what goes beyond that is deferred)"
        assert not names_the_word("use", "User authentication")
        assert not names_the_word("add", "Address book")
        assert names_the_word("edit", "Task editing (beyond status)")
        assert names_the_word("delete", "No deletion of archived items")

    def test_an_intake_with_no_conflict_is_returned_unchanged(self) -> None:
        intake = self._intake(["Scheduled exports"], ["Should creation be audited?"])
        assert with_what_the_brief_requires_marked_in_deferred_scope(intake, BRIEF) is intake

    def test_a_brief_without_criteria_changes_nothing(self) -> None:
        intake = self._intake(["Renaming projects later"])
        assert with_what_the_brief_requires_marked_in_deferred_scope(intake, "# Brief\n\nNothing.") is intake
