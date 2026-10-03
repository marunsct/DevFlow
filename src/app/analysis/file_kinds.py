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
    # JavaScript and TypeScript: foo.test.ts, foo.spec.jsx, test-helpers.mjs,
    # and the underscore form Node's own runner collects, foo_test.mjs.
    r"|\.(test|spec)\.([cm]?[jt]s|[jt]sx)$"
    r"|[-_](test|spec)\.([cm]?[jt]s|[jt]sx)$"
    r"|(^|/)test[-_][^/]*\.([cm]?[jt]s|[jt]sx)$"
    # The bare name, which every form above assumed would never be used on
    # its own. Measured across the stored workspaces: `simple-to-do-list-app
    # /test.js` was classified as APPLICATION, so the size budget counted a
    # suite as product, and the requirement checks - which exist precisely so
    # that "a suite naming a feature is not the product having one" - could
    # read it as evidence the feature was built.
    r"|(^|/)(test|spec|tests|specs)\.([cm]?[jt]s|[jt]sx)$"
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
    # A runner's setup and teardown files: loaded by the runner before the
    # suite, never by the product. One run's testing work order was refused
    # `jest.setup.js` seven times as "product code", while its runner's config
    # pointed at a setup file nobody was allowed to write.
    # Any case: `jestSetup.js` and `setupTests.ts` are as common as the dotted
    # forms.
    r"|(?i:(^|[./])(jest|vite|vitest|mocha|karma|cypress|playwright|ava|jasmine)"
    r"[._-]?(global[._-]?)?(setup|teardown)[^/]*\.[cm]?[jt]sx?$)"
    r"|(?i:(^|/)(setup[._-]?tests?|tests?[._-]?setup|global[._-]?(setup|teardown))\.[cm]?[jt]sx?$)"
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


#: A file name that says it was written to be thrown away. Matched against the
#: name only, never the directory.
SCRATCH_NAME = re.compile(
    r"^(?:tmp|temp|scratch|debug)\d*[_.-]|^test[_-]debug"
    # The numbered form, `temp2.js` to `temp5.mjs`: one fix stage left four,
    # a test round reported a defect in the first, and a testing stage was
    # refused seven times deleting it as product code. `template.js` and
    # `tempo.js` stay out - the digits are the only thing allowed between.
    # A `debug` segment anywhere in the name: `play_debug_e2e.js`,
    # `run_debug_console.js`, `check-debug2.mjs`. One run left these beside
    # `tmp_get_tasks.js` and `temp_open_file.js`, and only the prefixed two were
    # recognised. The separator on both sides keeps `debugger.js` out.
    r"|[_.-]debug(?:\d+|[_.-])"
    # `test2.mjs`, `test4.mjs` - a numbered throwaway, which one run left
    # two of. Anchored and digit-suffixed so `app.test.js` and `test.mjs` are
    # untouched: a bare `test.mjs` is a plausible entry point, `test2` is not.
    r"|^test\d+\.[cm]?js$"
    # The suffix the delete guard tells a stage to rename a throwaway probe to
    # on its way out - see `repository._somewhere_this_rule_will_let_go_of`.
    r"|\.probe$",
    re.I,
)


def is_scratch(relative_path: str) -> bool:
    """Whether this file's name says it is a throwaway - a probe, not the product.

    Separate from `classify_file`, because a scratch script still counts as
    application code against the size budget: that is the point of reporting it.
    What this answers is narrower: is work *on* this file work on the product?
    """
    name = str(relative_path or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return bool(name) and SCRATCH_NAME.search(name) is not None


#: Extensions a file is commonly given, across languages and the documents,
#: data and configuration around them. Not a list of what is supported: a
#: caller adds the extensions the project at hand already uses, so a language
#: missing here is still recognised wherever it is in use.
FILE_EXTENSIONS = frozenset({
    # code
    "js", "mjs", "cjs", "ts", "tsx", "jsx", "py", "rb", "php", "go", "rs", "java", "kt",
    "kts", "scala", "cs", "fs", "swift", "c", "h", "cc", "cpp", "hpp", "m", "mm", "dart",
    "lua", "pl", "r", "jl", "ex", "exs", "erl", "hs", "clj", "elm", "vue", "svelte", "sql",
    "sh", "bash", "zsh", "ps1", "bat",
    # pages and styling
    "html", "htm", "css", "scss", "sass", "less",
    # data and configuration
    "json", "yaml", "yml", "toml", "ini", "cfg", "conf", "env", "xml", "csv", "tsv",
    "lock", "gradle", "properties", "tf", "proto", "graphql",
    # documents and assets
    "md", "markdown", "rst", "txt", "adoc", "svg", "png", "jpg", "jpeg", "gif", "ico", "webp",
})


def names_a_file(token: str, also: "set[str] | frozenset[str]" = frozenset()) -> bool:
    """Whether a dotted name written in prose is a file, not `object.member`.

    `store.read` and `styles.css` have the same shape, and a plan was handed
    back twice - then dispatched as not ready - because its sprint's scope
    said "task-store.mjs: createTask(), ..., store.read(), store.write()" and
    no work order "listed" `store.read`. What tells them apart is the last
    part: a file's is an extension files are given, here or in general.

    `also` is the extensions the project already uses (its work orders' files,
    its workspace), without the dot. An extension in neither is not taken for
    a file - the safe side for a check that sends work back.
    """
    name = str(token or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if "." not in name.strip("."):
        return False
    extension = name.rsplit(".", 1)[-1].lower()
    return extension in FILE_EXTENSIONS or extension in {str(e).lower().lstrip(".") for e in also}


__all__ = [
    "FILE_EXTENSIONS",
    "FileKind",
    "SCRATCH_NAME",
    "classify_file",
    "is_application",
    "is_scratch",
    "is_test",
    "names_a_file",
]
