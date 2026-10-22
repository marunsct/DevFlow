"""A testing approach whose checks never fail is refused like "manual testing".

One run's stack selector chose "Browser Console Assertions" for the product's
logic. `console.assert`, a logged line and a printed one all exit 0 whatever they
find, so the suite is green by construction and reports no counts. The harness
then appended "..., Playwright for the page", and the architect's specification
read "use console.assert and manual verification".
"""
import pytest

from app.agents.tools_models import TechnologyStack


def _stack(testing: str) -> TechnologyStack:
    return TechnologyStack(language="L", framework="F", frontend_framework="", database="",
                           testing_framework=testing, additional_tools=[])


@pytest.mark.parametrize("approach", [
    "Browser Console Assertions",
    "console.assert checks in the page",
    "Print statements comparing expected output",
    "Logging assertions to the console",
    # One run's selector, of "a lightweight custom assert harness" in the page.
    "Custom asserts",
    "A hand-written assert helper",
    # And the same thing with the word the check looked for taken out.
    "Custom harness",
    "An in-house test runner",
    "Hand-rolled testing framework",
])
def test_an_approach_that_never_fails_is_refused(approach):
    with pytest.raises(ValueError, match="is not a test runner"):
        _stack(approach)


@pytest.mark.parametrize("approach", [
    "pytest with plain assert statements",
    "node --test with node:assert",
    "Playwright, asserting on console output",
    "go test",
    "A custom harness run with node --test",
    "pytest with a simple conftest",
    # A real runner this table has never heard of, described as people do.
    "QUnit, a lightweight framework",
])
def test_a_named_runner_is_kept_whatever_it_mentions(approach):
    assert _stack(approach).testing_framework == approach


class TestTheSpecificationsTesting:
    """The same gap one stage later: the specification's `testing` section."""

    @staticmethod
    def _spec(*testing: str):
        from types import SimpleNamespace

        return SimpleNamespace(testing=list(testing))

    def test_a_person_or_a_console_assert_is_named(self):
        from app.agents.principal_architect import testing_nobody_can_run

        found = testing_nobody_can_run(self._spec(
            "Unit tests for the pure functions",
            "No test framework dependencies - use console.assert and manual verification",
            "Visually inspect the layout at 320px",
        ))
        assert found == [
            "No test framework dependencies - use console.assert and manual verification",
            "Visually inspect the layout at 320px",
        ]

    def test_ruling_them_out_is_not_planning_them(self):
        from app.agents.principal_architect import testing_nobody_can_run

        assert testing_nobody_can_run(self._spec(
            "No manual testing: every check is automated",
            "End-to-end tests replace manual verification",
            "Headless end-to-end tests assert on console errors",
        )) == []

    @pytest.mark.parametrize("entry", [
        # One run's architect, twice: each was sent back as a plan for manual
        # testing, and the third answer dropped two required sections.
        "STRATEGY: two dev-only runners. Manual testing alone is refused - a page "
        "needs a real browser, and no human runs tests here.",
        "Manual and visual checks are excluded by design - no person watches the "
        "workspace, so the only valid checks are runner-backed tests.",
        "Manual verification is not used; every check is an automated test.",
        "Visual inspection is never relied on: layout is asserted by the runner.",
        "Checks by hand are ruled out.",
    ])
    def test_ruling_them_out_after_naming_them_is_not_planning_them(self, entry):
        from app.agents.principal_architect import testing_nobody_can_run

        assert testing_nobody_can_run(self._spec(entry)) == []

    @pytest.mark.parametrize("entry", [
        "Manual verification of the layout is required before release",
        "Visually check the page at 320px; manual testing is planned for edge cases",
        "Manual testing covers the export, which is not automated yet",
    ])
    def test_a_plan_that_names_them_without_refusing_them_is_still_named(self, entry):
        from app.agents.principal_architect import testing_nobody_can_run

        assert testing_nobody_can_run(self._spec(entry)) == [entry]


@pytest.mark.parametrize("approach", [
    "None (not required for MVP)",
    "N/A - the product is small",
    "No tests for the first release",
    "Nothing; verified by the reviewer",
    "Testing not required for a 500-line app",
])
def test_declining_a_runner_in_more_words_is_still_declining_it(approach):
    """One run's selector answered "None (not required for MVP)"; the exact-match
    check let it through and the browser rewrite recorded "None (not required for
    MVP) for the logic, Playwright for the page"."""
    with pytest.raises(ValueError, match="A testing framework is required"):
        _stack(approach)


@pytest.mark.parametrize("approach", [
    "Nodeunit",
    "nose2",
    "node --test (no dependencies needed beyond the runtime)",
    "pytest; a database is not required for the tests",
])
def test_a_runner_whose_name_or_note_resembles_declining_is_kept(approach):
    assert _stack(approach).testing_framework == approach
