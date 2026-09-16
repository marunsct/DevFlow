"""What kind of file is this - one answer, for every consumer.

"Is this a test?" was answered by two regexes that disagreed. `repository.py`
used `_LOOKS_LIKE_A_TEST` to protect test files from deletion;
`integration_checks.py` used `_NOT_APPLICATION` to keep them out of the size
report. Finding 92 was a third answer, written inline, which counted a
797-line `Task.test.mjs` against a 500-line application budget and would have
told the agent it was 1,033 lines over when it was 128.

The two also disagreed on Python. `_LOOKS_LIKE_A_TEST` matched `test_*.py` and
`*_test.py`; `_NOT_APPLICATION` matched neither, so every Python test file in
every run counted as application code against the declared budget. Nobody had
noticed because no Python product has reached a size review yet.

That is the cost of the same question having several answers: they drift, and
the drift is invisible until a number comes out wrong. The codebase's own
comment on an earlier instance of this says it plainly - "the two halves never
spoke".

`_NOT_APPLICATION` also conflated three different things: tests, build
configuration, and vendored output. All three are "not the application", but
they are not each other, and a checker that wants tests specifically (the size
split) had to accept config and vendored files with them. The kinds here are
separate, and `is_application` is the union everything used to approximate.

Naming conventions are per-language and deliberately open: the point of this
module is that adding Go, Rust or Java means adding a pattern here rather than
discovering, one checker at a time, that none of them knew.
"""

from __future__ import annotations

import re
from typing import Literal

FileKind = Literal["test", "config", "vendored", "document", "application"]

#: Test files, by the conventions each language actually uses.
_TEST = re.compile(
    # A directory of tests, whatever is in it.
    r"(^|/)(__tests__|tests?|e2e|spec|cypress)/"
    # JavaScript and TypeScript: foo.test.ts, foo.spec.jsx, test-helpers.mjs.
    r"|\.(test|spec)\.([cm]?[jt]s|[jt]sx)$"
    r"|(^|/)test[-_][^/]*\.([cm]?[jt]s|[jt]sx)$"
    # Python: pytest and unittest both look for these.
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.py$"
    # Go: the toolchain itself defines this one.
    r"|_test\.go$"
    # Rust: integration tests live in tests/, caught above; benches are not
    # application code either.
    r"|(^|/)benches/"
    # Java, Kotlin, Scala under Maven/Gradle layout.
    r"|(^|/)src/test/"
    r"|Test\.(java|kt|scala)$"
    # C#: xUnit and NUnit projects.
    r"|Tests?\.cs$"
    # Ruby.
    r"|_spec\.rb$"
    r"|_test\.rb$"
    # PHP.
    r"|Test\.php$",
    re.IGNORECASE,
)

#: Build, lint and tooling configuration - not the product, not a test.
_CONFIG = re.compile(
    r"(^|[./])(jest|vite|vitest|webpack|babel|rollup|esbuild|eslint|prettier"
    r"|cypress|karma|tailwind|playwright|nodemon|tsup)\.config\."
    r"|(^|/)(tsconfig|jsconfig)[^/]*\.json$"
    r"|(^|/)\.[^/]*rc(\.[a-z]+)?$"
    r"|(^|/)(setup|conftest)\.py$"
    r"|(^|/)(Makefile|Dockerfile|docker-compose\.ya?ml)$"
)

#: Dependencies and build output. Neither written nor maintained here.
_VENDORED = re.compile(
    r"\.min\.(js|css)$"
    r"|(^|/)(vendor|dist|build|out|target|node_modules|__pycache__)/"
    r"|(^|/)public/assets/"
    r"|(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.ya?ml|poetry\.lock"
    r"|Cargo\.lock|go\.sum|composer\.lock|Gemfile\.lock)$"
)

#: Prose. Read by people, counted against nothing.
_DOCUMENT = re.compile(r"\.(md|markdown|rst|txt|adoc)$", re.IGNORECASE)


def classify_file(relative_path: str) -> FileKind:
    """What this path is, from its name alone.

    Order matters. Vendored output is checked first because a bundled
    `vendor/app.test.js` is vendored, not a test this project owns, and a
    `dist/` copy of the application is not the application. Documents come
    before tests so `docs/testing.md` is prose rather than a test directory.
    """
    path = str(relative_path or "").replace("\\", "/").lstrip("./")
    if not path:
        return "application"
    if _VENDORED.search(path):
        return "vendored"
    if _DOCUMENT.search(path):
        return "document"
    if _TEST.search(path):
        return "test"
    if _CONFIG.search(path):
        return "config"
    return "application"


def is_test(relative_path: str) -> bool:
    """Whether this file is a test the project owns."""
    return classify_file(relative_path) == "test"


def is_application(relative_path: str) -> bool:
    """Whether this file is the product itself.

    The union `_NOT_APPLICATION` used to approximate by listing what it was
    not - which is why it drifted from the test check beside it.
    """
    return classify_file(relative_path) == "application"


__all__ = ["FileKind", "classify_file", "is_application", "is_test"]
