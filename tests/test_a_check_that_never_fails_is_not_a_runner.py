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
])
def test_an_approach_that_never_fails_is_refused(approach):
    with pytest.raises(ValueError, match="is not a test runner"):
        _stack(approach)


@pytest.mark.parametrize("approach", [
    "pytest with plain assert statements",
    "node --test with node:assert",
    "Playwright, asserting on console output",
    "go test",
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
