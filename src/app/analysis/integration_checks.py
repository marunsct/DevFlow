"""Check that files written separately actually refer to each other.

Every specialist writes its own files and each one is defensible alone. What
no stage checks is whether they connect, and that is where this pipeline's
output keeps breaking.

Measured on run-95ca3f72, milestone 1 produced four files and three of these
defects, none of which was found by the architecture review, the security
review, the test round or the milestone review:

- `styles.css` styled `#app-placeholder`; `index.html` contained `#app`, so
  every rule in the stylesheet was dead.
- `script.js` exported `initTodoApp()` and no page loaded it - `index.html` had
  no `<script>` tag at all.
- `script.js` used `export`, while `jest.config.js` declared a CommonJS
  environment with no transform, so Jest could not parse it.

Each is a relationship between two files, so each is cheap to check and
impossible for a single-file reviewer to see. These run deterministically and
are reported as evidence to the milestone reviewer, not as a gate: a finding
here is something a person should look at, not a reason to end a run.

Nothing in this module raises. A workspace that cannot be scanned reports that
it could not be scanned.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: Directories that are never the project's own source.
_SKIP = {
    "node_modules", ".git", "dist", "build", "coverage", ".agent-home",
    "large_tool_results", "__pycache__", ".venv", "vendor",
}

#: Files whose job is configuration or testing, not application source.
_NOT_APPLICATION = re.compile(
    r"(^|[./])(jest|vite|webpack|babel|rollup|eslint|cypress|karma|tailwind)\.config\."
    r"|\.(test|spec)\.[jt]sx?$"
    # `test-contract.js` and `test_helpers.py` are tests too. Without this they
    # are read as application code, which on run-2b5def74 reported two test
    # files as orphaned scripts "nothing runs" - they are run by `node --test`.
    r"|(^|/)test[-_][^/]*\.[jt]sx?$"
    r"|(^|/)(__tests__|tests?|cypress|e2e)/"
    # Vendored and built output is not the project's own source. A
    # `vendor.min.js` that nothing imports is a bundle, not an orphan, and
    # reporting it teaches the reviewer to discount the check.
    r"|\.min\.(js|css)$"
    r"|(^|/)(vendor|dist|build|public/assets)/"
)

_ID_SELECTOR = re.compile(r"#([A-Za-z][\w-]*)")
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_INNERMOST_BLOCK = re.compile(r"\{[^{}]*\}", re.S)
_HTML_ID = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
_SCRIPT_SRC = re.compile(r"""<script[^>]*\bsrc\s*=\s*["']([^"']+)["']""", re.I)
_LINK_HREF = re.compile(r"""<link[^>]*\bhref\s*=\s*["']([^"']+)["']""", re.I)
_ESM = re.compile(r"^\s*(export\s+(default|const|function|class|\{)|import\s+.*\bfrom\b)", re.M)
_IMPORT_TARGET = re.compile(r"""(?:from|require\()\s*["']([^"']+)["']""")
#: A filename appearing anywhere in package.json, e.g. in a `scripts` command.
_SCRIPT_FILENAME = re.compile(r"([\w.-]+\.(?:js|mjs|cjs|sh))")


def _source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in {".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".json"}:
            found.append(path)
    return found


def _css_selectors_only(css: str) -> str:
    """The selector text of a stylesheet, with every declaration block removed.

    Without this, `background-color: #fafafa` reads as a selector for an
    element with id `fafafa`. Removing the innermost `{...}` repeatedly unwraps
    nested at-rules such as `@media` correctly, and leaves only what actually
    selects.
    """
    text = _CSS_COMMENT.sub(" ", css)
    while True:
        stripped = _INNERMOST_BLOCK.sub(" ", text)
        if stripped == text:
            return stripped
        text = stripped


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _dangling_id_selectors(files: list[Path], root: Path) -> list[str]:
    """Stylesheet rules that target an element id no page contains.

    Ids only. A class may legitimately be added at runtime by script, but an id
    selector that matches nothing is dead in every case.
    """
    declared: set[str] = set()
    for path in files:
        if path.suffix.lower() in {".html", ".htm"}:
            declared.update(_HTML_ID.findall(_read(path)))
        elif path.suffix.lower() in {".js", ".mjs", ".cjs"}:
            # An id the script creates counts as declared.
            declared.update(_ID_SELECTOR.findall(_read(path)))

    problems = []
    for path in files:
        if path.suffix.lower() != ".css":
            continue
        targeted = set(_ID_SELECTOR.findall(_css_selectors_only(_read(path))))
        for identifier in sorted(targeted - declared):
            problems.append(
                f"{path.relative_to(root)} styles `#{identifier}`, which no HTML "
                "element declares. The rule never applies."
            )
    return problems


def _orphaned_scripts(files: list[Path], root: Path) -> list[str]:
    """Application scripts that nothing loads or imports, as relative paths."""
    referenced: set[str] = set()
    for path in files:
        text = _read(path)
        if path.suffix.lower() in {".html", ".htm"}:
            referenced.update(Path(src).name for src in _SCRIPT_SRC.findall(text))
        elif path.suffix.lower() in {".js", ".mjs", ".cjs"}:
            for target in _IMPORT_TARGET.findall(text):
                if target.startswith("."):
                    referenced.add(Path(target).name)
                    referenced.add(Path(target).name + ".js")
        elif path.name == "package.json":
            # A script named in `scripts` is run by the package manager, which
            # is every bit as much a caller as an import is.
            referenced.update(_SCRIPT_FILENAME.findall(text))

    orphans = []
    for path in files:
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in {".js", ".mjs", ".cjs"}:
            continue
        if _NOT_APPLICATION.search(relative):
            continue
        if path.name not in referenced:
            orphans.append(relative)
    return orphans


def _unreferenced_scripts(files: list[Path], root: Path) -> list[str]:
    """The orphan finding, phrased for a reviewer."""
    return [
        f"{relative} is never loaded by a page or imported by another "
        "module. Nothing runs it."
        for relative in _orphaned_scripts(files, root)
    ]


_TOP_LEVEL_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M
)
_TOP_LEVEL_CONST_FN = re.compile(
    r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?[\(<]", re.M
)


def _redefined_instead_of_imported(files: list[Path], root: Path) -> list[str]:
    """Test files that define the application's own functions rather than import them.

    A test that reimplements what it is testing passes whatever the application
    does. It is the same defect as `expect(1 + 1).toBe(2)` wearing a much better
    disguise: the assertions are real, the logic is real, and none of it is
    connected to the product.

    Measured on run-2b5def74. `app.js` calls `init()` at module scope, so
    importing it in Node runs DOM code and throws. The testing specialist said
    so in its own header - "it cannot be directly imported in a headless Node
    environment. Instead, this test file defines the same pure logic functions
    inline" - and six tests passed against a copy. Nothing in the workflow
    noticed, because six tests did pass.

    Only fires when the test imports nothing from the application at all. A
    test that imports the real module and also defines a helper of the same
    name is doing something deliberate, and is left alone.
    """
    application: dict[str, str] = {}
    for path in files:
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts"}:
            continue
        if _NOT_APPLICATION.search(relative):
            continue
        text = _read(path)
        for match in _TOP_LEVEL_FUNCTION.finditer(text):
            application.setdefault(match.group(1), relative)
        for match in _TOP_LEVEL_CONST_FN.finditer(text):
            application.setdefault(match.group(1), relative)

    if not application:
        return []

    problems = []
    for path in files:
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts"}:
            continue
        if not _NOT_APPLICATION.search(relative):
            continue
        text = _read(path)
        # A test that reaches the application at all is not this defect.
        # Only a RELATIVE import can name the application: `node:assert/strict`
        # and a bare package specifier both contain a slash and neither is the
        # product, which is what made the first version of this check silent on
        # the very file it was written for.
        if any(t.startswith((".", "/")) for t in _IMPORT_TARGET.findall(text)):
            continue
        shared = sorted(
            {name for name in _TOP_LEVEL_FUNCTION.findall(text) if name in application}
            | {name for name in _TOP_LEVEL_CONST_FN.findall(text) if name in application}
        )
        if not shared:
            continue
        source = application[shared[0]]
        named = ", ".join(shared[:4]) + (f" and {len(shared) - 4} more" if len(shared) > 4 else "")
        problems.append(
            f"{relative} defines {named} itself and imports nothing from the "
            f"application, so it tests a copy rather than {source}. These tests "
            f"pass whatever {source} does."
        )
    return problems


def _broken_local_references(files: list[Path], root: Path) -> list[str]:
    """`<script src>` and `<link href>` pointing at files that do not exist."""
    problems = []
    for path in files:
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        text = _read(path)
        for target in _SCRIPT_SRC.findall(text) + _LINK_HREF.findall(text):
            if "//" in target or target.startswith(("data:", "#", "mailto:")):
                continue
            if not (path.parent / target).exists():
                problems.append(
                    f"{path.relative_to(root)} references `{target}`, which does "
                    "not exist in the workspace."
                )
    return problems


def _module_system_mismatch(files: list[Path], root: Path) -> list[str]:
    """ES module source under a test configuration that cannot parse it."""
    esm_sources = [
        path
        for path in files
        if path.suffix.lower() in {".js", ".mjs"}
        and not _NOT_APPLICATION.search(str(path.relative_to(root)))
        and _ESM.search(_read(path))
    ]
    if not esm_sources:
        return []

    for path in files:
        name = path.name.lower()
        if name == "package.json" and '"type"' in _read(path) and '"module"' in _read(path):
            return []
        if name.startswith("jest.config") and "transform" in _read(path):
            return []

    listed = ", ".join(sorted(str(p.relative_to(root)) for p in esm_sources)[:4])
    return [
        f"{listed} use ES module syntax, but no `jest.config.*` declares a "
        '`transform` and no `package.json` sets `"type": "module"`. Jest cannot '
        "parse these files."
    ]


#: Evidence that a particular technology is actually being used, by filename or
#: by manifest content. Deliberately coarse: it answers "is this here at all?".
_STACK_EVIDENCE: dict[str, tuple[str, ...]] = {
    "python": ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile"),
    "javascript": ("package.json",),
    "typescript": ("tsconfig.json",),
}

#: Packages that identify a technology, grouped by the stack field they answer
#: to. Grouping matters: checked flat, a JavaScript manifest depending on
#: `express` was reported as contradicting the chosen *database*.
_JS_PACKAGES: dict[str, dict[str, tuple[str, ...]]] = {
    "framework": {
        "express": ("express",),
        "nest": ("@nestjs/core",),
        "next": ("next",),
        "react": ("react",),
        "vue": ("vue",),
    },
    "database": {
        "mongodb": ("mongoose", "mongodb"),
        "postgresql": ("pg", "sequelize", "typeorm", "prisma"),
        "mysql": ("mysql", "mysql2"),
    },
    "testing_framework": {
        "jest": ("jest",),
        "mocha": ("mocha",),
        "vitest": ("vitest",),
    },
}

#: The same, for a Python requirements or project file.
_PY_PACKAGES: dict[str, dict[str, tuple[str, ...]]] = {
    "framework": {
        "fastapi": ("fastapi",),
        "django": ("django",),
        "flask": ("flask",),
    },
    "database": {
        "postgresql": ("psycopg", "psycopg2", "asyncpg"),
        "mongodb": ("pymongo", "motor"),
    },
    "testing_framework": {
        "pytest": ("pytest",),
    },
}

#: How each stack field reads in a sentence.
_FIELD_NAMES = {
    "framework": "framework",
    "database": "database",
    "testing_framework": "testing framework",
}


def _manifest_packages(files: list[Path], *names: str) -> set[str]:
    """Every package-like token named in the manifests called `names`."""
    found: set[str] = set()
    wanted = set(names)
    for path in files:
        if path.name in wanted:
            found.update(re.findall(r"[A-Za-z0-9_@/.-]+", _read(path).lower()))
    return found


def _stack_conflicts(files: list[Path], root: Path, stack: Any) -> list[str]:
    """Where the code contradicts the technology stack this run chose.

    Nothing downstream checks this. The stack is selected, reviewed, and then
    each specialist builds on whatever it inferred from its own task.

    Measured on run-64df2b20, whose selection was Python / FastAPI /
    PostgreSQL / pytest: the project directory held `package.json` with
    express, jsonwebtoken and mongoose, a jest suite, an `index.ts`, *and* a
    FastAPI `main.py`. Three languages, a MongoDB driver against a chosen
    PostgreSQL, and every test round running jest against a Python product.

    Only contradictions are reported, never absences: a stack component that
    has not been built yet is the normal state of an unfinished sprint.
    """
    if stack is None:
        return []

    problems: list[str] = []
    present = {path.name for path in files}
    manifests = {
        "javascript": _manifest_packages(files, "package.json"),
        "python": _manifest_packages(files, "requirements.txt", "pyproject.toml"),
    }

    language = str(getattr(stack, "language", "") or "")
    lowered = language.lower()
    for other, markers in _STACK_EVIDENCE.items():
        if not language or other in lowered:
            continue
        # TypeScript is JavaScript for this purpose; a tsconfig in a JS project
        # is a build choice, not a second language.
        if lowered in {"javascript", "typescript"} and other in {"javascript", "typescript"}:
            continue
        marker = next((m for m in markers if m in present), None)
        if marker is not None:
            problems.append(
                f"The chosen language is {language}, but this project contains "
                f"'{marker}', which belongs to a {other} project. Two languages in "
                "one project directory means neither one is the product."
            )

    frontend = str(getattr(stack, "frontend_framework", "") or "").lower()
    for ecosystem, table in (("javascript", _JS_PACKAGES), ("python", _PY_PACKAGES)):
        packages = manifests[ecosystem]
        if not packages:
            continue
        for field, options in table.items():
            chosen = str(getattr(stack, field, "") or "")
            if not chosen:
                continue
            chosen_lower = chosen.lower()
            for name, markers in options.items():
                if name in chosen_lower or chosen_lower in name:
                    continue
                # The frontend framework is a legitimate second framework.
                if field == "framework" and frontend and name in frontend:
                    continue
                marker = next((m for m in markers if m in packages), None)
                if marker is not None:
                    problems.append(
                        f"The chosen {_FIELD_NAMES[field]} is {chosen}, but the "
                        f"{ecosystem} manifest depends on '{marker}'. The rest of the "
                        f"product is being built against {chosen}."
                    )
    return problems


#: Files whose length is the product's size, as a brief means it. Lockfiles,
#: minified bundles and vendored code are excluded: nobody writing "maximum 500
#: lines" means a `package-lock.json`.
_COUNTED_SUFFIXES = frozenset({".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py"})
_NOT_COUNTED = re.compile(r"(^|/)(package-lock\.json|.*\.min\.(js|css))$")


def _size_report(files: list[Path], root: Path, orphans: set[str] | None = None) -> str:
    """How many lines of code this project is, per file and in total.

    Reported rather than judged. A brief that caps the product at a number of
    lines - `brief_low` says "Maximum 500 lines of code" - is a constraint no
    stage ever checked against what was built: run-18c0e34c shipped 627 lines,
    390 of them CSS, and passed every review. The reviewer has the brief and
    can compare, but only if someone counts.

    Scripts nothing loads are counted apart from the application. They are not
    the product - they are the probes and verifiers an agent left behind - and
    including them makes the one number the reviewer judges the brief against
    wrong in both directions: it can fail a product that is within its cap, and
    it can hide an overrun behind a total nobody trusts. On run-61c5a5b6 the
    application measured 901 lines against a 500-line cap, of which 443 (49%)
    were `verify-milestone.mjs` and three abandoned cleanup scripts. The real
    application was 454.
    """
    application: list[tuple[int, str]] = []
    tests: list[tuple[int, str]] = []
    stray: list[tuple[int, str]] = []
    orphans = orphans or set()
    for path in files:
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in _COUNTED_SUFFIXES or _NOT_COUNTED.search(relative):
            continue
        try:
            lines = _read(path).count("\n") + 1
        except Exception:  # noqa: BLE001 - a size report must never fail the checks
            continue
        if relative in orphans:
            stray.append((lines, relative))
            continue
        # Split, because a brief capping "lines of code" almost never means the
        # test suite - and reporting one number invites the reviewer to judge
        # the wrong thing. On run-18c0e34c the application was 631 lines and the
        # tests the round installed were 1,558 more.
        (tests if _NOT_APPLICATION.search(relative) else application).append((lines, relative))

    if not application and not tests and not stray:
        return ""
    application.sort(reverse=True)
    tests.sort(reverse=True)
    stray.sort(reverse=True)
    app_total = sum(n for n, _ in application)
    test_total = sum(n for n, _ in tests)

    listed = "\n".join(f"  {n:5d}  {name}" for n, name in application[:8])
    more = f"\n  ... and {len(application) - 8} more" if len(application) > 8 else ""
    report = (
        f"\n\nSize of the product as built. If the brief caps the size, compare "
        f"it against the application total:\n"
        f"  application: {app_total:,} lines across {len(application)} file(s)\n"
        f"{listed}{more}"
    )
    if tests:
        report += f"\n  tests: {test_total:,} lines across {len(tests)} file(s) (counted separately)"
    if stray:
        stray_total = sum(n for n, _ in stray)
        named = ", ".join(name for _, name in stray[:4])
        more = f" and {len(stray) - 4} more" if len(stray) > 4 else ""
        report += (
            f"\n  not counted: {stray_total:,} lines across {len(stray)} file(s) "
            f"nothing loads ({named}{more}). These are left-over probes, not the "
            "product; they are excluded from the application total above and "
            "should be deleted."
        )
    return report


#: npm's own placeholder, written by `npm init -y`. A project that keeps it has
#: a test script that fails by design.
_NPM_PLACEHOLDER_TEST = 'echo \\"Error: no test specified\\" && exit 1'


def _manifest_defects(files: list[Path], root: Path, stack: Any) -> list[str]:
    """Claims a manifest makes that the project does not support.

    A manifest is read by tooling, by CI and by the next person; when it
    disagrees with the project it sends all three somewhere wrong. These are the
    disagreements seen in real runs:

    - run-3da8dd91 shipped `"dependencies": {"jsdom": "^29.1.1"}` against a
      brief reading "No external dependencies beyond basic HTML/CSS/JS". The
      application itself loaded nothing - jsdom was only used by the tests - but
      the manifest declared it a runtime dependency of the product.
    - run-3da8dd91 also kept npm's `"test": "echo \"Error: no test specified\"
      && exit 1"` placeholder, the same artefact that cost run-95ca3f72 its
      entire sprint when `npm test` resolved to it.
    - run-3da8dd91's `"main": "index.js"` named a file that does not exist.
    """
    problems: list[str] = []
    for path in files:
        if path.name != "package.json":
            continue
        relative = str(path.relative_to(root))
        try:
            manifest = json.loads(_read(path))
        except (ValueError, TypeError):
            problems.append(f"{relative} is not valid JSON, so no tool can read it.")
            continue
        if not isinstance(manifest, dict):
            continue

        scripts = manifest.get("scripts") or {}
        test_script = str(scripts.get("test", ""))
        if "no test specified" in test_script and "exit 1" in test_script:
            problems.append(
                f"{relative} still has npm's placeholder test script "
                f"(`{test_script[:48]}...`), which fails by design. Anything that "
                "runs `npm test` here gets a failure that says nothing about the "
                "product."
            )

        main = str(manifest.get("main", "") or "")
        if main and not (path.parent / main).exists():
            problems.append(
                f"{relative} declares `\"main\": \"{main}\"`, and that file does "
                "not exist."
            )

        runtime = manifest.get("dependencies") or {}
        if runtime:
            testing = str(getattr(stack, "testing_framework", "") or "").lower()
            # DOM shims and test tooling. `linkedom` was added after
            # run-cbd22a34's reviewer found it declared as a production
            # dependency and this check did not - a list of known names only
            # covers the names on it, so it grows when a run shows a gap.
            known_test_packages = {
                "jsdom", "linkedom", "happy-dom", "domino",
                "jest", "mocha", "vitest", "jasmine", "karma", "ava", "tape",
                "chai", "sinon", "expect", "supertest", "nock", "msw",
                "cypress", "playwright", "puppeteer", "webdriverio", "selenium-webdriver",
                "@testing-library/dom", "@testing-library/react", "c8", "nyc",
            }
            misplaced = sorted(set(runtime) & known_test_packages)
            for package in misplaced:
                if package in testing:
                    continue
                problems.append(
                    f"{relative} lists `{package}` under `dependencies`, so it is "
                    "declared a runtime dependency of the product. It is a testing "
                    "package: it belongs in `devDependencies`, and a brief that "
                    "rules out external dependencies means the shipped product, "
                    "which this claims it is part of."
                )
    return problems


def summarise_integration(repository_root: str | Path, stack: Any = None) -> str:
    """What the files in this workspace say about each other. Never raises."""
    try:
        root = Path(repository_root).resolve()
        if not root.is_dir():
            return "The workspace could not be read, so no cross-file checks ran."
        files = _source_files(root)
    except Exception:  # noqa: BLE001 - evidence is best-effort, never fatal
        return "The workspace could not be scanned, so no cross-file checks ran."

    if not files:
        return "No HTML, CSS or JavaScript files were found to cross-check."

    try:
        problems = (
            _stack_conflicts(files, root, stack)
            + _manifest_defects(files, root, stack)
            + _dangling_id_selectors(files, root)
            + _broken_local_references(files, root)
            + _unreferenced_scripts(files, root)
            + _redefined_instead_of_imported(files, root)
            + _module_system_mismatch(files, root)
        )
    except Exception:  # noqa: BLE001
        return "The cross-file checks could not complete on this workspace."

    checked = (
        f"Cross-file checks ran over {len(files)} files: stylesheet id selectors "
        "against declared element ids, HTML script and stylesheet references "
        "against the files they name, application modules against whatever "
        "loads them, and module syntax against the test configuration."
    )
    # The same orphan set the checks above reported, so the size report and the
    # problem list cannot disagree about which files are part of the product.
    try:
        orphans = set(_orphaned_scripts(files, root))
    except Exception:  # noqa: BLE001
        orphans = set()
    sizes = _size_report(files, root, orphans)
    if not problems:
        return checked + "\n\nNo cross-file problems found." + sizes
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        checked
        + f"\n\n{len(problems)} cross-file problem(s) found. Each is a real "
        "relationship between two files, not a style preference:\n"
        + listed
        + sizes
    )


__all__ = ["summarise_integration"]
