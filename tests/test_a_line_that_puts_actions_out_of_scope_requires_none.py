"""A line that names actions only to put them out of scope requires none of them.

Measured on one run, whose release was held as "the brief is not delivered"
for `search` and `filter`, read from a tool's replacement criteria: "... or
search/filter/pagination enters scope. None of these is in the current
acceptance criteria."
"""

from __future__ import annotations

from app.analysis.integration_checks import _actions_required_in


def test_replacement_criteria_and_out_of_scope_lines_require_nothing():
    text = (
        "- **Replacement criteria:** Move to SQLite when notes.json exceeds 2 MB; or search/filter/pagination "
        "enters scope. None of these is in the current acceptance criteria.\n"
        "- Acceptance criteria: sort, search and export are out of scope for this release.\n"
    )

    assert _actions_required_in(text, {}) == {}


def test_a_criterion_that_lists_actions_still_requires_them():
    found = _actions_required_in("- Acceptance criteria: a user can add, edit and delete notes.\n", {})

    assert {"add", "edit", "delete"} <= set(found)
