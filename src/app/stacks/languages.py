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
_NO_IMPORT_GRAPH = "imports are followed for Python and JavaScript/TypeScript only; definitions alone are read"
_NO_RESOLVED_SET = Gap("Maven and Gradle resolve while they build and keep no lock file read here, and Maven Central "
                       "states no runtime a release needs")
_INSTALLS_INTO_THE_PROJECT = "its packages are installed into the project, which the delivered copy carries"


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
        development_server="javascript",
        package_cache=Gap(_INSTALLS_INTO_THE_PROJECT),
        resolved="npm",
    )
    typescript = replace(
        javascript, name="typescript", suffixes=(".ts", ".tsx", ".mts", ".cts"),
        manifests=("package.json", "tsconfig.json"), executables=("tsc", "tsx"),
        development_server=Gap("its development servers are JavaScript's, read in the compiled .js"),
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
            development_server="python",
            package_cache=Gap(_INSTALLS_INTO_THE_PROJECT),
            resolved="python",
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
            development_server=Gap("Go's standard server is a production server; `go run` is read in no source"),
            package_cache=("GOMODCACHE", "go/pkg/mod"),
            resolved="go",
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
            development_server=Gap("Rust's servers are production servers; `cargo run` is read in no source"),
            package_cache=("CARGO_HOME", ".cargo"),
            resolved="cargo",
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
            development_server=Gap("`spring-boot:run` is a build command, read in no source"),
            package_cache=Gap("the Java pack fetches while it builds and tests, with a network (`fetches_while_building`)"),
            resolved=_NO_RESOLVED_SET,
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
            development_server=Gap("no pack is in Kotlin; its servers are production servers"),
            resolved=_NO_RESOLVED_SET,
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
            development_server=Gap("Kestrel is a production server; `dotnet watch` is read in no source"),
            package_cache=("NUGET_PACKAGES", ".nuget/packages"),
            resolved="nuget",
            restores_when_it_starts=True,
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
            development_server="ruby",
            package_cache=Gap("not measured: where bundler keeps its gems is set by the pack's install"),
            resolved="bundler",
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
            development_server="php",
            package_cache=Gap("Composer installs into `vendor/` in the project, which the delivered copy carries"),
            resolved="composer",
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
    "LanguageSupport", "MANIFESTS", "NOT_THE_PRODUCT", "TEST_FILE_PATTERNS", "TOOL_FOLDERS", "image_for_executable",
    "image_of", "is_generated", "is_manifest", "language",
]
