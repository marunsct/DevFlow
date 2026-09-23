"""`test.js` was product code to every check in this harness.

`classify_file` recognises `app.test.js`, `test_crud.js`, `tests/x.js`,
`foo_test.go` and a dozen other spellings. The one it did not recognise is
the plainest: a file named exactly `test.js`, `spec.js` or `tests.mjs`,
sitting at the top of a project directory.

Measured across the stored workspaces: seven products contain one, and every
one of them was classified as **application**. That is not a cosmetic
misfiling. Three consequences, each of which this harness has a check for:

* the size budget counted a whole suite as product code;
* `_a_required_action_nothing_implements` treats product files as evidence a
  feature exists, which is exactly what `eef6f55` - "a suite naming a feature
  is not the product having one" - was written to stop, reachable here by a
  different route;
* every check that skips tests, including the new storage-parsing one,
  examined a suite as though it were the product.

The risk in widening a name pattern is the other direction, so the near
misses are pinned below: `contest.js`, `latest.js`, `manifest.js` and
`protest.ts` are application files and must stay that way.
"""

from __future__ import annotations

import pytest

from app.analysis.file_kinds import classify_file, is_application, is_test


@pytest.mark.parametrize(
    "path",
    [
        "test.js", "test.mjs", "test.cjs", "test.ts", "test.jsx", "test.tsx",
        "spec.js", "spec.ts",
        "tests.js", "tests.mjs", "specs.ts",
        "todo-app/test.js",
        "simple-to-do-list-app/test.mjs",
        "a/b/spec.js",
    ],
)
def test_a_bare_test_name_is_a_test(path: str):
    assert is_test(path), f"{path} is a suite, not the product"
    assert not is_application(path)
    assert classify_file(path) == "test"


@pytest.mark.parametrize(
    "path",
    [
        # The near misses. Every one of these ends in the letters of a test
        # name and is ordinary product code.
        "contest.js", "latest.js", "manifest.js", "protest.ts", "greatest.mjs",
        "attest.js", "respec.js", "inspect.js",
        "app.js", "index.ts", "store.mjs",
        # A directory that merely starts with the letters.
        "testimonials/page.js",
    ],
)
def test_a_name_that_merely_ends_in_those_letters_is_not(path: str):
    assert not is_test(path), f"{path} is product code"
    assert is_application(path)


def test_the_spellings_that_already_worked_still_do():
    """The patterns this widening sits beside, unchanged."""
    for path in (
        "app.test.js", "app.spec.tsx", "test_crud.py", "crud_test.go",
        "tests/anything.js", "__tests__/a.js", "e2e/flow.spec.ts",
        "app-test.mjs", "test-helpers.js",
    ):
        assert is_test(path), path


def test_a_document_about_testing_is_still_prose():
    """Documents are classified before tests, and must stay that way."""
    assert classify_file("docs/testing.md") == "document"
    assert classify_file("docs/test.md") == "document"


def test_a_vendored_suite_is_vendored_not_ours():
    assert classify_file("node_modules/pkg/test.js") == "vendored"
    assert classify_file("vendor/lib/spec.js") == "vendored"
