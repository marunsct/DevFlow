"""The third hand-built DOM in a stage is refused, not noted again.

`a_dom_built_by_hand` says so and lets the write through, on the reasoning that
"a tiny stub for one function is a reasonable thing to write, and this cannot
tell that from a mock that is about to collapse". That is right the first time
and the second.

One run is the third. `specialist_testing_1` was told nine times, grew
`app.test.mjs` from 145 lines to 1,195 while being told - a `Proxy` over a
`Map` standing in for `dataset`, a `mockStorage` throwing `QUOTA_EXCEEDED`, an
`eventListeners` registry - and then spent three whole conversations debugging
the mock instead of the product. Each reached the model-call budget. The run
failed with 13.5 million tokens spent and nothing delivered.
"""

from __future__ import annotations

import pytest

from app.tools.repository import RepositoryToolError, _refuse_a_hand_built_dom_again
from app.tools.seen_content import (
    MOCK_DOM_WARNINGS_BEFORE_REFUSING,
    record_mock_dom_warning,
    times_warned_about_a_mock_dom,
)

A_MOCK = """
import { test } from 'node:test';
global.document = { getElementById: (id) => ({ innerHTML: '' }) };
test('renders', () => {});
"""

NO_MOCK = """
import { test } from 'node:test';
import { addTask } from './app.js';
test('adds', () => { addTask('milk'); });
"""


@pytest.fixture(autouse=True)
def _a_fresh_stage():
    from app.tools import seen_content

    seen_content.forget_everything()
    yield
    seen_content.forget_everything()


def test_the_first_two_are_let_through() -> None:
    """Noted, not refused - the note's own reasoning, unchanged."""
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING):
        _refuse_a_hand_built_dom_again("app.test.mjs", A_MOCK)
        record_mock_dom_warning("app.test.mjs")


def test_the_third_is_refused() -> None:
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING):
        record_mock_dom_warning("app.test.mjs")

    with pytest.raises(RepositoryToolError) as raised:
        _refuse_a_hand_built_dom_again("app.test.mjs", A_MOCK)

    assert "told twice already" in str(raised.value)


def test_the_refusal_names_a_way_out() -> None:
    """A refusal with no alternative is a stage with nothing left to do."""
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING):
        record_mock_dom_warning("app.test.mjs")

    with pytest.raises(RepositoryToolError) as raised:
        _refuse_a_hand_built_dom_again("app.test.mjs", A_MOCK)
    message = str(raised.value)

    assert "jsdom" in message
    assert "@playwright/test" in message
    assert "-D" in message
    # And the honest third option, so a stage that can do neither is not stuck.
    assert "say in your response that the UI is untested" in message


def test_a_file_that_stopped_mocking_is_written() -> None:
    """The count is about this file, and the refusal is about this content."""
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING + 3):
        record_mock_dom_warning("app.test.mjs")

    _refuse_a_hand_built_dom_again("app.test.mjs", NO_MOCK)


def test_another_file_in_the_same_stage_is_untouched() -> None:
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING + 3):
        record_mock_dom_warning("app.test.mjs")

    _refuse_a_hand_built_dom_again("other.test.mjs", A_MOCK)


def test_the_note_is_what_counts_the_warnings() -> None:
    """Counted where the model is told, not where the write happens: the
    refusal has to know how many times it was warned."""
    from app.tools.repository import _a_dom_built_by_hand_and_remember

    assert times_warned_about_a_mock_dom("app.test.mjs") == 0
    note = _a_dom_built_by_hand_and_remember("app.test.mjs", A_MOCK)

    assert "builds a browser API by hand" in note
    assert times_warned_about_a_mock_dom("app.test.mjs") == 1


def test_a_clean_test_never_counts() -> None:
    from app.tools.repository import _a_dom_built_by_hand_and_remember

    assert _a_dom_built_by_hand_and_remember("app.test.mjs", NO_MOCK) == ""
    assert times_warned_about_a_mock_dom("app.test.mjs") == 0


def test_the_edit_path_refuses_too() -> None:
    """Edits are how one run's mock grew: 145 lines to 1,195, one
    `edit_artifact` at a time."""
    import inspect

    from app.tools import repository

    source = inspect.getsource(repository._write_unless_it_changes_nothing)

    assert "_refuse_a_hand_built_dom_again" in source
