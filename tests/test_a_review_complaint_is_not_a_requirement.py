"""A document that reviews the work must not be read as stating requirements.

`_actions_the_documents_require` globbed every `*.md` under `docs/`. Four of the
nine workflow documents exist to comment on the work - `architecture_review`,
`security_review`, `milestone_review` - along with the sprint summaries, and a
comment is not a requirement.

Measured on one run, whose blocking finding was

    This project's own documents require that a user can `edit`: "- The test
    suite `app.test.mjs` only clears local storage and lacks tests for core CRUD
    operations (add, edit, delete) or filtering tasks, failing to meet the
    a[cceptance criteria]"

The quoted line is a review finding about missing *tests*. The word `edit` inside
it was read as the documents requiring that a user can edit, and graded BREAKS.

Two more of the same shape, from other stored runs:

    "If edit/filter functionality introduces regressions, revert app.mjs and
     index.html to the Sprint 1 committed state"        - a rollback plan
    "Verified index.html (245 lines) against milestone goal: form with
     #task-form (title input + description textarea..." - a verification note

Worse than a false positive each: it is a loop. A review's text becomes the next
round's requirements, so each revision can manufacture blocking findings out of
the previous review's complaints, and the run reaches its revision limit having
been told to implement things nobody asked for.

Across the 76 stored workspaces these two checks produce 111 of about 190
breaking findings. This removes 4 of them and leaves the rest, which come from
documents that really do state requirements.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _DOCUMENTS_THAT_STATE_REQUIREMENTS,
    _a_required_action_no_test_covers,
    _a_required_action_nothing_implements,
    _actions_the_documents_require,
    _source_files,
)

#: The line from one run's own milestone review that became a requirement.
A_REVIEW_COMPLAINT = (
    "## Findings\n"
    "- The test suite `app.test.mjs` only clears local storage and lacks tests "
    "for core CRUD operations (add, edit, delete) or filtering tasks, failing "
    "to meet the acceptance criteria.\n"
)

#: A document that really does state requirements.
A_REQUIREMENT = (
    "## Acceptance criteria\n"
    "- Users can add, edit, and delete tasks without errors\n"
)


@pytest.fixture
def a_project(tmp_path):
    def _build(**documents: str):
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        for name, text in documents.items():
            (docs / name.replace("__", ".")).write_text(text)
        project = tmp_path / "app"
        project.mkdir(exist_ok=True)
        (project / "app.js").write_text("export const addTask = (t) => t;\n")
        (project / "app.test.mjs").write_text(
            "import { addTask } from './app.js';\ntest('add', () => addTask('x'));\n"
        )
        return tmp_path

    return _build


class TestTheReviewThatBecameARequirement:
    def test_a_milestone_review_states_no_requirements(self, a_project):
        root = a_project(milestone_review__md=A_REVIEW_COMPLAINT)

        assert _actions_the_documents_require(root) == {}

    def test_no_blocking_finding_comes_from_it(self, a_project):
        root = a_project(milestone_review__md=A_REVIEW_COMPLAINT)
        files = _source_files(root)

        assert _a_required_action_nothing_implements(files, root, "") == []
        assert _a_required_action_no_test_covers(files, root, "") == []

    @pytest.mark.parametrize(
        "document",
        ["milestone_review__md", "architecture_review__md", "security_review__md",
         "sprint_1_summary__md", "sprint_2_summary__md"],
    )
    def test_every_commenting_document_is_excluded(self, a_project, document):
        root = a_project(**{document: A_REVIEW_COMPLAINT})

        assert _actions_the_documents_require(root) == {}

    def test_a_rollback_plan_is_not_a_requirement(self, a_project):
        """From one run's stored documents."""
        root = a_project(
            milestone_review__md=(
                "If edit/filter functionality introduces regressions, revert "
                "app.mjs and index.html to the Sprint 1 committed state.\n"
            )
        )

        assert _actions_the_documents_require(root) == {}


class TestTheRequirementsThatMustSurvive:
    @pytest.mark.parametrize(
        "document",
        ["product_intake__md", "technical_specification__md", "milestone_plan__md",
         "sprint_plan__md", "technology_stack__md", "tools_and_models__md"],
    )
    def test_every_stating_document_is_still_read(self, a_project, document):
        root = a_project(**{document: A_REQUIREMENT})

        assert "edit" in _actions_the_documents_require(root), document

    def test_the_finding_is_still_raised_from_a_real_requirement(self, a_project):
        root = a_project(product_intake__md=A_REQUIREMENT)
        files = _source_files(root)

        problems = _a_required_action_nothing_implements(files, root, "")

        assert any("`edit`" in problem for problem in problems), problems

    def test_a_brief_in_the_workspace_root_is_still_read(self, a_project, tmp_path):
        """Which is where an operator's own brief lands, under any name."""
        root = a_project()
        (tmp_path / "whatever-the-operator-called-it.md").write_text(A_REQUIREMENT)

        assert "edit" in _actions_the_documents_require(root)

    def test_the_brief_argument_still_outranks_the_documents(self, a_project):
        """An action the operator asked for and the documents dropped."""
        root = a_project(product_intake__md="## Scope\n- Something else entirely\n")
        files = _source_files(root)

        problems = _a_required_action_nothing_implements(files, root, A_REQUIREMENT)

        assert any("`edit`" in problem for problem in problems), problems

    def test_a_review_cannot_drown_out_a_real_requirement(self, a_project):
        """Both present: the requirement still counts, the complaint still does not."""
        root = a_project(
            product_intake__md=A_REQUIREMENT,
            milestone_review__md=A_REVIEW_COMPLAINT,
        )

        required = _actions_the_documents_require(root)

        assert "edit" in required
        assert "test suite" not in required["edit"], required["edit"]


class TestTheAllowlist:
    def test_it_names_only_documents_the_workflow_renders(self):
        from app.tools.repository import WORKFLOW_DOCUMENTS

        assert set(_DOCUMENTS_THAT_STATE_REQUIREMENTS) <= set(WORKFLOW_DOCUMENTS)

    def test_no_review_document_is_on_it(self):
        assert not any("review" in name for name in _DOCUMENTS_THAT_STATE_REQUIREMENTS)

    def test_the_intake_and_the_specification_are_on_it(self):
        """The two that carry acceptance criteria. Losing either is the old bug
        `_actions_the_brief_requires` was written for, the other way round."""
        assert "product_intake.md" in _DOCUMENTS_THAT_STATE_REQUIREMENTS
        assert "technical_specification.md" in _DOCUMENTS_THAT_STATE_REQUIREMENTS

    def test_a_missing_docs_folder_requires_nothing(self, tmp_path):
        assert _actions_the_documents_require(tmp_path) == {}
