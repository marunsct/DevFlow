"""One answer to "what kind of file is this", for every consumer.

See `app.analysis.file_kinds` for why it is one module: the question used to
have two regexes that disagreed, and the drift was invisible until a number
came out wrong.
"""

from __future__ import annotations

import pytest

from app.analysis.file_kinds import classify_file, is_application, is_test


@pytest.mark.parametrize(
    "path",
    [
        "src/app.test.mjs",
        "src/app.spec.tsx",
        "src/test-helpers.mjs",
        "src/test_helpers.js",
        # Node's runner collects these two and the classifier did not know,
        # so a real test file counted against the application size budget.
        "src/app_test.mjs",
        "src/app-test.js",
        "tests/anything.mjs",
        "__tests__/anything.jsx",
        "tests/test_thing.py",
        "thing_test.py",
        "thing_test.go",
        "src/test/java/WidgetTest.java",
        "spec/widget_spec.rb",
    ],
)
def test_a_test_is_recognised(path: str) -> None:
    assert classify_file(path) == "test", path
    assert is_test(path)
    assert not is_application(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/app.js",
        "src/latest.mjs",
        "src/contest.js",
        "src/protest_banner.ts",
    ],
)
def test_application_code_is_not_mistaken_for_a_test(path: str) -> None:
    """`latest`, `contest`, `protest` all contain the word."""
    assert classify_file(path) == "application", path
    assert is_application(path)


@pytest.mark.parametrize("path", [
    "simple-to-do-list-app/jest.setup.js",
    "simple-to-do-list-app/jest.setup.sync.js",
    "app/jestSetup.js",
    "app/vitest.setup.ts",
    "app/src/setupTests.ts",
    "app/tests/global-setup.ts",
    "app/playwright.global-setup.ts",
    "app/test-setup.mjs",
])
def test_a_runner_s_setup_file_is_configuration_not_the_application(path):
    """One run's testing work order was refused `jest.setup.js` seven times as
    "product code", while its runner's config pointed at a setup file nobody
    was allowed to write."""
    from app.analysis.file_kinds import classify_file

    assert classify_file(path) in {"config", "test"}


@pytest.mark.parametrize("path", ["app/setup.js", "app/src/setupStore.js", "app/jest.js", "app/teardown.js"])
def test_a_product_file_that_merely_mentions_setup_is_still_the_application(path):
    from app.analysis.file_kinds import classify_file

    assert classify_file(path) == "application"
