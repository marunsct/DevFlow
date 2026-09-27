"""Files a sprint plan named that the workspace does not have.

Every other cross-file check in `integration_checks` decides by comparing two
files that exist. This one compares the plan against the workspace, which is the
only way to see a file that was planned and simply never written: there is no
inconsistency on disk to find, because there is nothing on disk at all.

Two consecutive runs ended on exactly that.

run-e980310b delegated "Create style.css with basic responsive CSS rules",
`index.html` linked it, and no tool call in the run ever touched the path. That
one `_broken_local_references` can prove, because the link is a second file
naming the first.

run-2ac28a2f is the version nothing could prove. Its plan named

    index.html with semantic HTML5 structure: <header>, form (#add-form) for
    task creation, unordered list container for tasks, embedded CSS

and the workspace finished with `app.js`, `app.test.js`, `package.json`,
`jest.config.cjs` and no HTML file at all - a "single-page application" with no
page. 34 tests passed, 0 failed, 0 bugs found across three test rounds, and the
milestone reviewer raised it three times until the run hit the revision limit:

    [major] correctness: No HTML file exists for the single-page application.
    A glob search of simple-to-do-list/**/*.html returned zero results.

Nothing references a file nobody wrote, so no amount of reading the workspace
finds it. The plan is the other half of the comparison.

Language- and framework-agnostic: it reads path-like tokens out of the plan's own
prose and asks the filesystem. A plan that names `Cargo.toml`, `main.go`,
`pom.xml` or `index.html` is checked the same way, and a plan that names no file
produces nothing.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Sequence

from app.tools.repository import IGNORED_DIRECTORIES

#: A path in prose: an optional leading dot, a stem, a dot, and an alphabetic
#: extension of up to eight characters - `.env.example` is a real planned
#: file. The lookbehind lets a quote, a backtick or a bracket sit in front,
#: which is how a plan usually writes one; the optional leading dot is what makes
#: `.eslintrc.json` and `.env.example` readable as the files they are.
#:
#: A single-segment dotfile - `.gitignore`, `.dockerignore` - has no extension to
#: anchor on and is not matched. Matching a bare dotted word would read half a
#: sentence as a path.
_A_PATH_IN_PROSE = re.compile(r"(?<![\w/.-])(\.?[\w-][\w./-]*\.[A-Za-z]{1,8})\b")

#: Abbreviations the pattern above cannot tell from a filename. Matched on the
#: whole token, so a real `e.g.js` would still be read as a path.
_NOT_A_FILENAME = frozenset({
    "e.g", "i.e", "etc.al", "et.al", "vs.the", "a.k.a", "no.1",
    # Suffix patterns a plan names when it means "files ending in this". Found on
    # run-a6b28314, whose plan asked for `.spec.ts` files and had `.spec.ts`
    # reported as a file nobody wrote. Structurally identical to `.env.example`,
    # which is a real file, so this is a list rather than a rule.
    ".spec.ts", ".spec.js", ".spec.mjs", ".spec.cjs", ".spec.jsx", ".spec.tsx",
    ".test.ts", ".test.js", ".test.mjs", ".test.cjs", ".test.jsx", ".test.tsx",
    ".d.ts", ".min.js", ".min.css",
})

#: A JavaScript library or platform, not a file: a capitalised single-word stem
#: followed by `.js`.
#:
#: The convention is what makes this decidable. JavaScript libraries are written
#: `Node.js`, `Vue.js`, `React.js`, `Next.js`, `D3.js`, `Three.js`, `Chart.js`,
#: `Backbone.js`; JavaScript *files* in a project are lowercase or kebab-case -
#: `app.js`, `main.js`, `task-list.js`. Nothing else is affected: `App.java`,
#: `Program.cs`, `Cargo.toml`, `Dockerfile` and `README.md` are all capitalised
#: files with other extensions, and a lowercase `d3.js` still reads as a file.
#:
#: Found by sweeping the stored sprint plans: 25 read, and a plan saying "Use
#: Node.js built-in test runner" had `Node.js` reported as a file the sprint
#: planned and nobody wrote - at the breaking tier, handed to the test round as a
#: proven defect. `Vue.js`, `Next.js`, `D3.js` and `Backbone.js` all did the same.
#:
#: The cost of being wrong the other way is small: a genuinely planned
#: `Widget.js` goes unreported, and a workspace that does contain the file is
#: silent either way, because only a missing path is ever reported.
_A_JAVASCRIPT_LIBRARY = re.compile(r"^[A-Z][A-Za-z0-9]*\.js$")

#: Extensions a planned file really has. Checked as an allowlist rather than by
#: excluding things that are not files, because the shapes that are not files are
#: unbounded and this set is not.
#:
#: The first version matched any short alphabetic tail, which read a CSS selector
#: as a filename. Found live in run-1a0d3610, where `div.error` was reported as
#:
#:     This sprint's plan names `div.error` and the workspace has no file of that
#:     name anywhere.
#:
#: at the breaking tier - the tier handed to the test round as already proven. A
#: plan describing `div.error`, `span.task-title` or `input.checkbox` would have
#: produced a blocking defect for a selector.
#:
#: Grown from `integration_checks._COLLECTED_SUFFIXES`, which is the set this
#: harness already maintains across every language it builds in, plus the
#: configuration, documentation and asset extensions a plan names and no check
#: reads. Missing an unusual extension costs a missed detection, which is the
#: safe direction: the alternative is a blocking defect for something that was
#: never a file.
_REALLY_AN_EXTENSION = frozenset({
    # Everything the cross-file checks collect.
    "html", "htm", "css", "js", "mjs", "cjs", "json", "py", "rb", "go", "rs",
    "java", "cs", "php", "ts", "tsx", "jsx", "scss", "sass", "vue", "svelte",
    "toml", "cfg", "kt", "kts", "scala", "swift", "dart", "ex", "exs", "c", "h",
    "cpp", "cc", "hpp", "m", "mm", "pl", "lua", "sql", "sh", "bash", "less",
    "pyi",
    # Configuration and metadata a plan names.
    "yml", "yaml", "ini", "env", "lock", "properties", "conf", "editorconfig",
    "gradle", "xml", "csproj", "sln", "mod", "sum", "gemspec", "cabal", "nix",
    "tf", "tfvars", "proto", "graphql", "gql", "prisma", "dockerfile",
    # Documentation.
    "md", "mdx", "rst", "txt", "adoc", "example", "template", "sample",
    # Assets a plan asks for by name.
    "svg", "png", "jpg", "jpeg", "gif", "webp", "ico", "avif", "woff", "woff2",
    "ttf", "otf", "eot", "map", "csv", "tsv", "webmanifest",
    # Languages and template formats the collected set does not reach. `ru` is
    # here because `config.ru` is a real Rack entry point and the parametrised
    # language cases caught its absence.
    "ru", "erb", "haml", "slim", "hbs", "ejs", "pug", "twig", "mustache",
    "razor", "cshtml", "vb", "fs", "fsx", "clj", "cljs", "cljc", "edn", "hs",
    "elm", "zig", "nim", "cr", "jl", "r", "groovy", "gvy", "tcl", "f90", "for",
    "pas", "ada", "asm", "s", "bat", "ps1", "psm1", "fish", "zsh", "make", "mk",
    "cmake", "bzl", "bazel", "sbt", "mill", "podspec", "gemfile", "rake",
})

#: Extensions that name a language or a format in prose far more often than a
#: file: "ES2015.js" is not a file, and neither is "HTML5.md".
_MAX_PATHS_REPORTED = 4

#: How deep to walk looking for a basename. A plan names a file, not a path into
#: someone's node_modules, so the walk prunes the same directories every other
#: check prunes.
_RUNNER_OUTPUT = frozenset({
    "node_modules", "dist", "build", "coverage", "target", "vendor",
    "__pycache__", ".pytest_cache", ".venv", "venv", "out", ".next",
})


def paths_a_plan_named(texts: Iterable[str]) -> list[str]:
    """Every path-like token the plan's prose contains, in order, deduplicated."""
    found: list[str] = []
    for text in texts:
        for token in _A_PATH_IN_PROSE.findall(str(text or "")):
            # `rstrip`, not `strip`: the leading dot is part of a dotfile's name.
            candidate = token.strip().rstrip(".,;:)")
            if not candidate or candidate.lower() in _NOT_A_FILENAME:
                continue
            if _A_JAVASCRIPT_LIBRARY.match(candidate):
                continue
            if candidate.rsplit(".", 1)[-1].lower() not in _REALLY_AN_EXTENSION:
                continue
            if candidate not in found:
                found.append(candidate)
    return found


#: Extensions that name the same thing. A plan that asks for `app.test.js` is
#: satisfied by `app.test.mjs`: the module is there, under the extension its own
#: module system requires.
#:
#: Measured on run-a6b28314. Its plan named `app.test.js`, the project built
#: `app.test.mjs`, and this check reported the planned file as never written -
#: eight times, at the breaking tier, which is the tier handed to the test round
#: as already proven. A `defect_fix` stage then tried to fix the finding by
#: rewriting `docs/sprint_plan.md` with a `python3 -c` snippet, which is refused
#: twice over: for executing code, and for writing into the workflow's own
#: directory. A false finding does not just waste a call, it aims a stage at the
#: wrong file.
#:
#: Only extensions that are interchangeable for one language. `main.js` and
#: `main.py` share a stem and are not the same file, and a plan that asked for one
#: is not answered by the other.
_THE_SAME_KIND_OF_FILE: tuple[frozenset[str], ...] = (
    frozenset({"js", "mjs", "cjs"}),
    frozenset({"ts", "mts", "cts"}),
    frozenset({"jsx", "tsx"}),
    frozenset({"yml", "yaml"}),
    frozenset({"htm", "html"}),
    frozenset({"md", "markdown"}),
)


def _interchangeable_names(candidate: str) -> set[str]:
    """Every filename that would satisfy a plan asking for `candidate`."""
    name = os.path.basename(candidate)
    if "." not in name:
        return {name}
    stem, _, extension = name.rpartition(".")
    extension = extension.lower()
    for family in _THE_SAME_KIND_OF_FILE:
        if extension in family:
            return {f"{stem}.{other}" for other in family}
    return {name}


def _every_file_in(repository_root: str) -> tuple[set[str], set[str]]:
    """Every relative path in the workspace, and every basename in it."""
    paths: set[str] = set()
    basenames: set[str] = set()
    root = os.path.abspath(repository_root)
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [
            name
            for name in subdirectories
            if name not in IGNORED_DIRECTORIES
            and name not in _RUNNER_OUTPUT
            and not name.startswith(".")
        ]
        for name in files:
            paths.add(os.path.relpath(os.path.join(directory, name), root))
            basenames.add(name)
    return paths, basenames


def files_the_plan_named_that_are_missing(
    texts: Iterable[str], repository_root: str
) -> list[str]:
    """One message per file the plan named that the workspace does not hold.

    Matched on basename as well as path, so a plan that writes `index.html` and
    a workspace that holds `todo-app/index.html` agree - the plan is prose and
    does not have to predict the project directory's name.

    Never raises: a workspace that cannot be read reports nothing, because a
    check that cannot see the files cannot say one is absent.
    """
    try:
        wanted = paths_a_plan_named(texts)
        if not wanted:
            return []
        paths, basenames = _every_file_in(repository_root)
        if not paths:
            # Nothing readable. An empty workspace and an unreadable one look
            # the same here, and reporting every planned file as missing on a
            # path error would be the loudest possible way to be wrong.
            return []
    except Exception:  # noqa: BLE001 - a check must never fail a stage
        return []

    missing: list[str] = []
    for candidate in wanted:
        # Any extension that means the same thing counts as delivered.
        if _interchangeable_names(candidate) & basenames:
            continue
        if any(path == candidate or path.endswith("/" + candidate) for path in paths):
            continue
        missing.append(candidate)
        if len(missing) >= _MAX_PATHS_REPORTED:
            break

    return [
        f"This sprint's plan names `{name}` and the workspace has no file of "
        f"that name anywhere. Nothing references it either, so no test can fail "
        f"for its absence and a passing suite says nothing about it: it was "
        f"planned and not written. Write it, or say in your report why the plan "
        f"no longer needs it."
        for name in missing
    ]


__all__ = ["files_the_plan_named_that_are_missing", "paths_a_plan_named"]
