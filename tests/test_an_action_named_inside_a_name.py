"""`saveEdit` is a product that can edit, and the matcher could not see it.

One run's product implements inline editing in full: a double-click
handler on `.task-title`, `saveEdit()`, `cancelEdit()`, Enter to commit,
Escape to cancel, blur to save, and `updateTask(id, { title })` underneath.
Not one of those names *starts* with `edit`, so a matcher anchored to the
start of an identifier reported the product as having no way to edit a task.

It was harmless while `edit` only entered the required set when the run's own
documents kept the word. Once the brief puts it there on every run, the gap
fires on every product that names its handlers this way - and the finding goes
to the milestone reviewer as blocking.
"""

from __future__ import annotations

from app.analysis.integration_checks import _names_the_action

EDIT = ("edit", "rename")


def test_a_name_that_starts_with_the_action_counts() -> None:
    assert _names_the_action("export function editTask(id, title) {}", EDIT)


def test_a_camel_case_boundary_counts(  ) -> None:
    """The one run shape."""
    assert _names_the_action("    function saveEdit() {", EDIT)
    assert _names_the_action("    function cancelEdit() {", EDIT)
    assert _names_the_action("btn.addEventListener('click', handleEditClick)", EDIT)


def test_a_hyphen_or_underscore_name_counts() -> None:
    assert _names_the_action('<button class="edit-btn">', EDIT)
    assert _names_the_action("def edit_task(id):", EDIT)


def test_a_word_that_merely_contains_it_does_not() -> None:
    """The reason the boundary has to be a capital after a lowercase letter:
    `credit` contains `edit` after a lowercase letter and is not a camelCase
    boundary."""
    assert not _names_the_action("const credit = balance - spent;", EDIT)
    assert not _names_the_action("function discredit(x) {}", EDIT)


def test_a_trailing_lowercase_still_refuses_it() -> None:
    """A comment saying "inline editing" is not a feature, and `editor` is a
    person or a textarea."""
    assert not _names_the_action("// Wire double-click on .task-title", EDIT)
    assert not _names_the_action("  // inline editing goes here", EDIT)
    assert not _names_the_action("const editor = document.querySelector('x');", EDIT)


def test_a_built_in_method_is_still_not_evidence() -> None:
    """`tasks.filter(t => t.id !== id)` is `Array.prototype.filter`, and it
    vouched for three dead buttons once already."""
    assert not _names_the_action("const open = tasks.filter(t => !t.done);", ("filter",))


def test_a_method_call_on_an_object_is_still_refused_at_a_boundary() -> None:
    """The `.` lookbehind guards the start-of-name shape; the camelCase shape
    must not hand back what it refuses."""
    assert not _names_the_action("arr.filter(x => x)", ("filter",))


def test_the_inflected_form_still_works_for_tests() -> None:
    """`_a_required_action_no_test_covers` asks with `inflected=True`, because
    a test is named for what it does: "edits a task"."""
    assert _names_the_action("test('edits a task', ...)", EDIT, inflected=True)
    assert _names_the_action("test('saveEdits the title', ...)", EDIT, inflected=True)


def test_the_real_product_reads_as_having_it() -> None:
    """The exact lines from one run's `app.js`."""
    product = """
      // Wire double-click on .task-title -> inline editing
      function cancelEdit() { input.replaceWith(span); }
      function saveEdit() {
        const newTasks = taskLogic.updateTask(id, { title: newValue }, tasks);
      }
      input.addEventListener('blur', saveEdit);
    """

    assert _names_the_action(product, EDIT)


def test_a_capital_that_is_not_the_word_is_not_a_boundary() -> None:
    """Real strings from real suites, and the nearest misses this matcher has.

    `persistedItems` (one run) and `completedItems` (one run) both
    contain `edIt`. The camelCase rung looks for the capitalised *word* -
    `Edit` - so neither counts, and both of those runs are correctly reported
    as having no test for editing. A looser rule would have accepted a
    variable about persistence as evidence of a feature.
    """
    assert not _names_the_action("const persistedItems = load();", EDIT)
    assert not _names_the_action("const completedItems = all.filter(t => t.done);", EDIT)
    assert not _names_the_action("let editedItems = 0;", EDIT, inflected=False)
