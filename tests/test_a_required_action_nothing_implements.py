"""An action the run's own documents enumerate and the product never builds.

`tests/brief_low.md` lists its features as "Add new tasks", "Mark tasks as
complete/incomplete", "Delete tasks" and "Filter tasks by status", and states
separately, under Acceptance Criteria, "Users can add, edit, delete tasks".
Editing is in the second list and not the first.

Two of three runs against that brief shipped no way to edit a task. Run
b0db10b1's own `product_intake.md` had it right - "All four acceptance criteria
delivered together: add/edit/delete, persistence, filtering, and responsive
design" - and the product it then built has no edit control, no edit handler and
no test naming one. Neither its security review nor its milestone review raised
it. Run b598780b, from the same brief, built editing with a double-click handler
and an Edit button, so this is what the workflow drops, not what it cannot do.

The requirement is captured correctly and then lost between the intake and the
code, which is precisely the gap no reviewer is looking at.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _a_required_action_nothing_implements,
    _actions_the_documents_require,
    _source_files,
)

INTAKE = """# Product Intake

## Acceptance criteria
- Users can add, edit, delete tasks
- Tasks persist between page refreshes
"""


def _problems(root):
    return _a_required_action_nothing_implements(_source_files(root), root)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(INTAKE)
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script src="app.js"></script></body></html>'
    )
    return tmp_path


def test_the_action_that_went_missing_is_named(project):
    """Run b0db10b1's shape: add and delete built, edit dropped."""
    (project / "app.js").write_text(
        "function addTask(t) { return t; }\n"
        "function deleteTask(id) { return id; }\n"
    )

    problems = _problems(project)

    assert len(problems) == 1, problems
    assert "`edit`" in problems[0]
    # It must quote the line it read the requirement from.
    assert "Users can add, edit, delete tasks" in problems[0]


def test_a_product_that_implements_every_action_is_silent(project):
    (project / "app.js").write_text(
        "function addTask(t) { return t; }\n"
        "function editTask(id) { return id; }\n"
        "function deleteTask(id) { return id; }\n"
    )
    assert _problems(project) == []


def test_a_synonym_counts_as_the_action(project):
    """A product that calls editing `rename` has delivered `edit`."""
    (project / "app.js").write_text(
        "function addTask(t) { return t; }\n"
        "function renameTask(id) { return id; }\n"
        "function deleteTask(id) { return id; }\n"
    )
    assert _problems(project) == []


def test_a_test_naming_the_action_does_not_count(project):
    """Corrected: a suite is not the product.

    This asserted the opposite - "built or tested, either is evidence the
    capability was not forgotten" - and that union was wrong. Run 6b511391 was
    reported clean for `edit` on the strength of `app.test.mjs` mentioning it,
    with no edit anywhere in `app.js`. Whether a suite covers the requirement
    is `_a_required_action_no_test_covers`'s question, and it reads the suites;
    this one reads the product.
    """
    (project / "app.js").write_text(
        "function addTask(t) { return t; }\nfunction deleteTask(i) { return i; }\n"
    )
    (project / "app.test.mjs").write_text(
        "import { test } from 'node:test';\ntest('edit a task', () => {});\n"
    )

    problems = _problems(project)

    assert len(problems) == 1 and "`edit`" in problems[0]


class TestItDoesNotInventRequirements:
    """The narrowness, which is what makes this honest."""

    def test_a_single_verb_in_prose_is_not_an_enumeration(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "product_intake.md").write_text(
            "# Intake\n## Acceptance criteria\n- Users can delete tasks\n"
        )
        (tmp_path / "app.js").write_text("const x = 1;\n")
        (tmp_path / "index.html").write_text("<html></html>")
        assert _problems(tmp_path) == []

    def test_adjectives_are_not_actions(self, tmp_path):
        """"simple, fast and lightweight" is not a feature list."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "product_intake.md").write_text(
            "# Intake\n## Acceptance criteria\n"
            "- The app must be simple, fast and lightweight\n"
            "- Responsive design for mobile and desktop\n"
        )
        (tmp_path / "app.js").write_text("const x = 1;\n")
        (tmp_path / "index.html").write_text("<html></html>")
        assert _actions_the_documents_require(tmp_path) == {}
        assert _problems(tmp_path) == []

    def test_a_line_that_is_not_a_criterion_is_ignored(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "notes.md").write_text(
            "We considered whether to add, edit, delete in one screen.\n"
        )
        (tmp_path / "app.js").write_text("const x = 1;\n")
        (tmp_path / "index.html").write_text("<html></html>")
        assert _problems(tmp_path) == []

    def test_no_documents_require_nothing(self, tmp_path):
        (tmp_path / "app.js").write_text("const x = 1;\n")
        (tmp_path / "index.html").write_text("<html></html>")
        assert _problems(tmp_path) == []


class TestTheSynonymsAreEvidence:
    """Generic vocabulary must not be read as a delivered feature.

    The first version accepted `update`, `change`, `new`, `append` and `check`.
    Run 8904f87b, which has no way to edit a task, was reported clean because
    one comment in it reads "update closure so subsequent ops work".
    """

    @pytest.fixture
    def bare(self, project):
        (project / "app.js").write_text(
            "function addTask(t) { return t; }\n"
            "function deleteTask(id) { return id; }\n"
        )
        return project

    @pytest.mark.parametrize(
        "incidental",
        [
            "// update closure so subsequent ops work\n",
            "el.addEventListener('change', () => {});\n",
            "const d = new Date();\n",
            "parent.appendChild(node);\n",
            "const box = document.querySelector('input[type=checkbox]');\n",
        ],
    )
    def test_ordinary_code_is_not_evidence_of_editing(self, bare, incidental):
        bare_js = bare / "app.js"
        bare_js.write_text(bare_js.read_text() + incidental)

        problems = _problems(bare)

        assert len(problems) == 1, f"{incidental!r} was read as an edit feature"
        assert "`edit`" in problems[0]

    def test_a_css_class_is_not_a_filter_feature(self, tmp_path):
        """`active` and `completed` are in every to-do list, filtering or not."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "product_intake.md").write_text(
            "# Intake\n## Acceptance criteria\n- Users can filter, sort tasks\n"
        )
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "style.css").write_text(".active { color: red }\n.completed {}\n")
        (tmp_path / "app.js").write_text("const x = 1;\n")

        problems = _problems(tmp_path)

        assert len(problems) == 2
        assert any("`filter`" in p for p in problems)
        assert any("`sort`" in p for p in problems)


class TestEvidenceIsBehaviourNotMarkup:
    """Three buttons that do nothing are the opposite of delivered.

    Run b0db10b1's milestone review found "Filter buttons (All/Active/Completed)
    are present in index.html with data-filter attributes and CSS styling, but
    no JavaScript handler exists for them". Markup and a stylesheet are not
    evidence that a user can do anything, and neither is a built-in method that
    happens to share the name.
    """

    @pytest.fixture
    def wants_filtering(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "product_intake.md").write_text(
            "# Intake\n## Acceptance criteria\n- Users can add, filter, delete tasks\n"
        )
        (tmp_path / "task-utils.js").write_text(
            "export function addTask(t) { return t; }\n"
            # Array.prototype.filter, inside delete. Not a feature.
            "export function deleteTask(id, tasks) "
            "{ return tasks.filter(t => t.id !== id); }\n"
        )
        return tmp_path

    def test_buttons_and_stylesheet_alone_are_not_the_feature(self, wants_filtering):
        (wants_filtering / "index.html").write_text(
            "<!doctype html><html><body>\n"
            '<nav id="filter-buttons">\n'
            '<button data-filter="all" class="filter-btn">All</button>\n'
            "</nav>\n"
            '<script src="task-utils.js"></script></body></html>\n'
        )
        (wants_filtering / "style.css").write_text(".filter-btn { color: red }\n")

        problems = _problems(wants_filtering)

        assert any("`filter`" in p for p in problems), problems

    def test_a_handler_in_a_script_is_the_feature(self, wants_filtering):
        (wants_filtering / "index.html").write_text(
            '<!doctype html><html><body><script src="ui.js"></script></body></html>'
        )
        (wants_filtering / "ui.js").write_text(
            "function filterTasks(which) { return which; }\n"
        )
        assert _problems(wants_filtering) == []

    def test_an_inline_module_still_counts_as_script(self, wants_filtering):
        """Run 9c0fc48d kept its whole application inside the page."""
        (wants_filtering / "index.html").write_text(
            "<!doctype html><html><body>\n"
            '<script type="module">\n'
            "function filterTasks(which) { return which; }\n"
            "</script></body></html>\n"
        )
        assert _problems(wants_filtering) == []


class TestADescopeTheRunAuthorisedItself:
    """Recorded is better than forgotten, and still not the run's call.

    Run 35424714 captured "Users can successfully add, edit, and delete tasks
    without errors" in its intake, then wrote into its technical specification

        ADR-08 - Inline Editing: Deferred - not implemented in MVP

    and its milestone reviewer cited that ADR to accept the milestone, calling
    this check a false positive and suggesting the spec be reworded "to prevent
    future cross-file check false positives regarding deferred features".

    The ADR was real and the reasoning was reasonable. The authority was not:
    the same workflow wrote the requirement and the deferral, so one cannot
    overrule the other. This is the four-runs-running gap - runs 2, 3, 4 and 5
    all shipped without editing - and the difference in run 5 is only that it
    was argued rather than silent.
    """

    @pytest.fixture
    def deferred(self, project):
        (project / "app.js").write_text(
            "function addTask(t) { return t; }\n"
            "function deleteTask(id) { return id; }\n"
        )
        return project

    def test_a_recorded_deferral_changes_the_finding(self, deferred):
        (deferred / "docs" / "technical_specification.md").write_text(
            "# Spec\n\n## Decisions (ADR)\n"
            "ADR-08 - Inline Editing: Deferred - not implemented in MVP\n"
        )

        problems = _problems(deferred)

        assert len(problems) == 1
        assert "also defer it" in problems[0]
        assert "ADR-08" in problems[0], "the finding must quote the line it found"
        assert "carries no authority" in problems[0]
        assert "put the descope to the operator" in problems[0]

    def test_without_a_deferral_the_plain_finding_stands(self, deferred):
        problems = _problems(deferred)
        assert len(problems) == 1
        assert "also defer it" not in problems[0]
        assert "Either build it or record why it was dropped" in problems[0]

    def test_a_deferral_of_something_else_is_not_this_one(self, deferred):
        """`add` and `delete` are built; only a deferral of `edit` counts."""
        (deferred / "docs" / "technical_specification.md").write_text(
            "# Spec\n- Authentication is deferred to post-MVP.\n"
        )

        problems = _problems(deferred)

        assert "also defer it" not in problems[0]

    def test_a_built_feature_is_not_reported_however_it_is_described(self, project):
        """A deferral that was later reversed must not resurrect the finding."""
        (project / "app.js").write_text(
            "function addTask(t) { return t; }\n"
            "function editTask(id) { return id; }\n"
            "function deleteTask(id) { return id; }\n"
        )
        (project / "docs" / "technical_specification.md").write_text(
            "# Spec\nADR-08 - Inline Editing: Deferred - not implemented in MVP\n"
        )
        assert _problems(project) == []

    def test_it_still_blocks(self, deferred):
        from app.analysis.integration_checks import _severity_of

        (deferred / "docs" / "technical_specification.md").write_text(
            "ADR-08 - Inline Editing: Deferred - not implemented in MVP\n"
        )

        assert all(_severity_of(p) == "BREAKS" for p in _problems(deferred))


class TestARequirementSectionIsEnoughOnItsOwn:
    """A heading says these lines are requirements; the wording need not.

    The per-line test was too narrow. Run 0cbbb28b's intake stated

        ## Success measures
        - All four CRUD operations (add, edit, delete, mark complete) work
          without errors

    which names no actor - no "users can", no "acceptance" - and so matched
    nothing. That run shipped with no way to edit a task and this check said
    nothing about it, which is the second time the same gap has gone unreported
    for want of a phrase rather than for want of the requirement.

    The document's own structure is the more reliable signal.
    """

    @pytest.fixture
    def under_a_heading(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "index.html").write_text(
            '<!doctype html><html><body><script src="app.js"></script></body></html>'
        )
        (tmp_path / "app.js").write_text(
            "function addTask(t) { return t; }\n"
            "function deleteTask(id) { return id; }\n"
        )
        return tmp_path

    @pytest.mark.parametrize(
        "heading",
        [
            "## Success measures",
            "## Acceptance criteria",
            "### Requirements",
            "## Definition of done",
            "## MVP candidates",
        ],
    )
    def test_a_bullet_under_a_requirement_heading_counts(
        self, under_a_heading, heading
    ):
        (under_a_heading / "docs" / "product_intake.md").write_text(
            f"# Intake\n\n{heading}\n"
            "- All four CRUD operations (add, edit, delete) work without errors\n"
        )

        problems = _problems(under_a_heading)

        assert len(problems) == 1 and "`edit`" in problems[0]

    def test_the_section_ends_at_the_next_heading(self, under_a_heading):
        """A later section must not inherit the previous one's authority."""
        (under_a_heading / "docs" / "product_intake.md").write_text(
            "# Intake\n\n## Success measures\n- Tasks persist across reloads\n\n"
            "## Deferred scope\n- We considered add, edit, delete in one screen\n"
        )
        assert _problems(under_a_heading) == []

    def test_an_ordinary_section_still_needs_the_wording(self, under_a_heading):
        (under_a_heading / "docs" / "product_intake.md").write_text(
            "# Intake\n\n## Notes\n- We discussed add, edit, delete at length\n"
        )
        assert _problems(under_a_heading) == []

    def test_the_run_0cbbb28b_line_verbatim(self, under_a_heading):
        """The exact text that went unreported."""
        (under_a_heading / "docs" / "product_intake.md").write_text(
            "# Product Intake\n\n## Success measures\n"
            "- All four CRUD operations (add, edit, delete, mark complete) "
            "work without errors\n"
            "- Tasks persist correctly across page refreshes using local storage\n"
        )

        problems = _problems(under_a_heading)

        assert len(problems) == 1
        assert "`edit`" in problems[0]
        assert "All four CRUD operations" in problems[0]


class TestASuiteIsNotTheProduct:
    """A test naming a feature is not the product having one.

    Run 6b511391 was reported clean for `edit` because `app.test.mjs` mentions
    it, while `app.js` has no edit anywhere. This check asks whether the product
    does it; `_a_required_action_no_test_covers` asks whether anything would
    notice if it stopped. They read different files on purpose, and neither may
    borrow the other's evidence.

    The same mistake in a different check gave one run's dead filter
    buttons an alibi from the Playwright spec that located them.
    """

    @pytest.fixture
    def tested_but_unbuilt(self, project):
        (project / "app.js").write_text(
            "function addTask(t) { return t; }\n"
            "function deleteTask(id) { return id; }\n"
        )
        (project / "app.test.mjs").write_text(
            "import { test } from 'node:test';\n"
            "test('edits a task title', () => {});\n"
        )
        return project

    def test_a_suite_does_not_satisfy_the_built_check(self, tested_but_unbuilt):
        problems = _problems(tested_but_unbuilt)
        assert len(problems) == 1 and "`edit`" in problems[0]

    def test_the_two_checks_disagree_as_they_should(self, tested_but_unbuilt):
        """Not built, and yet covered - both true, and both worth saying."""
        from app.analysis.integration_checks import (
            _a_required_action_no_test_covers,
            _source_files,
        )

        files = _source_files(tested_but_unbuilt)
        built = _problems(tested_but_unbuilt)
        tested = _a_required_action_no_test_covers(files, tested_but_unbuilt)

        assert len(built) == 1 and "`edit`" in built[0], "the product does not do it"
        # `edit` is covered; `add` and `delete` are not named by this suite, so
        # the other check reports those instead - which is the point: the two
        # answer different questions about different files.
        assert not any("`edit`" in p for p in tested), "a test does name edit"

    def test_an_inline_script_in_the_page_still_counts_as_product(self, project):
        """Run 9c0fc48d kept its whole application inside the page."""
        (project / "app.js").write_text("function addTask(t) { return t; }\n")
        (project / "index.html").write_text(
            "<!doctype html><html><body>\n"
            '<script type="module">\n'
            "function editTask(id) { return id; }\n"
            "function deleteTask(id) { return id; }\n"
            "</script></body></html>\n"
        )
        assert _problems(project) == []
