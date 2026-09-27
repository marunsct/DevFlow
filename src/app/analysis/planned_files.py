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
            if candidate not in found:
                found.append(candidate)
    return found


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
        if os.path.basename(candidate) in basenames:
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
