"""Catch a test file the project's runner will never collect.

run-d3965815's security specialist wrote `todo-app/app.test_xss.mjs`: a real
test file, with real assertions, for a real XSS concern. Node's test runner
collects `*.test.mjs`, `*-test.mjs`, `*_test.mjs`, `test-*.mjs`, `test.mjs` and
anything under a `test/` directory. `app.test_xss.mjs` is none of those, so
`node --test todo-app/` ran one file and reported "# tests 1" while two test
files sat in the directory.

Nothing failed. That is what makes it worth catching at the write: a test that
is not collected does not error, it is simply absent, and every later stage -
the testing round, the milestone review, the defect loop - reads a green run
that never executed it. The harness's own file classifier had the same blind
spot and counted it as application code.

A warning, not a refusal. The name is legal, the content is fine, and a project
may have its own runner configuration this cannot see. What the specialist
needs is to be told the runner will skip it while it is still looking at the
file it just wrote.
"""

from __future__ import annotations

import re

#: Node's documented default patterns, as globs reduced to what they mean for a
#: basename. https://nodejs.org/api/test.html#running-tests-from-the-command-line
_NODE_TEST_NAME = re.compile(
    r"^(?:.+[.\-_]test|test|test[-_].+)\.[cm]?js$",
    re.IGNORECASE,
)

#: Extensions Node's runner considers at all.
_NODE_SUFFIXES = (".js", ".cjs", ".mjs")

#: What makes this Node's own runner's problem: the file imports `node:test`.
#:
#: Deliberately only that. Matching a bare top-level `test(` or `describe(`
#: would flag an application module that happens to call a function named
#: `test`, and matching vitest, jest or mocha would flag files whose runner has
#: entirely different discovery patterns and its own configuration file this
#: cannot read. A warning that is wrong about a file which runs perfectly well
#: is worse than no warning.
_DECLARES_TESTS = re.compile(
    r"""from\s+['"]node:test['"]|require\(\s*['"]node:test['"]"""
)


def _under_a_test_directory(relative_path: str) -> bool:
    parts = relative_path.replace("\\", "/").split("/")[:-1]
    return any(part.lower() in {"test", "tests", "__tests__"} for part in parts)


def _renamed(stem: str) -> str:
    """The stem with any test/spec fragment taken out, ready for `.test`.

    `app.test_xss` would otherwise become `app-test_xss.test.mjs`, which names
    testing twice and reads like a mistake of its own.
    """
    cleaned = re.sub(r"[.\-_]+", "-", stem)
    cleaned = re.sub(r"(?<![a-z0-9])(test|spec)(?![a-z0-9])", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "suite"


def undiscoverable_test(relative_path: str, content: str) -> str | None:
    """Why the runner will skip this test file, or None if it will not.

    Only JavaScript, and only Node's own runner, because those are the patterns
    that are documented rather than guessed. A stack whose runner is configured
    elsewhere - a `jest.config.js`, a `vitest.config.ts` - is left alone; this
    cannot read that configuration and a wrong warning about a file that runs
    perfectly well is worse than no warning.
    """
    path = relative_path.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    if not name.lower().endswith(_NODE_SUFFIXES):
        return None
    if not content or not _DECLARES_TESTS.search(content):
        return None
    if _under_a_test_directory(path) or _NODE_TEST_NAME.match(name):
        return None
    stem, suffix = name.rsplit(".", 1)
    suggestion = f"{_renamed(stem)}.test.{suffix}"
    return (
        f"This file declares tests, and `node --test` will not collect it: the "
        f"name '{name}' matches none of the patterns it looks for "
        f"(*.test.{suffix}, *-test.{suffix}, *_test.{suffix}, test-*.{suffix}, "
        f"test.{suffix}, or anything under a test/ directory). It will not "
        f"fail - it will simply never run, and every later stage will read a "
        f"green result that did not include it. Rename it to "
        f"'{suggestion}', or move it into a test/ directory."
    )


__all__ = ["undiscoverable_test"]
