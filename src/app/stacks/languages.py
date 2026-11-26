"""One row per language: what each mechanism of the harness needs to know about it.

A deep review (2026-11-18) found about twenty mechanisms that each covered only
some languages - the test totals read from a runner's output, the image a
command runs in, the version a runtime is pinned to, the registry docs are read
from - and at least twelve lists of "folders that are not the product's code",
each a little different. Each gap was found one run at a time, when a product
in a language nobody had listed went wrong.

So each language says here, once, what every mechanism needs: its source
suffixes, its manifests and lock files, the folders its package manager fills
and its build writes, its test file names, and which of the harness's checks,
runners, runtimes, registries and images cover it. A field a language has no
answer for is a `Gap` with the reason - never left out - so a missing answer is
visible in one place, and the completeness test holds every pack's language to
a full row.

Language-specific content belongs in a pack, `app.plugins.seed` or a table like
this one; the mechanisms read it from here.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, replace
from typing import Iterable, Mapping


@dataclass(frozen=True)
class Gap:
    """A field a language has no answer for yet, and why."""

    reason: str


@dataclass(frozen=True)
class TreeReading:
    """How the code graph reads a file of this language from its syntax tree (KG.2, `app.analysis.parsed_definitions`).

    Each pattern is a tree-sitter query over the bundled grammar. A definition pattern captures the definition with the
    kind it is (`@function`, `@class`, `@method`, ...) and its name with `@name`, and may capture `@owner`, the type a
    method belongs to when the method is written outside it. An import pattern captures the text its resolver reads
    with a name starting `@import` (`@import.relative`, `@import.module`, ...); a namespace pattern captures the
    package or namespace the file declares with `@namespace`. Captures starting with `_` only constrain a match.
    """

    #: The grammar of `tree_sitter_language_pack` each suffix is read with.
    grammars: Mapping[str, str]
    #: Patterns of what the file defines, most specific first: a node two patterns match takes the first one's kind.
    definitions: tuple[str, ...]
    #: Patterns of its import statements; () when `import_graph` names the family that follows its imports.
    imports: tuple[str, ...] = ()
    #: Patterns of the package or namespace it declares, which its resolver looks imports up by.
    namespaces: tuple[str, ...] = ()
    #: The resolver of `app.analysis.import_resolvers` that turns its imports into project files; "" when
    #: `import_graph` names the family that follows them.
    resolver: str = ""
    #: Patterns of the names a file uses (KG.3, `app.analysis.name_references`), a node two patterns capture taking
    #: the more specific capture (`none`, `self`, `other`, `member`, then a bare name): `@reference` a bare name, `@reference.self` a name after the object itself (`this`, `self`),
    #: `@reference.other` a name after another receiver, `@reference.member` a name after a receiver that may be
    #: either (a language with no word for the object itself), `@reference.none` a name that is never another
    #: definition (a variable's).
    references: tuple[str, ...] = ()
    #: Which files a file uses names of without importing them: "folder" (its package is its folder), "namespace"
    #: (the files declaring a package or namespace it declares), "required" (whatever the files it requires require,
    #: once loaded) or "" (only those it imports).
    sees: str = ""


@dataclass(frozen=True)
class LanguageSupport:
    #: The name a pack's `language` uses.
    name: str
    #: Source files written in it.
    suffixes: tuple[str, ...]
    #: Its manifests and build files, as file-name globs: build configuration, not the product's behaviour.
    manifests: tuple[str, ...]
    #: Files its package manager writes to pin what it installed.
    lockfiles: tuple[str, ...]
    #: Folders a tool fills in any project in it, known by name alone: never the product's code.
    installed: tuple[str, ...]
    #: Folders a tool fills, known by a manifest beside them (file-name globs): `vendor` beside `composer.json`. The
    #: same name with no such manifest beside it is the project's own.
    installed_beside: Mapping[str, tuple[str, ...]]
    #: Folders its build writes, known by a manifest beside them: `target` beside `Cargo.toml`.
    build_output_beside: Mapping[str, tuple[str, ...]]
    #: Folders its build usually writes, skipped by name where the listings always skipped them (`dist`, `build`).
    build_output_by_name: tuple[str, ...]
    #: Patterns (regular expressions over a workspace-relative path) of a test file by its own convention.
    test_files: tuple[str, ...]
    #: What reports a name nothing defines before the tests run: a `compiler_check` checker's language, or the
    #: language service ("language_service" for TypeScript's, "pyright" for Python's).
    check: str | Gap
    #: The runners whose printed totals `sandbox` counts for it (`sandbox.RUNNERS_COUNTED`).
    test_totals: tuple[str, ...] | Gap
    #: The runtime `app.tools.runtimes` pins a project's version of (`runtimes.SUPPORTED`).
    runtime_version: str | Gap
    #: The registry `app.tools.docs` reads a package's README from.
    docs: str | Gap
    #: The toolchain whose sandbox image its commands run in when no pack names one, chosen by the command's
    #: executable: "node" for the Playwright image, else the folder under `deploy/sandbox-images/` (`image_of`).
    sandbox_toolchain: str | Gap
    #: The executables that choose `sandbox_toolchain` for a command of a project no pack set up.
    executables: tuple[str, ...]
    #: The family `app.analysis.reachability` follows imports with, which the code graph and the export checks read.
    import_graph: str | Gap
    #: The key of `app.plugins.seed.DEVELOPMENT_SERVERS` whose markers a release reads its sources for.
    development_server: str | Gap
    #: (the variable that names its package cache, that cache's folder under a home) when its toolchain keeps what
    #: an install restored under the user's home rather than in the project; () when it installs into the project.
    #: The product started as delivered, from a stranger's empty home, is pointed at the restored cache: measured on
    #: one C# run, `dotnet run` restored again from that home, with no network, failed NU1301 on a version range, and
    #: a product that started for the suite was reported as not starting in every round.
    package_cache: tuple[str, str] | Gap = Gap("not set for this language")
    #: Whether its usual start command restores the project's packages before it runs (`dotnet run`): a copy of the
    #: product started elsewhere restores again, and a version range is resolved against the package source, so the
    #: product started as delivered is given a network, as a stranger starting it has. Measured on one C# run: with
    #: none, NU1301 in every round on a product that started for the suite.
    restores_when_it_starts: bool | Gap = Gap("its usual start command runs what was built or installed")
    #: The reader of `app.analysis.resolved_packages` that lists what an install resolved (its lock file, the restore's
    #: assets or the installed packages) with the runtime each needs, for the toolchain-fit check (HK.2).
    resolved: str | Gap = Gap("no reader lists what its install resolved")
    #: Patterns (regular expressions over a test file's text) of a stand-in the test puts in place of a component - a
    #: mock, stub, fake or patched name - each with a group naming what it replaces (`name`, or a second spelling's
    #: own group) and an optional group `attr`, the member replaced on it (`app.analysis.stand_in_tests`, LF.1312).
    #: Measured: a controller test that replaced the service asserted the service's validation rule, and failed beside
    #: a product that kept the rule.
    stand_ins: tuple[str, ...] | Gap = Gap("no stand-in declarations are read in this language")
    #: Patterns over its runners' failure messages that say a test expected a refusal and got a success: a 4xx status
    #: expected where a 2xx or 3xx came (groups `expected` and `got`), or an error expected and none raised.
    refusal_not_given: tuple[str, ...] | Gap = Gap("no runner message is read for a refusal that did not come")
    #: Patterns over a test file's text of where one test begins, each with a group `name` (or `id`, a second
    #: spelling's): the test's name as its runner reports it (`app.analysis.shared_store_tests`, LF.1316). A file is read as the tests between them.
    test_starts: tuple[str, ...] | Gap = Gap("no test definitions are read in this language")
    #: Patterns over its runners' failure messages that say a count or a list came back larger than the test expected:
    #: a count's carry the groups `expected` and `got` (read as numbers, `got` the larger), a list's carry none.
    #: Measured (LF.1316): unit tests that shared one store file failed with "6 !== 1" and with six records where `[]`
    #: was expected, and five tests-only rewrites never gave each test an empty store.
    more_than_expected: tuple[str, ...] | Gap = Gap("no runner message is read for a count larger than expected")
    #: How a unit test in this language starts from an empty store of its own, in one sentence for a test's writer or
    #: fixer (LF.1316).
    fresh_store: str | Gap = Gap("no wording for an empty store per test in this language")
    #: The reader of `app.analysis.development_packages` that tells the packages its manifests declare for development
    #: only from those the product runs with, and the packages a source file imports (PQ.10).
    development_only: str | Gap = Gap("no reader tells its development-only packages apart")
    #: How the code graph reads its definitions and imports from the file's syntax tree (KG.2). Before it the graph
    #: followed imports in Python and JavaScript/TypeScript only, so a Go, Java, Kotlin, C#, Rust, Ruby or PHP fixer
    #: was told no file its handler imports, and a sliced memory held none of them.
    tree: TreeReading | Gap = Gap("no grammar reading is set for this language")
    #: Modules its interpreter runs by name (`-m`) that only check the code they are given and run none of it, so the
    #: sandbox runs them as it runs its test runners (TR.9, LF.1522). Measured over 26 runs: `-m py_compile` was
    #: refused three times as able to "execute arbitrary code".
    checking_modules: tuple[str, ...] | Gap = Gap("its interpreter runs no checking module by name")
    #: Patterns (regular expressions matched against the whole of the code its interpreter is handed on the command
    #: line, `python -c CODE`, `node -e CODE`) of code that only opens one file and prints it, or a slice of its lines:
    #: a group `path`, and optional groups `start` and `end`, the slice's bounds counted from 0 as the language counts
    #: them (`app.agents.shell_reads`, LF.1525). Such a command is a read, decided as `read_file` is. Measured on one
    #: medium run: with its reader withheld, a builder read a 593-line file five times by such code, once failing on
    #: the path, twice for the same lines.
    file_prints: tuple[str, ...] | Gap = Gap("no inline code is read as a file read in this language")
    #: Patterns over its runners' failure output that say a test's assertion was reached and failed - the test's own
    #: check, a stand-in's expectation, or a test's own failure report - as opposed to an error raised before any
    #: assertion (`app.analysis.unit_failure_side`, PA.15). Each row also matches `_ANY_ASSERTION`.
    assertion_failed: tuple[str, ...] | Gap = Gap("no runner message is read for an assertion in this language")


_NODE_INSTALLED = ("node_modules",)
_PYTHON_INSTALLED = ("__pycache__", ".venv", "venv", "site-packages", ".tox", ".mypy_cache", ".pytest_cache",
                     ".ruff_cache")
#: foo.test.ts, foo.spec.jsx, test-helpers.mjs, the underscore form Node's own runner collects (foo_test.mjs), and the
#: bare name: measured across stored workspaces, a `test.js` read as the application let the size budget count a suite
#: as product and the requirement checks read it as evidence a feature was built.
_JS_TESTS = (
    r"\.(test|spec)\.([cm]?[jt]s|[jt]sx)$",
    r"[-_](test|spec)\.([cm]?[jt]s|[jt]sx)$",
    r"(^|/)test[-_][^/]*\.([cm]?[jt]s|[jt]sx)$",
    r"(^|/)(test|spec|tests|specs)\.([cm]?[jt]s|[jt]sx)$",
)
_JVM_BESIDE = {"target": ("pom.xml",), "build": ("build.gradle", "build.gradle.kts")}
_JVM_MANIFESTS = ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
                  "gradle.properties")
_JVM_TESTS = (r"(^|/)src/test/", r"Test\.(java|kt|scala)$")
_NO_DOCS_REGISTRY = "the docs tool reads READMEs from npm, PyPI, crates.io and GitHub-hosted Go modules only"
_NO_RUNTIME_PIN = "runtimes pins node, go, java and python; the pack's sandbox image carries this toolchain's version"
_NO_IMPORT_GRAPH = ("unreached modules are found for Python and JavaScript/TypeScript only; the code graph follows its "
                    "imports through its `tree` resolver")
_NO_RESOLVED_SET = Gap("Maven and Gradle resolve while they build and keep no lock file read here, and Maven Central "
                       "states no runtime a release needs")
_INSTALLS_INTO_THE_PROJECT = "its packages are installed into the project, which the delivered copy carries"

#: A status the client is refused with, and one it is served with, as numbers (LF.1312).
_REFUSED = r"(?P<expected>4\d\d)"
_SERVED = r"(?P<got>[23]\d\d)"
#: "expected 400, got 201", "want 400 but got 201", "got 201, want 400": the wording many runners and assertion
#: libraries share, whatever the language.
_EXPECTED_GOT = (
    rf"(?i:expected|want(?:ed)?)\W{{0,4}}{_REFUSED}\b[^\n\d]{{0,20}}?(?i:but\s+)?(?i:got|was|received|actual)\W{{0,4}}{_SERVED}\b",
    rf"(?i:got|actual)\W{{0,4}}{_SERVED}\b[^\n\d]{{0,20}}?(?i:expected|want(?:ed)?)\W{{0,4}}{_REFUSED}\b",
)
_JVM_STAND_INS = (
    # `@MockitoBean private NoteService service;` - Spring's and Mockito's annotations on a field.
    r"@(?:MockBean|MockitoBean|SpyBean|MockitoSpyBean|Mock|Spy|MockkBean|MockK)\b(?:\s*\([^)]*\))?\s+"
    r"(?:(?:private|protected|public|final|static|lateinit|val|var)\s+)*(?:(?P<name>[A-Z]\w*)(?:<[^>;]*>)?\s+\w+\s*;"
    r"|\w+\s*:\s*(?P<kotlin>[A-Z]\w*))",
    r"\bmock\(\s*(?P<name>[A-Z]\w*)\.class",
    r"\bmockk<\s*(?P<name>[A-Z]\w*)",
)
_JVM_REFUSAL = (
    rf"(?:Status )?expected:\s*<{_REFUSED}> but was:\s*<{_SERVED}>",
    r"Expected [\w.$]+ to be thrown, but nothing was thrown",
    r"Expecting code to raise a throwable",
    *_EXPECTED_GOT,
)
_JS_STAND_INS = (
    r"\b(?:jest|vi)\.mock\(\s*['\"`](?P<name>[^'\"`]+)['\"`]",
    r"\b(?:jest|vi)\.spyOn\(\s*(?P<name>[\w.$]+)\s*,\s*['\"`](?P<attr>\w+)['\"`]",
    r"\bsinon\.(?:stub|replace)\(\s*(?P<name>[\w.$]+)\s*,\s*['\"`](?P<attr>\w+)['\"`]",
    r"\bmock\.method\(\s*(?P<name>[\w.$]+)\s*,\s*['\"`](?P<attr>\w+)['\"`]",
)
_JS_REFUSAL = (
    rf"Expected:?\s*{_REFUSED}\s+Received:?\s*{_SERVED}",
    rf"expected {_REFUSED} \"[^\"]*\", got {_SERVED}",
    rf"expected {_SERVED} to (?:equal|be|eql) {_REFUSED}",
    rf"{_SERVED} !== {_REFUSED}",
    r"Received function did not throw",
    r"Received promise resolved instead of rejected",
    r"Missing expected (?:exception|rejection)",
    *_EXPECTED_GOT,
)

#: "expected 1, actual 6", "expected 1 but got 6", "got 6, want 1": a count's wording many runners share (LF.1316).
_COUNT_EXPECTED_GOT = (
    r"(?i:expected|want(?:ed)?)\W{0,4}(?P<expected>\d+)\b[^\n\d]{0,20}?(?i:but\s+)?(?i:got|was|received|actual)\W{0,4}"
    r"(?P<got>\d+)\b",
    r"(?i:got|actual)\W{0,4}(?P<got>\d+)\b[^\n\d]{0,20}?(?i:expected|want(?:ed)?)\W{0,4}(?P<expected>\d+)\b",
)
#: `test('name', ...)`, `it("name", ...)`, `t.test(...)`: node:test, Jest, Vitest, Mocha.
_JS_TEST_STARTS = (r"(?m)^[ \t]*(?:await\s+)?(?:\w+\.)?(?:it|test)\s*\(\s*(?P<q>['\"`])(?P<name>.*?)(?P=q)",)
_JS_MORE_THAN_EXPECTED = (
    # node:assert's strictEqual: actual !== expected; its error's own fields.
    r"(?P<got>\d+) !== (?P<expected>\d+)",
    r"actual: (?P<got>\d+),\s*expected: (?P<expected>\d+)",
    # Jest and Vitest.
    r"Expected(?: length)?:\s*(?P<expected>\d+)\s+Received(?: length)?:\s*(?P<got>\d+)",
    # Chai.
    r"expected (?P<got>\d+) to (?:equal|be|eql) (?P<expected>\d+)",
    r"to have a length of (?P<expected>\d+) but got (?P<got>\d+)",
    r"to be empty",
    # node:assert's deepStrictEqual of a list: records added on the actual side, or an empty list expected.
    r"(?m)\+ actual - expected[\s\S]*^[ \t]*- \[\][ \t]*$",
    r"(?m)\+ actual - expected[\s\S]*^[ \t]*\+[ \t]+\{",
    r"expected: \[\]",
    r"Expected: \[\]\s+Received: \[",
    *_COUNT_EXPECTED_GOT,
)
_JS_FRESH_STORE = (
    "With `node:test`, Jest or Vitest, point the store at a fresh folder before its module is first loaded "
    "(`process.env.DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'data-'))` above the `require`, or an `await "
    "import(...)` after it for ES modules) and empty that folder in `beforeEach` (`fs.rmSync(dir, { recursive: true, "
    "force: true })`, then create it again), building any store that also keeps records in memory again there."
)
_JVM_TEST_STARTS = (
    r"@(?:Test|ParameterizedTest|RepeatedTest)\b(?:\s*\([^)]*\))?(?:\s*@\w+(?:\([^)]*\))?)*\s+"
    r"(?:(?:public|protected|private|static|final|suspend|internal)\s+)*(?:void\s+|fun\s+)?"
    r"(?:`(?P<name>[^`]+)`|(?P<id>\w+))\s*\(",
)
_JVM_MORE_THAN_EXPECTED = (
    # JUnit's assertEquals(1, list.size()).
    r"expected:\s*<(?P<expected>\d+)> but was:\s*<(?P<got>\d+)>",
    # AssertJ.
    r"Expected size:\s*<?(?P<expected>\d+)>? but was:\s*<?(?P<got>\d+)",
    r"Expecting (?:actual )?(?:to be )?empty but was",
    r"expected: <\[\]> but was: <\[",
    # Hamcrest.
    r"Expected: a collection with size <(?P<expected>\d+)>\s+but: collection size was <(?P<got>\d+)>",
    r"Expected: an empty collection\s+but:",
    *_COUNT_EXPECTED_GOT,
)
_JVM_FRESH_STORE = (
    "With JUnit 5, each test builds its store on its own folder from `@TempDir` in `@BeforeEach`; a Spring test that "
    "shares one application context points the store at a temporary folder and clears it in `@BeforeEach`, or marks "
    "the class `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)`."
)

#: PA.15: what says an assertion was reached, whatever the runner: an assertion error by name, an assertion that
#: "failed", and "expected ... got/received/but was" (the wording many assertion libraries share).
_ANY_ASSERTION = (
    r"\bAssertion(?:Error|FailedError|Exception)\b",
    r"\bassertion\b[^\n]{0,80}?\bfailed\b",
    r"(?i)\bexpected\b[^\n]{0,120}?(?:\bgot\b|\breceived\b|\bbut was\b|\bactual\b|\bto (?:be|equal|eq|eql|have|contain"
    r"|match|include|raise|throw)\b)",
)
_JS_ASSERTION = (
    *_ANY_ASSERTION,
    r"\bERR_ASSERTION\b",
    r"Expected values to be (?:strictly |loosely )?(?:deep-?)?equal",
    r"\bexpect\((?:received|actual|\w+)?\)\.",
    r"(?m)^\s*(?:Expected|Received)(?: length| value)?:\s",
    r"Received (?:function did not throw|promise resolved instead of rejected)",
    r"Missing expected (?:exception|rejection)",
)
_PYTHON_ASSERTION = (
    *_ANY_ASSERTION,
    # pytest's `E   assert ...` and its short summary's `: assert ...`; not the `>` line, which only shows where the
    # test was when an error was raised, assertion or not.
    r"(?m)(?:^E\s+|: )assert\s",
    r"\bFailed: DID NOT RAISE\b",
    # unittest's assertEqual family.
    r"\b(?:Lists|Dicts|Tuples|Sets|Sequences) differ\b",
)
_GO_ASSERTION = (
    *_ANY_ASSERTION,
    # A test's own report through `t.Errorf` or `t.Fatalf`: `server_test.go:64: ...`.
    r"(?m)(?:^|\s)\w+_test\.go:\d+: ",
    # testify.
    r"\bError Trace:",
    r"\bError:\s+(?:Not equal|Should|Expected|Received unexpected|An error is expected)",
)
_RUST_ASSERTION = (
    *_ANY_ASSERTION,
    r"assertion `[^`\n]*` failed",
    r"(?m)^\s*left: [^\n]*\n\s*right: ",
)
_JVM_ASSERTION = (
    *_ANY_ASSERTION,
    r"expected:\s*<[^\n]*> but was:\s*<",
    r"\bExpecting\b",
    r"\bComparisonFailure\b",
    # Mockito's expectations of a stand-in.
    r"\bWanted but not invoked\b",
    r"\bArgument\(s\) are different!",
)
_CSHARP_ASSERTION = (
    *_ANY_ASSERTION,
    r"\bAssert\.\w+\(\) Failure\b",
    r"\bXunit\.Sdk\.\w+Exception\b",
    r"\bNUnit\.Framework\.\w*Exception\b",
    r"\bExpected [^\n]{0,120}? to (?:be|equal|contain|have|start|end)\b",
)
_RUBY_ASSERTION = (
    *_ANY_ASSERTION,
    r"(?m)^\s*expected:? [^\n]*\n\s*got:? ",
    r"\bexpected [^\n]{0,120}? to\b",
    r"\bRSpec::Expectations::ExpectationNotMetError\b",
    r"\bMinitest::Assertion\b",
)
_PHP_ASSERTION = (
    *_ANY_ASSERTION,
    r"\bFailed asserting\b",
    # A stand-in's expectation (`$this->createMock(...)->expects(...)`).
    r"\bdoes not match expected value\b",
    r"\bExpectation failed for method\b",
)


#: KG.2: the syntax-tree readings. Definitions only for the languages whose imports `app.analysis.reachability`
#: already follows; definitions, imports and the declared namespace for the rest.
_SCRIPT_DEFINITIONS = (
    "(function_declaration name: (_) @name) @function",
    "(generator_function_declaration name: (_) @name) @function",
    "(class_declaration name: (_) @name) @class",
    "(method_definition name: (_) @name) @method",
    "(variable_declarator name: (identifier) @name value: [(arrow_function) (function_expression)]) @function",
)
_SCRIPT_REFERENCES = (
    "(member_expression object: (this) property: (property_identifier) @reference.self)",
    "(member_expression property: (property_identifier) @reference.other)",
    "(identifier) @reference",
    "(shorthand_property_identifier) @reference",
)
_JAVASCRIPT_TREE = TreeReading(
    grammars={".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript"},
    definitions=_SCRIPT_DEFINITIONS,
    references=_SCRIPT_REFERENCES,
)
_TYPESCRIPT_TREE = TreeReading(
    grammars={".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx"},
    definitions=(
        *_SCRIPT_DEFINITIONS,
        "(abstract_class_declaration name: (_) @name) @class",
        "(interface_declaration name: (_) @name) @interface",
        "(type_alias_declaration name: (_) @name) @type",
        "(enum_declaration name: (_) @name) @enum",
    ),
    references=(*_SCRIPT_REFERENCES, "(type_identifier) @reference"),
)
_PYTHON_TREE = TreeReading(
    grammars={".py": "python"},
    definitions=("(function_definition name: (_) @name) @function", "(class_definition name: (_) @name) @class"),
    references=(
        '(attribute object: (identifier) @_self (#eq? @_self "self") attribute: (identifier) @reference.self)',
        "(attribute attribute: (identifier) @reference.other)",
        "(identifier) @reference",
    ),
)
_GO_TREE = TreeReading(
    grammars={".go": "go"},
    definitions=(
        "(function_declaration name: (_) @name) @function",
        "(method_declaration receiver: (parameter_list (parameter_declaration type: [(type_identifier) @owner "
        "(pointer_type (type_identifier) @owner) (generic_type type: (type_identifier) @owner) "
        "(pointer_type (generic_type type: (type_identifier) @owner))])) name: (_) @name) @method",
        "(method_declaration name: (_) @name) @method",
        "(type_spec name: (_) @name type: (struct_type)) @struct",
        "(type_spec name: (_) @name type: (interface_type)) @interface",
        "(type_spec name: (_) @name) @type",
    ),
    imports=("(import_spec path: (_) @import)",),
    resolver="module_path",
    references=(
        "(selector_expression field: (field_identifier) @reference.member)",
        "(qualified_type name: (type_identifier) @reference.member)",
        "(identifier) @reference",
        "(type_identifier) @reference",
    ),
    sees="folder",
)
_RUST_TREE = TreeReading(
    grammars={".rs": "rust"},
    definitions=(
        "(function_item name: (_) @name) @function",
        "(function_signature_item name: (_) @name) @function",
        "(struct_item name: (_) @name) @struct",
        "(enum_item name: (_) @name) @enum",
        "(trait_item name: (_) @name) @trait",
        "(impl_item type: (_) @name) @impl",
        "(mod_item name: (_) @name) @module",
        "(type_item name: (_) @name) @type",
        "(macro_definition name: (_) @name) @macro",
    ),
    imports=(
        "(use_declaration argument: (_) @import)",
        "(mod_item !body name: (_) @import.module)",
        "(scoped_identifier) @import.path",
        "(scoped_type_identifier) @import.path",
    ),
    resolver="crate_modules",
    references=(
        "(field_expression value: (self) field: (field_identifier) @reference.self)",
        "(field_expression field: (field_identifier) @reference.other)",
        "(scoped_identifier name: (identifier) @reference.other)",
        "(identifier) @reference",
        "(type_identifier) @reference",
    ),
)
_JAVA_TREE = TreeReading(
    grammars={".java": "java"},
    definitions=(
        "(class_declaration name: (_) @name) @class",
        "(interface_declaration name: (_) @name) @interface",
        "(enum_declaration name: (_) @name) @enum",
        "(record_declaration name: (_) @name) @record",
        "(annotation_type_declaration name: (_) @name) @interface",
        "(method_declaration name: (_) @name) @method",
        "(constructor_declaration name: (_) @name) @constructor",
    ),
    imports=("(import_declaration) @import",),
    namespaces=("(package_declaration [(scoped_identifier) (identifier)] @namespace)",),
    resolver="declared_package",
    references=(
        "(method_invocation object: (this) name: (identifier) @reference.self)",
        "(field_access object: (this) field: (identifier) @reference.self)",
        "(method_invocation object: (_) name: (identifier) @reference.other)",
        "(field_access field: (identifier) @reference.other)",
        "(identifier) @reference",
        "(type_identifier) @reference",
    ),
    sees="namespace",
)
_KOTLIN_TREE = TreeReading(
    grammars={".kt": "kotlin", ".kts": "kotlin"},
    definitions=(
        "(class_declaration (type_identifier) @name) @class",
        "(object_declaration (type_identifier) @name) @object",
        "(function_declaration (simple_identifier) @name) @function",
        "(type_alias (type_identifier) @name) @type",
    ),
    imports=("(import_header) @import",),
    namespaces=("(package_header (identifier) @namespace)",),
    resolver="declared_package",
    references=(
        "(navigation_expression (this_expression) (navigation_suffix (simple_identifier) @reference.self))",
        "(navigation_suffix (simple_identifier) @reference.other)",
        "(simple_identifier) @reference",
        "(type_identifier) @reference",
    ),
    sees="namespace",
)
_CSHARP_TREE = TreeReading(
    grammars={".cs": "csharp"},
    definitions=(
        "(class_declaration name: (_) @name) @class",
        "(interface_declaration name: (_) @name) @interface",
        "(struct_declaration name: (_) @name) @struct",
        "(record_declaration name: (_) @name) @record",
        "(enum_declaration name: (_) @name) @enum",
        "(method_declaration name: (_) @name) @method",
        "(constructor_declaration name: (_) @name) @constructor",
        "(local_function_statement name: (_) @name) @function",
    ),
    imports=("(using_directive) @import",),
    namespaces=(
        "(namespace_declaration name: (_) @namespace)",
        "(file_scoped_namespace_declaration name: (_) @namespace)",
    ),
    resolver="declared_package",
    references=(
        '(member_access_expression expression: "this" name: (identifier) @reference.self)',
        "(member_access_expression name: (identifier) @reference.other)",
        "(identifier) @reference",
    ),
    sees="namespace",
)
_RUBY_TREE = TreeReading(
    grammars={".rb": "ruby"},
    definitions=(
        "(method name: (_) @name) @method",
        "(singleton_method name: (_) @name) @method",
        "(class name: (_) @name) @class",
        "(module name: (_) @name) @module",
    ),
    imports=(
        '(call method: (identifier) @_how (#eq? @_how "require_relative") '
        "arguments: (argument_list . (string (string_content) @import.relative)))",
        '(call method: (identifier) @_how (#eq? @_how "require") '
        "arguments: (argument_list . (string (string_content) @import)))",
    ),
    resolver="relative_require",
    references=(
        "(call receiver: (self) method: (identifier) @reference.self)",
        "(call receiver: (_) method: (identifier) @reference.other)",
        "(identifier) @reference",
        "(constant) @reference",
    ),
    sees="required",
)
_PHP_TREE = TreeReading(
    grammars={".php": "php"},
    definitions=(
        "(class_declaration name: (_) @name) @class",
        "(interface_declaration name: (_) @name) @interface",
        "(trait_declaration name: (_) @name) @trait",
        "(enum_declaration name: (_) @name) @enum",
        "(function_definition name: (_) @name) @function",
        "(method_declaration name: (_) @name) @method",
    ),
    imports=("(namespace_use_declaration) @import", "(qualified_name) @import.name"),
    namespaces=("(namespace_definition name: (_) @namespace)",),
    resolver="autoload_namespace",
    references=(
        '(member_call_expression object: (variable_name (name) @_self (#eq? @_self "this")) name: (name) @reference.self)',
        '(member_access_expression object: (variable_name (name) @_self (#eq? @_self "this")) name: (name) @reference.self)',
        "(member_call_expression name: (name) @reference.other)",
        "(member_access_expression name: (name) @reference.other)",
        "(scoped_call_expression name: (name) @reference.other)",
        "(variable_name (name) @reference.none)",
        "(name) @reference",
    ),
    sees="namespace",
)


#: A quoted path, and an `open` call's other arguments (a mode, an encoding).
_QUOTED_PATH = r"""(?P<q>['"])(?P<path>[^'"\n]+)(?P=q)"""
_OPEN = rf"open\(\s*{_QUOTED_PATH}(?:\s*,[^()]*)?\)"
#: `[100:250]`, `[:50]`, `[400:]`.
_PY_SLICE = r"\[\s*(?P<start>\d*)\s*:\s*(?P<end>\d*)\s*\]"
#: Python code that only prints a file or a slice of its lines. Captured on a medium run:
#: `with open('task_management_dashboard/routes.py') as f: lines=f.readlines(); print(''.join(lines[100:250]))`.
_PYTHON_FILE_PRINTS = (
    rf"""\s*with\s+{_OPEN}\s+as\s+(?P<f>\w+)\s*:\s*(?P<l>\w+)\s*=\s*(?P=f)\.readlines\(\)\s*;\s*"""
    rf"""print\(\s*(?P<j>['"])(?P=j)\.join\(\s*(?P=l){_PY_SLICE}\s*\)\s*(?:,\s*end\s*=\s*['"]['"]\s*)?\)\s*;?\s*""",
    rf"""\s*with\s+{_OPEN}\s+as\s+(?P<f>\w+)\s*:\s*print\(\s*(?P=f)\.read\(\)\s*(?:,\s*end\s*=\s*['"]['"]\s*)?\)\s*;?\s*""",
    rf"""\s*print\(\s*{_OPEN}\.read\(\)\s*(?:,\s*end\s*=\s*['"]['"]\s*)?\)\s*;?\s*""",
    rf"""\s*print\(\s*(?P<j>['"])(?P=j)\.join\(\s*{_OPEN}\.readlines\(\){_PY_SLICE}\s*\)\s*(?:,\s*end\s*=\s*['"]['"]\s*)?\)\s*;?\s*""",
)
#: `require('fs').readFileSync('app.js', 'utf8')`, or `fs.` after a `require` of it.
_JS_READ = rf"""(?:require\(\s*['"](?:node:)?fs['"]\s*\)|fs)\.readFileSync\(\s*{_QUOTED_PATH}\s*(?:,\s*['"]utf-?8['"]\s*)?\)(?:\.toString\(\))?"""
_JS_REQUIRE = r"""(?:(?:const|let|var)\s+fs\s*=\s*require\(\s*['"](?:node:)?fs['"]\s*\)\s*;\s*)?"""
#: JavaScript code that only prints a file or a slice of its lines.
_JS_FILE_PRINTS = (
    rf"""\s*{_JS_REQUIRE}console\.log\(\s*{_JS_READ}\s*\)\s*;?\s*""",
    rf"""\s*{_JS_REQUIRE}console\.log\(\s*{_JS_READ}\.split\(\s*['"]\\n['"]\s*\)\.slice\(\s*(?P<start>\d+)\s*(?:,\s*(?P<end>\d+)\s*)?\)"""
    rf"""\.join\(\s*['"]\\n['"]\s*\)\s*\)\s*;?\s*""",
)


def file_prints(executable: str) -> tuple[str, ...]:
    """The patterns of inline code that only prints a file, of each language whose interpreter is `executable`."""
    return tuple(pattern for row in LANGUAGES if executable in row.executables
                 and not isinstance(row.file_prints, Gap) for pattern in row.file_prints)


def _rows() -> tuple[LanguageSupport, ...]:
    javascript = LanguageSupport(
        name="javascript",
        suffixes=(".js", ".mjs", ".cjs", ".jsx"),
        manifests=("package.json",),
        lockfiles=("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "pnpm-lock.yml"),
        installed=_NODE_INSTALLED,
        installed_beside={},
        build_output_beside={},
        build_output_by_name=("dist", "build", ".next", ".nuxt"),
        test_files=_JS_TESTS,
        check="language_service",
        test_totals=("tap", "jest", "vitest", "playwright"),
        runtime_version="node",
        docs="npm",
        sandbox_toolchain="node",
        executables=("npm", "npx", "node", "yarn", "pnpm"),
        import_graph="script",
        tree=_JAVASCRIPT_TREE,
        development_server="javascript",
        package_cache=Gap(_INSTALLS_INTO_THE_PROJECT),
        resolved="npm",
        development_only="npm",
        stand_ins=_JS_STAND_INS,
        refusal_not_given=_JS_REFUSAL,
        test_starts=_JS_TEST_STARTS,
        more_than_expected=_JS_MORE_THAN_EXPECTED,
        assertion_failed=_JS_ASSERTION,
        fresh_store=_JS_FRESH_STORE,
        file_prints=_JS_FILE_PRINTS,
    )
    typescript = replace(
        javascript, name="typescript", suffixes=(".ts", ".tsx", ".mts", ".cts"),
        manifests=("package.json", "tsconfig.json"), executables=("tsc", "tsx"),
        development_server=Gap("its development servers are JavaScript's, read in the compiled .js"),
        tree=_TYPESCRIPT_TREE,
    )
    return (
        javascript,
        typescript,
        LanguageSupport(
            name="python",
            suffixes=(".py",),
            manifests=("pyproject.toml", "setup.cfg", "requirements*.txt", "Pipfile"),
            lockfiles=("poetry.lock",),
            installed=_PYTHON_INSTALLED,
            installed_beside={},
            build_output_beside={},
            build_output_by_name=("dist", "build"),
            test_files=(r"(^|/)test_[^/]*\.py$", r"_test\.py$"),
            check="pyright",
            test_totals=("pytest",),
            runtime_version="python",
            docs="pypi",
            sandbox_toolchain="python",
            executables=("python", "python3", "pip", "pip3", "pytest", "uv", "django-admin", "alembic"),
            import_graph="python",
            tree=_PYTHON_TREE,
            checking_modules=("py_compile",),
            file_prints=_PYTHON_FILE_PRINTS,
            development_server="python",
            package_cache=Gap(_INSTALLS_INTO_THE_PROJECT),
            resolved="python",
            development_only="python",
            stand_ins=(
                r"\bpatch\(\s*['\"](?P<name>[\w.]+)['\"]",
                r"\bpatch\.object\(\s*(?P<name>[A-Za-z_][\w.]*)\s*,\s*['\"](?P<attr>\w+)['\"]",
                r"\bsetattr\(\s*['\"](?P<name>[\w.]+)['\"]",
                r"\bsetattr\(\s*(?P<name>[A-Za-z_][\w.]*)\s*,\s*['\"](?P<attr>\w+)['\"]",
                r"\bdependency_overrides\[\s*(?P<name>[\w.]+)\s*\]",
            ),
            refusal_not_given=(
                rf"assert {_SERVED} == {_REFUSED}\b",
                rf"assert {_REFUSED} == {_SERVED}\b",
                r"DID NOT RAISE",
                *_EXPECTED_GOT,
            ),
            test_starts=(r"(?m)^[ \t]*(?:async\s+)?def\s+(?P<name>test\w*)\s*\(",),
            more_than_expected=(
                # pytest: `assert len(items) == 1`, `assert items == []`.
                r"assert (?P<got>\d+) == (?P<expected>\d+)\b",
                r"Left contains (?:\d+ )?more items?",
                r"assert \[[^\n]+\] == \[\]",
                # unittest: `assertEqual(len(items), 1)`, `assertEqual(items, [])`.
                r"AssertionError: (?P<got>\d+) != (?P<expected>\d+)\b",
                r"First list contains \d+ additional elements?",
                r"Lists differ: \[[^\n]+\] != \[\]",
                *_COUNT_EXPECTED_GOT,
            ),
            assertion_failed=_PYTHON_ASSERTION,
            fresh_store=(
                "With pytest, a fixture gives each test its own folder (`tmp_path`), sets the setting the store reads "
                "to it (`monkeypatch.setenv(\"DATA_DIR\", str(tmp_path))`, or the store's own path argument) and only "
                "then builds the store or the app, so no test reads another's records."
            ),
        ),
        LanguageSupport(
            name="go",
            suffixes=(".go",),
            manifests=("go.mod",),
            lockfiles=("go.sum",),
            installed=(),
            installed_beside={"vendor": ("go.mod",)},
            build_output_beside={},
            build_output_by_name=(),
            test_files=(r"_test\.go$",),
            check="go",
            test_totals=("go", "gotestsum"),
            runtime_version="go",
            docs="go",
            sandbox_toolchain="go",
            executables=("go", "gotestsum", "gofmt"),
            import_graph=Gap(_NO_IMPORT_GRAPH),
            tree=_GO_TREE,
            development_server=Gap("Go's standard server is a production server; `go run` is read in no source"),
            package_cache=("GOMODCACHE", "go/pkg/mod"),
            resolved="go",
            stand_ins=(
                r"\btype\s+(?P<name>(?:[mM]ock|[fF]ake|[sS]tub)\w*)\s+struct\b",
                r"\bNewMock(?P<name>[A-Z]\w*)\(",
            ),
            refusal_not_given=_EXPECTED_GOT,
            test_starts=(
                r"(?m)^func\s+(?P<name>Test\w*)\s*\(",
                r"\bt\.Run\(\s*\"(?P<name>[^\"]*)\"",
            ),
            more_than_expected=(
                # testify: assert.Len, assert.Equal(t, 1, len(items)), assert.Empty.
                r"should have (?P<expected>\d+) item\(s\), but has (?P<got>\d+)",
                r"expected:\s*(?P<expected>\d+)\s+actual\s*:\s*(?P<got>\d+)\b",
                r"Should be empty, but was",
                *_COUNT_EXPECTED_GOT,
            ),
            assertion_failed=_GO_ASSERTION,
            fresh_store=(
                "In Go, each test makes its own folder with `t.TempDir()` and builds its store on it (or sets the "
                "setting the store reads with `t.Setenv(\"DATA_DIR\", dir)` before building it)."
            ),
        ),
        LanguageSupport(
            name="rust",
            suffixes=(".rs",),
            manifests=("Cargo.toml",),
            lockfiles=("Cargo.lock",),
            installed=(),
            installed_beside={},
            build_output_beside={"target": ("Cargo.toml",)},
            build_output_by_name=("target",),
            test_files=(r"(^|/)benches/",),
            check="rust",
            test_totals=("cargo", "nextest"),
            runtime_version=Gap(_NO_RUNTIME_PIN),
            docs="crates",
            sandbox_toolchain="rust",
            executables=("cargo", "rustc", "cargo-nextest"),
            import_graph=Gap(_NO_IMPORT_GRAPH),
            tree=_RUST_TREE,
            development_server=Gap("Rust's servers are production servers; `cargo run` is read in no source"),
            package_cache=("CARGO_HOME", ".cargo"),
            resolved="cargo",
            stand_ins=(r"\b(?P<name>Mock[A-Z]\w*)::(?:new|default)\(",),
            refusal_not_given=(
                rf"left:\s*{_SERVED}\s+right:\s*{_REFUSED}\b",
                r"did not panic as expected",
                *_EXPECTED_GOT,
            ),
            test_starts=(r"#\[(?:[\w:]+::)?test\b[^\]]*\](?:\s*#\[[^\]]*\])*\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>\w+)",),
            more_than_expected=(
                # assert_eq!(items.len(), 1), assert_eq!(items, vec![]).
                r"left:\s*(?P<got>\d+)\s+right:\s*(?P<expected>\d+)\b",
                r"left:\s*\[[^\n]+\]\s+right:\s*\[\]",
                *_COUNT_EXPECTED_GOT,
            ),
            assertion_failed=_RUST_ASSERTION,
            fresh_store=(
                "In Rust, each test builds its store on its own folder from `tempfile::tempdir()` (a dev-dependency), "
                "never on a fixed path that tests running side by side share."
            ),
        ),
        LanguageSupport(
            name="java",
            suffixes=(".java",),
            manifests=_JVM_MANIFESTS,
            lockfiles=("gradle.lockfile",),
            installed=(".gradle",),
            installed_beside={},
            build_output_beside=_JVM_BESIDE,
            build_output_by_name=("target",),
            test_files=_JVM_TESTS,
            check="java",
            test_totals=("maven", "gradle"),
            runtime_version="java",
            docs=Gap(_NO_DOCS_REGISTRY),
            sandbox_toolchain="java",
            executables=("java", "javac", "mvn", "gradle"),
            import_graph=Gap(_NO_IMPORT_GRAPH),
            tree=_JAVA_TREE,
            development_server=Gap("`spring-boot:run` is a build command, read in no source"),
            package_cache=Gap("the Java pack fetches while it builds and tests, with a network (`fetches_while_building`)"),
            resolved=_NO_RESOLVED_SET,
            stand_ins=_JVM_STAND_INS,
            refusal_not_given=_JVM_REFUSAL,
            test_starts=_JVM_TEST_STARTS,
            more_than_expected=_JVM_MORE_THAN_EXPECTED,
            assertion_failed=_JVM_ASSERTION,
            fresh_store=_JVM_FRESH_STORE,
        ),
        LanguageSupport(
            name="kotlin",
            suffixes=(".kt", ".kts"),
            manifests=_JVM_MANIFESTS,
            lockfiles=("gradle.lockfile",),
            installed=(".gradle",),
            installed_beside={},
            build_output_beside=_JVM_BESIDE,
            build_output_by_name=("target",),
            test_files=_JVM_TESTS,
            check="java",
            test_totals=("maven", "gradle"),
            runtime_version="java",
            docs=Gap(_NO_DOCS_REGISTRY),
            sandbox_toolchain="java",
            executables=("kotlinc", "kotlin"),
            import_graph=Gap(_NO_IMPORT_GRAPH),
            tree=_KOTLIN_TREE,
            development_server=Gap("no pack is in Kotlin; its servers are production servers"),
            resolved=_NO_RESOLVED_SET,
            stand_ins=_JVM_STAND_INS,
            refusal_not_given=_JVM_REFUSAL,
            test_starts=_JVM_TEST_STARTS,
            more_than_expected=_JVM_MORE_THAN_EXPECTED,
            assertion_failed=_JVM_ASSERTION,
            fresh_store=_JVM_FRESH_STORE,
        ),
        LanguageSupport(
            name="csharp",
            suffixes=(".cs",),
            manifests=("*.csproj", "*.fsproj", "*.sln", "Directory.Build.props", "Directory.Packages.props",
                       "global.json", "NuGet.config"),
            lockfiles=("packages.lock.json",),
            installed=(),
            installed_beside={},
            build_output_beside={"bin": ("*.csproj", "*.fsproj"), "obj": ("*.csproj", "*.fsproj")},
            build_output_by_name=(),
            test_files=(r"Tests?\.cs$",),
            check="csharp",
            test_totals=("dotnet",),
            runtime_version=Gap(_NO_RUNTIME_PIN),
            docs=Gap(_NO_DOCS_REGISTRY),
            sandbox_toolchain="dotnet",
            executables=("dotnet",),
            import_graph=Gap(_NO_IMPORT_GRAPH),
            tree=_CSHARP_TREE,
            development_server=Gap("Kestrel is a production server; `dotnet watch` is read in no source"),
            package_cache=("NUGET_PACKAGES", ".nuget/packages"),
            resolved="nuget",
            restores_when_it_starts=True,
            stand_ins=(
                r"\bnew\s+Mock<\s*(?P<name>\w+)\s*>",
                r"\bSubstitute\.For<\s*(?P<name>\w+)\s*>",
                r"\bA\.Fake<\s*(?P<name>\w+)\s*>",
            ),
            refusal_not_given=(
                r"Expected:\s*(?P<expected>4\d\d|BadRequest|UnprocessableEntity|UnprocessableContent|Conflict|NotFound"
                r"|Unauthorized|Forbidden)\s+Actual:\s*(?P<got>[23]\d\d|OK|Created|NoContent|Accepted|Found|Redirect)\b",
                r"No exception was thrown",
                *_EXPECTED_GOT,
            ),
            test_starts=(
                r"\[(?:Fact|Theory|Test|TestMethod|TestCase)\b[^\]]*\](?:\s*\[[^\]]*\])*\s*public\s+"
                r"(?:async\s+)?(?:void|[A-Z][\w.]*(?:<[^>]*>)?)\s+(?P<name>\w+)\s*\(",
            ),
            more_than_expected=(
                # xUnit and MSTest: Assert.Equal(1, items.Count); NUnit: Assert.That(items.Count, Is.EqualTo(1)).
                r"Expected:\s*<?(?P<expected>\d+)>?\s+(?:Actual|But was):\s*<?(?P<got>\d+)>?",
                r"Assert\.(?:Single|Empty)\(\) Failure",
                r"Expected: <empty>\s+But was:",
                # FluentAssertions.
                r"to contain (?P<expected>\d+) item\(s\), but found (?P<got>\d+)",
                r"to be empty, but found",
                *_COUNT_EXPECTED_GOT,
            ),
            assertion_failed=_CSHARP_ASSERTION,
            fresh_store=(
                "With xUnit, the test class's constructor (run before each test) builds the store on a fresh folder "
                "under `Path.GetTempPath()` and `Dispose` deletes it; NUnit's `[SetUp]` and MSTest's "
                "`[TestInitialize]` do the same."
            ),
        ),
        LanguageSupport(
            name="ruby",
            suffixes=(".rb",),
            manifests=("Gemfile", "*.gemspec", "Rakefile", "config.ru", ".rspec"),
            lockfiles=("Gemfile.lock",),
            installed=(),
            installed_beside={"vendor": ("Gemfile",), ".bundle": ("Gemfile",)},
            build_output_beside={},
            build_output_by_name=(),
            test_files=(r"_spec\.rb$", r"_test\.rb$"),
            check=Gap("no checker finds an undefined name in Ruby without running it; its tests are the check"),
            test_totals=("rspec", "minitest"),
            runtime_version=Gap(_NO_RUNTIME_PIN),
            docs=Gap(_NO_DOCS_REGISTRY),
            sandbox_toolchain="ruby",
            executables=("ruby", "bundle", "gem", "rake", "rails", "rspec"),
            import_graph=Gap(_NO_IMPORT_GRAPH),
            tree=_RUBY_TREE,
            development_server="ruby",
            package_cache=Gap("not measured: where bundler keeps its gems is set by the pack's install"),
            resolved="bundler",
            stand_ins=(
                r"\b(?:instance_double|class_double|object_double)\(\s*['\"]?(?P<name>[\w:]+)",
                r"\ballow(?:_any_instance_of)?\(\s*(?P<name>[\w:.@]+)\s*\)\.to\s+receive\(\s*:(?P<attr>\w+)",
                r"\b(?P<name>[A-Z][\w:]*)\.stubs?\(?\s*:(?P<attr>\w+)",
            ),
            refusal_not_given=(
                rf"status code\D{{0,40}}{_REFUSED}\D{{0,40}}but it was\D{{0,40}}{_SERVED}",
                rf"Expected response to be a <{_REFUSED}[^>]*>, but was a <{_SERVED}",
                rf"expected:\s*{_REFUSED}\s+got:\s*{_SERVED}\b",
                r"but nothing was raised",
                *_EXPECTED_GOT,
            ),
            test_starts=(
                r"(?m)^[ \t]*(?:it|specify|scenario|test)\s*\(?\s*(?P<q>['\"])(?P<name>.*?)(?P=q)",
                r"(?m)^[ \t]*def\s+(?P<id>test_\w+)",
            ),
            more_than_expected=(
                # RSpec's eq and minitest's assert_equal.
                r"expected:\s*(?P<expected>\d+)\s+got:\s*(?P<got>\d+)\b",
                r"Expected:\s*(?P<expected>\d+)\s+Actual:\s*(?P<got>\d+)\b",
                r"expected:\s*\[\]\s+got:\s*\[",
                r"(?i:expected) \[[^\n]*\] to be empty",
                r"expected collection contained:",
                *_COUNT_EXPECTED_GOT,
            ),
            assertion_failed=_RUBY_ASSERTION,
            fresh_store=(
                "With RSpec or Minitest, `before` (or `setup`) makes a fresh folder with `Dir.mktmpdir` and points the "
                "store at it (`ENV[\"DATA_DIR\"]` set before the store is built), and `after` (or `teardown`) "
                "removes it."
            ),
        ),
        LanguageSupport(
            name="php",
            suffixes=(".php",),
            manifests=("composer.json", "phpunit.xml", "phpunit.xml.dist", "phpstan.neon"),
            lockfiles=("composer.lock",),
            installed=(),
            installed_beside={"vendor": ("composer.json",)},
            build_output_beside={},
            build_output_by_name=(),
            test_files=(r"Test\.php$",),
            check="php",
            test_totals=("phpunit",),
            runtime_version=Gap(_NO_RUNTIME_PIN),
            docs=Gap(_NO_DOCS_REGISTRY),
            sandbox_toolchain="php",
            executables=("php", "composer"),
            import_graph=Gap(_NO_IMPORT_GRAPH),
            tree=_PHP_TREE,
            development_server="php",
            package_cache=Gap("Composer installs into `vendor/` in the project, which the delivered copy carries"),
            resolved="composer",
            stand_ins=(
                r"\b(?:createMock|createStub|createPartialMock|getMockBuilder|mock|partialMock|spy)\(\s*\\?(?P<name>[\w\\]+)::class",
            ),
            refusal_not_given=(
                rf"Expected response status code \[{_REFUSED}\] but received {_SERVED}",
                rf"Failed asserting that {_SERVED} (?:is identical to|matches expected) {_REFUSED}\b",
                r"Failed asserting that exception of type \"[^\"]+\" is thrown",
                *_EXPECTED_GOT,
            ),
            test_starts=(
                r"function\s+(?P<name>test\w*)\s*\(",
                r"(?:#\[Test\]|@test\b)[\s\S]{0,200}?function\s+(?P<id>\w+)\s*\(",
                r"(?m)^[ \t]*(?:it|test)\(\s*(?P<q>['\"])(?P<name>.*?)(?P=q)",
            ),
            more_than_expected=(
                # PHPUnit's assertCount, assertSame and assertEmpty; Laravel's assertDatabaseCount.
                r"actual size (?P<got>\d+) matches expected size (?P<expected>\d+)",
                r"Failed asserting that (?P<got>\d+) (?:is identical to|matches expected) (?P<expected>\d+)\b",
                r"Failed asserting that an array is empty",
                r"expected entries count of (?P<expected>\d+)\. Entries found: (?P<got>\d+)",
                *_COUNT_EXPECTED_GOT,
            ),
            assertion_failed=_PHP_ASSERTION,
            fresh_store=(
                "With PHPUnit, `setUp()` builds the store on a fresh folder under `sys_get_temp_dir()` "
                "(`putenv(\"DATA_DIR=...\")` before it is built) and `tearDown()` removes it; with Laravel, the "
                "`RefreshDatabase` trait gives each test an empty database."
            ),
        ),
    )


LANGUAGES: tuple[LanguageSupport, ...] = _rows()


def language(name: str) -> LanguageSupport | None:
    """The row for a pack's `language`, or None."""
    return next((row for row in LANGUAGES if row.name == str(name or "").lower()), None)


#: Folders a tool fills that belong to no one language: version control, the sandbox's own caches (HOME points into
#: the workspace, see `sandbox._child_environment`) and infrastructure state.
TOOL_FOLDERS = frozenset({".git", ".hg", ".svn", ".agent-home", ".terraform"})

#: Folders a package manager or interpreter fills, in any language, known by name alone: never written by hand.
INSTALLED = frozenset({name for row in LANGUAGES for name in row.installed})

#: The one shared set of folders that are never the product's code, whatever the language: every listing, check and
#: copy starts from it and adds only what its own job needs.
NOT_THE_PRODUCT = TOOL_FOLDERS | INSTALLED

#: Folders a build usually writes, skipped by name by the listings that always skipped them.
BUILT_BY_NAME = frozenset({name for row in LANGUAGES for name in row.build_output_by_name})


def _merged(*mappings: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    merged: dict[str, tuple[str, ...]] = {}
    for mapping in mappings:
        for folder, markers in mapping.items():
            merged[folder] = tuple(dict.fromkeys((*merged.get(folder, ()), *markers)))
    return merged


#: A folder a tool fills or a build writes, known by the manifest beside it (file-name globs).
GENERATED_BESIDE: dict[str, tuple[str, ...]] = _merged(
    *(row.installed_beside for row in LANGUAGES), *(row.build_output_beside for row in LANGUAGES))


def is_generated(name: str, siblings: Iterable[str]) -> bool:
    """Whether a folder called `name`, beside files called `siblings`, is a tool's or a build's, not the project's."""
    markers = GENERATED_BESIDE.get(name)
    return bool(markers) and any(fnmatch.fnmatchcase(sibling, marker) for sibling in siblings for marker in markers)


#: Every manifest and build file, as file-name globs.
MANIFESTS = tuple(dict.fromkeys(glob for row in LANGUAGES for glob in row.manifests))
#: Every lock file, by name.
LOCKFILES = tuple(dict.fromkeys(name for row in LANGUAGES for name in row.lockfiles))
#: Every language's test file conventions, as one alternation.
TEST_FILE_PATTERNS = tuple(dict.fromkeys(pattern for row in LANGUAGES for pattern in row.test_files))


def is_manifest(relative_path: str) -> bool:
    """Whether a path names a manifest or build file of some language."""
    name = str(relative_path or "").replace("\\", "/").rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, glob) for glob in MANIFESTS)


def checking_modules(executable: str) -> frozenset[str]:
    """The modules `executable` runs by name that only check code, from each language that runs it (`checking_modules`)."""
    return frozenset(module for row in LANGUAGES if executable in row.executables
                     and not isinstance(row.checking_modules, Gap) for module in row.checking_modules)


def image_of(row: LanguageSupport) -> str | None:
    """The sandbox image a row's toolchain is built into, or None for a gap."""
    if isinstance(row.sandbox_toolchain, Gap):
        return None
    from app.stacks.packs import _sandbox

    return _sandbox.PLAYWRIGHT_IMAGE if row.sandbox_toolchain == "node" else _sandbox.built_image(row.sandbox_toolchain)


def image_for_executable(executable: str) -> str | None:
    """The image the table names for a command run by `executable`, or None when no row names that executable."""
    row = next((row for row in LANGUAGES if executable in row.executables), None)
    return image_of(row) if row is not None else None


#: Any lock file's name, for a pattern over a path.
LOCKFILE_PATTERN = "|".join(re.escape(name) for name in LOCKFILES)

__all__ = [
    "BUILT_BY_NAME", "GENERATED_BESIDE", "Gap", "INSTALLED", "LANGUAGES", "LOCKFILES", "LOCKFILE_PATTERN",
    "LanguageSupport", "MANIFESTS", "NOT_THE_PRODUCT", "TEST_FILE_PATTERNS", "TOOL_FOLDERS", "TreeReading",
    "image_for_executable",
    "image_of", "is_generated", "is_manifest", "language",
]
