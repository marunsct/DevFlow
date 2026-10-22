"""A finding that breaks the product, told apart from one that is untidy.

One run's milestone reviewer read the cross-file evidence and accepted the
milestone with: "The cross-file check identified unused CSS classes; this does
not affect functionality but could be cleaned up." That is a fair reading of
dead CSS. It is the reading this split exists to stop being applied to a script
hook that does not exist - the two look alike in one bullet list and are not
alike at all. One is paint nobody sees; the other is the submit button not
working.
"""

from __future__ import annotations

import inspect

import pytest

import app.analysis.integration_checks as checks
from app.analysis.integration_checks import _BREAKS_BEHAVIOUR, _severity_of


@pytest.mark.parametrize(
    "problem",
    [
        "app.js looks for the element id `task-form`, which no HTML file declares.",
        "app.js reads the attribute `data-status`, which no HTML element sets.",
        "index.html references `./app.js`, which does not exist in the workspace.",
        "app.js exists but is empty. The page loads it and gets nothing - ",
        "package.json is not valid JSON, so no tool can read it.",
        "app.test.js defines addTask itself and calls its own copy rather than importing it.",
        "app.test.js opens fixtures.json relative to whatever directory it is run from.",
        "package.json declares no `test` script, and this project has tests.",
        "package.json still has npm's placeholder test script.",
    ],
)
def test_a_finding_that_stops_something_working(problem: str) -> None:
    assert _severity_of(problem) == "BREAKS"


@pytest.mark.parametrize(
    "problem",
    [
        "style.css styles .add-task-button and 3 more, and no page or script ever "
        "puts those classes on an element.",
        "style.css styles `#app-placeholder`, which no HTML element declares. "
        "The rule never applies.",
        "the project holds 620 lines of application code and its documents state "
        "a limit of 500.",
    ],
)
def test_a_finding_that_is_merely_untidy(problem: str) -> None:
    assert _severity_of(problem) == "untidy"


@pytest.mark.parametrize("marker", _BREAKS_BEHAVIOUR)
def test_every_marker_matches_a_message_this_module_emits(marker: str) -> None:
    """A marker that matches nothing classifies every finding as untidy, in
    silence. Guessed phrases are how that happens, so each one is checked
    against the source that produces the messages."""
    assert marker in inspect.getsource(checks), (
        f"`{marker}` appears in no message this module emits; it would never fire"
    )
