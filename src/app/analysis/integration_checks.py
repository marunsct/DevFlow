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

from app.analysis.file_kinds import is_application, is_test

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


#: What language a source file belongs to. Only languages whose projects carry
#: their own manifest and their own runner, because that is what makes sharing a
#: directory a problem rather than a preference.
_LANGUAGE_OF: dict[str, str] = {
    ".py": "Python", ".rb": "Ruby", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".cs": "C#", ".php": "PHP",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
}
_MANIFEST_OF: dict[str, str] = {
    "package.json": "JavaScript", "requirements.txt": "Python",
    "pyproject.toml": "Python", "Pipfile": "Python", "Gemfile": "Ruby",
    "go.mod": "Go", "Cargo.toml": "Rust", "pom.xml": "Java",
}


_COLLECTED_SUFFIXES = frozenset({
    ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".json",
    ".py", ".rb", ".go", ".rs", ".java", ".cs", ".php", ".ts", ".tsx", ".jsx",
    ".scss", ".sass", ".vue", ".svelte", ".toml", ".cfg",
})


def _source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP for part in path.relative_to(root).parts):
            continue
        # Web files plus every language whose projects carry their own manifest
        # and runner. It was web-only, which made every cross-file check blind
        # on a product with a Python or Go backend - and `brief_medium` asks for
        # exactly that. Each check filters this list by the suffixes it
        # understands, so widening the collection adds files without changing
        # what any existing check looks at.
        if path.suffix.lower() in _COLLECTED_SUFFIXES or path.name in _MANIFEST_OF:
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


_CLASS_SELECTOR = re.compile(r"\.([A-Za-z_][\w-]*)")
_HTML_CLASS = re.compile(r"""\bclass\s*=\s*["']([^"']+)["']""")


_DOC_COMMAND = re.compile(
    r"`(?:node|python3?|bash|sh)\s+([\w./-]+\.(?:js|mjs|cjs|py|sh))`"
)


def _documented_commands_that_cannot_run(files: list[Path], root: Path, docs: Path) -> list[str]:
    """Documentation telling a reader to run a file the project does not have.

    A document is the one artefact nobody executes, so a wrong instruction in it
    survives every test round and reaches whoever tries to use the product.

    Measured on run-cbb1a5fc, whose `docs/deployment.md` said "Run with
    `node server.js`, then open http://localhost:3000" for a product whose
    files are `app.js`, `app.test.mjs`, `index.html`, `package.json` and
    `style.css`. Four milestone reviews read that document and none tried the
    command. run-3da8dd91 shipped the same shape - a README citing
    `npm run build-static`, which did not exist.

    Only a bare filename in a code span, so prose about a hypothetical server
    and a command with a real path elsewhere are both left alone.
    """
    if not docs.is_dir():
        return []
    present = {p.name for p in files} | {str(p.relative_to(root)) for p in files}

    problems = []
    for document in sorted(docs.glob("*.md")):
        text = _read(document)
        missing = sorted({
            name for name in _DOC_COMMAND.findall(text)
            if Path(name).name not in present and name not in present
        })
        if not missing:
            continue
        listed = ", ".join(f"`{name}`" for name in missing[:3])
        problems.append(
            f"docs/{document.name} tells a reader to run {listed}, and no such "
            "file exists in this project. A document is the one artefact nobody "
            "executes, so the instruction survives every test round and reaches "
            "whoever tries to use the product."
        )
    return problems


def _dangling_class_selectors(files: list[Path], root: Path) -> list[str]:
    """Stylesheet rules for a class nothing ever puts on an element.

    Unlike an id, a class is often added at runtime - so this counts any
    mention of the name anywhere in the scripts, not only a `classList.add`.
    A rule survives if the word appears at all; it is reported only when no
    page and no script contains it in any form.

    Measured on run-da6c5e19's second sprint, where the reviewer found this by
    reading: `#filters button.active` was styled, `init()` never added the
    class, and the filter buttons gave no indication of which view was
    selected. `.task-text` and `.empty-message` were styled and never used at
    all. Real defects, found by one careful read of three files against each
    other - which is the kind of thing worth not depending on.
    """
    used: set[str] = set()
    for path in files:
        suffix = path.suffix.lower()
        if suffix in {".html", ".htm"}:
            text = _read(path)
            for attribute in _HTML_CLASS.findall(text):
                used.update(attribute.split())
        elif suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}:
            # Any occurrence of the bare word counts: a class may be built into
            # a template string, a variable, or a `classList.toggle`.
            used.update(re.findall(r"[A-Za-z_][\w-]*", _read(path)))

    problems = []
    for path in files:
        if path.suffix.lower() not in {".css", ".scss", ".sass"}:
            continue
        targeted = set(_CLASS_SELECTOR.findall(_css_selectors_only(_read(path))))
        dead = sorted(name for name in targeted if name not in used)
        if not dead:
            continue
        listed = ", ".join(f".{name}" for name in dead[:4])
        more = f" and {len(dead) - 4} more" if len(dead) > 4 else ""
        problems.append(
            f"{path.relative_to(root)} styles {listed}{more}, and no page or "
            "script ever puts those classes on an element. Either the rule is "
            "dead, or the code that was meant to apply it is missing - on one "
            "run that was a filter bar whose selected button never looked "
            "selected."
        )
    return problems


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


#: `document.getElementById("x")`, and `#x` inside a querySelector string.
_JS_BY_ID = re.compile(r"""getElementById\s*\(\s*["']([A-Za-z][\w-]*)["']""")
_JS_QUERY = re.compile(r"""querySelector(?:All)?\s*\(\s*["']([^"']+)["']""")

#: An id the script creates for itself, which no page needs to declare.
_JS_ASSIGNS_ID = re.compile(
    r"""\.id\s*=\s*["']([A-Za-z][\w-]*)["']"""
    r"""|setAttribute\(\s*["']id["']\s*,\s*["']([A-Za-z][\w-]*)["']"""
)

#: `element.dataset.status` - which reads the HTML attribute `data-status`.
_JS_DATASET = re.compile(r"""\.dataset\.([A-Za-z][\w]*)""")
_JS_ASSIGNS_DATASET = re.compile(r"""\.dataset\.([A-Za-z][\w]*)\s*=""")
_HTML_DATA_ATTR = re.compile(r"""\bdata-([A-Za-z][\w-]*)\s*=""")
_JS_DATA_SELECTOR = re.compile(r"""\[\s*data-([A-Za-z][\w-]*)""")


def _camel_to_dashed(name: str) -> str:
    """`dataset.taskId` reads the attribute `data-task-id`. That is the rule."""
    return re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), name)


def _hooks_javascript_reaches_for(files: list[Path], root: Path) -> list[str]:
    """Element ids and data attributes the script uses that no page declares.

    The counterpart to `_dangling_id_selectors`, on the side that actually
    breaks the product. A stylesheet targeting a missing id is dead paint; a
    script targeting a missing id is a feature that does nothing, and it throws
    no error - `getElementById` returns null, the usual `if (!el) return;`
    swallows it, and every test of the module's pure functions still passes.

    Measured on run-499c771a, the first run of this harness to reach `complete`.
    Its `app.js` did

        document.getElementById("task-form")

    while `index.html` declared `id="add-task-form"`, so the submit handler was
    never attached and no task could be added. Its `filterCurrent()` read
    `filterBtn.dataset.status` from buttons that carried no `data-status`, so
    the filter was always `undefined` and the list rendered nothing. The
    architecture review, the security review, three passing tests and the
    milestone review all accepted it, because the tests exercised `addTask`
    and `loadTasks` directly and nothing exercised the two files together.

    Only runs when the project has an HTML file that declares at least one id.
    A React or Vue project builds its DOM from templates this cannot read, and
    a script-only page declares its own ids as it goes; flagging either would
    be noise.
    """
    pages = [path for path in files if path.suffix.lower() in {".html", ".htm"}]
    declared_ids: set[str] = set()
    declared_data: set[str] = set()
    for path in pages:
        text = _read(path)
        declared_ids.update(_HTML_ID.findall(text))
        declared_data.update(_HTML_DATA_ATTR.findall(text))
    if not declared_ids:
        return []

    problems: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".js", ".mjs", ".cjs"} or is_test(str(path)):
            continue
        text = _read(path)
        made_here = {
            name for pair in _JS_ASSIGNS_ID.findall(text) for name in pair if name
        }
        wanted = set(_JS_BY_ID.findall(text))
        for selector in _JS_QUERY.findall(text):
            wanted.update(_ID_SELECTOR.findall(selector))
        for identifier in sorted(wanted - declared_ids - made_here):
            problems.append(
                f"{path.relative_to(root)} looks for the element id "
                f"`{identifier}`, which no HTML file declares. "
                "`getElementById` returns null and the code around it does "
                "nothing, silently."
            )

        set_here = set(_JS_ASSIGNS_DATASET.findall(text))
        read_here = {
            _camel_to_dashed(name)
            for name in set(_JS_DATASET.findall(text)) - set_here
        }
        for selector in _JS_QUERY.findall(text):
            read_here.update(_JS_DATA_SELECTOR.findall(selector))
        for attribute in sorted(read_here - declared_data):
            problems.append(
                f"{path.relative_to(root)} reads the attribute "
                f"`data-{attribute}`, which no HTML element sets. It is "
                "`undefined` every time."
            )
    return problems


#: Node's own default patterns, as a basename test. Verified by running Node
#: over six names rather than read off the documentation: the prefix form takes
#: a hyphen, so `test-add.mjs` is collected and `test_add.mjs` is not.
_NODE_COLLECTS = re.compile(r"^(?:.+[.\-_]test|test|test-.+)\.[cm]?js$", re.IGNORECASE)

#: Runners whose discovery is decided by their own configuration file, which
#: this cannot read. Saying anything about those would be a guess.
_RUNNERS_WITH_THEIR_OWN_CONFIG = ("jest", "vitest", "mocha", "ava", "tap", "playwright")


def _tests_the_project_never_runs(files: list[Path], root: Path) -> list[str]:
    """Test files the project's own `npm test` will not execute.

    Decided by the manifest, not by a convention: `scripts.test` says what runs,
    and everything `classify_file` calls a test and that command does not reach
    has never executed once.

    run-04576307 reached its third milestone round with seven test files -
    `app.test.mjs` and six standalone assertion scripts named `test_add_task.mjs`,
    `test_delete_task.mjs`, `test_edit_task.mjs`, `test_filter_tasks.mjs`,
    `test_persistence.mjs` and `test_toggle_task.mjs`, 3,845 bytes of real
    assertions. Its `scripts.test` is `node --test`, whose prefix pattern is
    `test-*`, so `node --test .` reported `# tests 1`. The cross-file checks
    reported no problems and the size report described "tests: 207 lines across
    7 file(s)".

    A false green is worse than a red: the run does not merely lack the
    coverage, every stage after it reads a passing suite as evidence the
    product works.

    Only `node --test`. Jest, Vitest and Mocha decide discovery in their own
    configuration, which this cannot read, and a wrong claim about a suite that
    runs perfectly well would be worse than no claim.
    """
    problems: list[str] = []
    for manifest in files:
        if manifest.name != "package.json":
            continue
        try:
            scripts = (json.loads(_read(manifest)) or {}).get("scripts") or {}
        except Exception:  # noqa: BLE001 - a broken manifest is reported elsewhere
            continue
        command = str(scripts.get("test") or "")
        if "node --test" not in command:
            continue
        if any(runner in command for runner in _RUNNERS_WITH_THEIR_OWN_CONFIG):
            continue
        project = manifest.parent
        stranded = [
            path
            for path in files
            if path.parent == project
            and path.suffix.lower() in {".js", ".mjs", ".cjs"}
            and is_test(str(path.relative_to(root)))
            and not _NODE_COLLECTS.match(path.name)
        ]
        if not stranded:
            continue
        listed = ", ".join(sorted(path.name for path in stranded))
        problems.append(
            f"{manifest.relative_to(root)} runs `{command}`, which does not "
            f"collect {listed}. Those files have never executed, and a passing "
            "suite is being read as evidence they did. Node's patterns are "
            "*.test.js, *-test.js, *_test.js, test-*.js, test.js, or anything "
            "under a test/ directory - note the prefix form takes a hyphen."
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
        if (not is_application(relative)):
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


_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.S | re.I)

#: Below this an inline script is a bootstrap line or an analytics snippet, not
#: the application. Above it, it is the product and nothing can test it.
_EMBEDDED_APPLICATION_LINES = 30


def _languages_sharing_a_directory(files: list[Path], root: Path) -> list[str]:
    """Directories holding source from two languages at once.

    A directory is what a manifest and a test runner address. Two languages in
    one means neither runner sees a complete project, and no single command
    runs the tests.

    Measured on run-64df2b20, whose stack was Python/FastAPI/pytest: its
    `tests/` directory held `test_auth.py` beside `auth.test.js`,
    `password.test.js` and `user.test.js`, and its project root held
    `__init__.py` beside `package.json` and `requirements.txt`. Each file was a
    sensible answer to the task its author was given; nothing could run the set.

    TypeScript and JavaScript are counted separately only when a manifest says
    so - a `.ts` file beside a `.js` file is ordinary in one project.
    """
    by_directory: dict[Path, dict[str, set[str]]] = {}
    for path in files:
        relative = str(path.relative_to(root))
        if _NOT_COUNTED.search(relative):
            continue
        language = _LANGUAGE_OF.get(path.suffix.lower()) or _MANIFEST_OF.get(path.name)
        if language is None:
            continue
        if language == "TypeScript":
            language = "JavaScript"  # one toolchain, one manifest
        seen = by_directory.setdefault(path.parent, {})
        seen.setdefault(language, set()).add(path.name)

    problems = []
    for directory, languages in sorted(by_directory.items()):
        if len(languages) < 2:
            continue
        shown = str(directory.relative_to(root)) or "."
        detail = "; ".join(
            f"{language}: {', '.join(sorted(names)[:3])}"
            for language, names in sorted(languages.items())
        )
        problems.append(
            f"{shown}/ holds source from {len(languages)} languages at once "
            f"({detail}). A directory is what a manifest and a test runner "
            "address, so neither one sees a complete project here and no single "
            "command runs the tests. Give each language its own directory inside "
            "the project, with its own manifest and its own tests."
        )
    return problems


def _application_embedded_in_html(files: list[Path], root: Path) -> list[str]:
    """An application inside a `<script>` tag, which no runner can open.

    A test can only import a file. Logic embedded in HTML can only be tested by
    copying it, and a copy passes whatever the real code does - so this produces
    exactly the green-but-meaningless suite that `_redefined_instead_of_imported`
    reports, one step earlier and for a reason nobody can fix afterwards.

    Measured on run-2f252e4e, whose specification described pure functions, a
    storage adapter and an `init()` - correctly - and then placed all of it in a
    single `index.html`: "No external files, no build step, no module system."

    Only fires when the page loads no script of its own, so a page that embeds a
    little bootstrap alongside a real `app.js` is left alone.
    """
    problems = []
    for path in files:
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        text = _read(path)
        if _SCRIPT_SRC.search(text):
            continue  # it loads a file; that file is what tests will import
        for body in _INLINE_SCRIPT.findall(text):
            lines = len([line for line in body.splitlines() if line.strip()])
            if lines < _EMBEDDED_APPLICATION_LINES:
                continue
            relative = str(path.relative_to(root))
            problems.append(
                f"{relative} holds {lines} lines of JavaScript inside a <script> "
                "tag and loads no script file. No test runner can import it, so "
                "the only way to test this code is to copy it - and a copy passes "
                "whatever the real code does. Move it to its own file beside the "
                "page and load it with <script src>."
            )
            break
    return problems


#: A relative import, in any of the forms a test file actually uses:
#: `import x from './a.js'`, `import {a, b as c} from './a.js'`,
#: `import * as ns from './a.js'`, `const {a} = await import('./a.js')`,
#: `const a = require('./a.js')`. A leading dot is what makes it the product.
_RELATIVE_BINDING = re.compile(
    r"""import\s+(?P<clause>[^;'"]+?)\s+from\s*["']\.[^"']*["']"""
    r"""|(?:const|let|var)\s+(?P<lhs>\{[^{}]*\}|[A-Za-z_$][\w$]*)\s*="""
    r"""\s*(?:await\s+)?(?:import|require)\s*\(\s*["']\.[^"']*["']\s*\)""",
    re.M,
)
_IDENTIFIER = re.compile(r"^[A-Za-z_$][\w$]*$")
_NAMESPACE_CLAUSE = re.compile(r"^\*\s+as\s+([A-Za-z_$][\w$]*)$")


def _names_bound_from_a_relative_module(text: str) -> set[str]:
    """Every identifier the file binds from a relative module.

    Written for the shadowing case: a test may import the application and still
    define its own `addTask`, and only the names it actually binds tell the two
    apart. Destructuring renames bind the name on the right of `as`/`:`, which
    is the one the tests then call.
    """
    names: set[str] = set()
    for match in _RELATIVE_BINDING.finditer(text):
        clause = (match.group("clause") or match.group("lhs") or "").strip()
        opening = clause.find("{")
        if opening != -1:
            closing = clause.find("}", opening)
            inside = clause[opening + 1 : closing if closing != -1 else len(clause)]
            for piece in inside.split(","):
                piece = piece.strip()
                if not piece:
                    continue
                bound = re.split(r"\s+as\s+|:", piece)[-1].strip()
                if _IDENTIFIER.match(bound):
                    names.add(bound)
            clause = clause[:opening] + (
                clause[closing + 1 :] if closing != -1 else ""
            )
        for piece in clause.split(","):
            piece = piece.strip().rstrip("=").strip()
            if not piece:
                continue
            namespace = _NAMESPACE_CLAUSE.match(piece)
            if namespace:
                names.add(namespace.group(1))
            elif _IDENTIFIER.match(piece):
                names.add(piece)
    return names


#: `readFileSync("./x")` and friends. A bare `x/y` is relative too; a leading
#: `/` is not, and neither is a path built from `import.meta.url`.
_READS_A_PATH = re.compile(
    r"""readFile(?:Sync)?\s*\(\s*["'](\.{1,2}/[^"']+|[A-Za-z][^"'/]*/[^"']+)["']""",
)

#: The two ways a test file anchors a path to its own location.
_ANCHORED = ("import.meta.url", "__dirname")


def _tests_that_depend_on_the_working_directory(files: list[Path], root: Path) -> list[str]:
    """Test files that open a path relative to wherever they were run from.

    This is the defect that passes every check the workflow makes. On
    run-9ff00d5b the suite read `'./todo-app/index.html'`, and the test round
    ran it as `node --test todo-app/app.test.mjs` from the workspace root,
    where that path resolves. It passed eight times. From inside the project
    directory - `cd todo-app && node --test app.test.mjs`, which is how anyone
    who is handed the project runs it - every test fails with ENOENT.

    So the workflow cannot find this by running the tests: they pass. It is
    only visible by reading how the path is built.

    run-5d83e946 hit the same thing with `path.resolve('./script.js')`, where
    the test round happened to run from the other directory, the tests failed,
    and a defect-fix round corrected it to `import.meta.url`. The difference
    between a caught defect and a shipped one was which directory the command
    happened to use.

    Measured across the delivered workspaces: 19 test files anchor their paths
    to the test file and one does not, so this reports the one.
    """
    problems = []
    for path in files:
        relative = str(path.relative_to(root))
        if not (not is_application(relative)):
            continue
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts"}:
            continue
        text = _read(path)
        if any(anchor in text for anchor in _ANCHORED):
            continue
        found = _READS_A_PATH.findall(text)
        if not found:
            continue
        named = ", ".join(sorted(set(found))[:3])
        problems.append(
            f"{relative} opens {named} relative to whatever directory it is "
            "run from, not to itself. It passes when run from the workspace "
            "root and fails from the project directory, which is where anyone "
            "handed this project will run it. Resolve the path against "
            "`import.meta.url` (or `__dirname`) so it works from either."
        )
    return problems


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

    Fires per NAME, not per file. run-5d83e946 shipped the same defect wearing
    an import: `script.test.mjs` opened with "Inline copies of the pure
    functions (mirrors script.js exactly)", ran every behavioural assertion
    against those copies, and closed with nine tests that did import the real
    module - to assert `typeof mod.addTask === 'function'` and nothing more.
    The first version of this rule exempted any file holding a relative import,
    so it said nothing. A name the test defines itself and never binds from the
    application is a copy however many other imports the file carries.

    That run is also why a rename is not a mutation test: renaming `addTask`
    broke the eight `typeof` checks, which made the suite look bound while
    every assertion about behaviour still passed against the copy.
    """
    application: dict[str, str] = {}
    for path in files:
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts"}:
            continue
        if (not is_application(relative)):
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
        if not (not is_application(relative)):
            continue
        text = _read(path)
        # Names this file binds from the application itself. Only a RELATIVE
        # specifier can name the product: `node:assert/strict` and a bare
        # package specifier both contain a slash and neither is the product,
        # which is what made the first version of this check silent on the very
        # file it was written for.
        imported = _names_bound_from_a_relative_module(text)
        defined = set(_TOP_LEVEL_FUNCTION.findall(text)) | set(
            _TOP_LEVEL_CONST_FN.findall(text)
        )
        shared = sorted(
            name for name in defined if name in application and name not in imported
        )
        if not shared:
            continue
        source = application[shared[0]]
        named = ", ".join(shared[:4]) + (f" and {len(shared) - 4} more" if len(shared) > 4 else "")
        reaches = bool(imported)
        problems.append(
            f"{relative} defines {named} itself and calls its own copy rather "
            f"than {source}'s, so it tests a copy: those assertions pass "
            f"whatever {source} does."
            + (
                " The file does import from the application, but not these "
                "names - importing a module and then shadowing what it exports "
                "leaves the assertions pointing at the copy."
                if reaches
                else f" It imports nothing from {source} at all."
            )
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
            referenced = path.parent / target
            if not referenced.exists():
                problems.append(
                    f"{path.relative_to(root)} references `{target}`, which does "
                    "not exist in the workspace."
                )
                continue
            # Present but empty is not the same as present. A page that links
            # an empty stylesheet renders unstyled and a page that loads an
            # empty script does nothing, and both look correct to a check that
            # only asks whether the file is there.
            #
            # Measured on run-5f4cdd55: index.html linked `style.css` on line
            # 6, the file was zero bytes, the reference check passed, and the
            # size report counted it as one line of the product.
            try:
                if referenced.is_file() and not referenced.read_text(
                    encoding="utf-8", errors="replace"
                ).strip():
                    problems.append(
                        f"{path.relative_to(root)} references `{target}`, which "
                        "exists but is empty. The page loads it and gets nothing - "
                        "a stylesheet with no rules or a script with no code. "
                        "Either write it or stop referencing it."
                    )
            except OSError:  # unreadable is not the same as empty
                continue
    return problems


def _module_system_mismatch(files: list[Path], root: Path) -> list[str]:
    """ES module source under a test configuration that cannot parse it."""
    esm_sources = [
        path
        for path in files
        if path.suffix.lower() in {".js", ".mjs"}
        and not (not is_application(str(path.relative_to(root))))
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
    # Naming only Jest made this dismissible by every project that does not use
    # Jest - which is most of them here. Measured on run-da6c5e19: `app.js`
    # exported three objects, nothing declared the module type, and `node --test`
    # loaded it as CommonJS. The test file then reported "we can't directly
    # import app.js", wrote its own copy of the logic, and passed.
    return [
        f'{listed} use ES module syntax, but nothing declares it: no '
        '`package.json` sets `"type": "module"` and the files are not named '
        "`.mjs`. A test that imports them gets \"does not provide an export "
        "named ...\" - the runner loads them as CommonJS and the exports are "
        "invisible. Jest additionally needs a `transform`."
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


_LINE_COMMENT = re.compile(r"^\s*(//|#)")
_BLOCK_COMMENT_EDGES = (("/*", "*/"), ("<!--", "-->"))


def _code_lines(text: str) -> int:
    """Lines that are neither blank nor comment.

    "Maximum 500 lines of code" does not mean 500 lines of file. Reporting only
    the raw count leaves the reviewer comparing a number against a limit that
    means something else, and on run-2b5def74 that ambiguity is why nothing
    could say whether 609 raw lines broke a 500-line cap. The workflow's own
    agent reached the same conclusion unprompted: the audit it wrote in sprint 1
    counted "non-blank, non-comment" lines, and then never ran again.
    """
    count = 0
    in_block: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if in_block:
            if in_block in line:
                in_block = None
            continue
        if not line:
            continue
        opened = False
        for start, end in _BLOCK_COMMENT_EDGES:
            if line.startswith(start):
                if end not in line[len(start):]:
                    in_block = end
                opened = True
                break
        if opened:
            continue
        if _LINE_COMMENT.match(line):
            continue
        count += 1
    return count


#: A line budget stated in the project's own documents. Both spellings the
#: workflow actually writes: "Maximum 500 lines of code" straight from the
#: brief, and "the 500-line limit" as the intake and specification restate it.
_DECLARED_BUDGET = re.compile(
    r"(?:maximum|max|no more than|within|under|cap(?:ped)?\s+(?:at|to)|limit\s+of)"
    r"\s*(\d{2,5})\s*(?:total\s+)?lines"
    r"|(\d{2,5})[-\s]line\s*(?:limit|cap|budget|maximum)",
    re.I,
)


def _declared_line_budget(root: Path) -> int | None:
    """The line cap this project's own documents state, if they state one.

    Taken from the workspace's documents rather than threaded through from the
    brief, because those documents are where the number has already been
    interpreted: `brief_low` says "Maximum 500 lines of code" and the intake
    restates it as an acceptance criterion, "Total source code stays within the
    500-line limit". Reading them needs no new plumbing and picks up a cap the
    workflow set for itself.

    The most frequently stated number wins, ties going to the smallest, so one
    passing mention of a different figure cannot move the budget.
    """
    seen: list[int] = []
    for folder in (root / "docs", root):
        if not folder.is_dir():
            continue
        for document in sorted(folder.glob("*.md")):
            try:
                text = _read(document)
            except Exception:  # noqa: BLE001 - a missing document is not a budget
                continue
            for match in _DECLARED_BUDGET.finditer(text):
                value = match.group(1) or match.group(2)
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    continue
                if 50 <= number <= 100_000:
                    seen.append(number)
    if not seen:
        return None
    best = max(set(seen), key=lambda n: (seen.count(n), -n))
    return best


def _over_the_declared_budget(
    files: list[Path], root: Path, orphans: set[str] | None = None
) -> list[str]:
    """The product measured against the cap its own documents state.

    `_size_report` was written to report and not judge - "The reviewer has the
    brief and can compare, but only if someone counts." run-1d1b6c9c shows the
    reviewer comparing only when something else makes size an explicit
    criterion for that milestone.

    Sprint 2's review was handed `550 of them code`, directly under a sentence
    saying that is the number a cap means; the cap appears six times in that
    run's own documents, once as the acceptance criterion "Total source code
    stays within the 500-line limit". It accepted the milestone with two
    findings, neither about size, and the sprint was tagged sprint-2.

    Sprint 3's review DID catch it - "total 893 lines (602 code lines) exceeds
    the stated 500-line target" - because that milestone's goal named code size
    compliance and a prior audit had recorded it as AC-9.

    So the difference was not the evidence, which was the same both times. It
    was whether that sprint's goal happened to mention size. A constraint that
    holds for the whole product should not be enforced only in the sprint whose
    goal remembers it, and one subtraction over two numbers the harness already
    has is the wrong thing to leave to model judgment.
    """
    budget = _declared_line_budget(root)
    if budget is None:
        return []
    application, _, _, counted_code = _measure_sizes(files, root, orphans)
    if not application:
        return []
    code_total = sum(counted_code.get(name, 0) for _, name in application)
    if code_total <= budget:
        return []
    biggest = ", ".join(
        f"{name} ({counted_code.get(name, 0):,})"
        for _, name in sorted(application, reverse=True)[:3]
    )
    return [
        f"The product is {code_total:,} lines of code against the {budget:,}-line "
        f"maximum this project's own documents state - {code_total - budget:,} over. "
        f"Counted without blank lines, comments, tests or files nothing loads. "
        f"Largest: {biggest}. This is a stated acceptance criterion, not a "
        f"preference: either bring it under {budget:,} or say in the review why "
        f"the criterion no longer holds."
    ]



def budget_note_for_a_write(repo_root, relative_path: str) -> str:
    """What to tell the agent that just wrote a file, about the line budget.

    The budget check has only ever run at review time, and by then the cost is
    a whole cycle: the reviewer blocks, the Technical Lead re-plans, a
    specialist is re-delegated, and the code is rewritten. run-fa7b7286 spent
    three milestone cycles on it and went the wrong way - the review that first
    raised it counted 671 lines against a stated 500, and the next cycle
    produced 859.

    Every correction that has actually changed this model's behaviour arrived
    in the result of the call that caused the problem; the same words in a
    brief did not. The 500-line cap is stated in the brief, the intake and the
    specification, and was exceeded anyway.

    So this says the number at the moment the file lands, while the agent still
    has the file in mind and no other stage has been involved. It never
    refuses: a write that fails leaves the agent with nowhere to put its work,
    and the cap is the project's own stated preference, not a rule of the
    sandbox.

    Returns "" whenever it cannot be sure - no declared budget, an unreadable
    workspace, or a project still inside its cap.
    """
    try:
        # Only when the file just written is itself counted code. Writing a
        # document does not move this number, and a note about it there reads
        # as a complaint about the wrong file.
        if Path(relative_path).suffix.lower() not in _COUNTED_SUFFIXES:
            return ""
        root = Path(repo_root).resolve()
        budget = _declared_line_budget(root)
        if not budget:
            return ""
        files = _source_files(root)
        orphans = _orphans_quietly(files, root)
        application, _, _, counted_code = _measure_sizes(files, root, orphans)
        # Over `application`, exactly as `_over_the_declared_budget` does, not
        # over every entry in `counted_code`. Summing all of it counts the test
        # suite, which `_measure_sizes` splits off for the stated reason that a
        # brief capping "lines of code" almost never means the tests.
        #
        # The first version of this note summed everything and said 1,533 on
        # run-44653bd2 where the reviewer would say 628, because one 797-line
        # `Task.test.mjs` was in the total. Warning an agent it is 1,033 over
        # when it is 128 over does not just overstate: the cheapest way to
        # close a gap that size is to delete tests.
        if not application:
            return ""
        total = sum(counted_code.get(name, 0) for _, name in application)
        if total <= budget:
            return ""
        biggest = sorted(
            ((name, counted_code.get(name, 0)) for _, name in application),
            key=lambda kv: -kv[1],
        )[:3]
        largest = ", ".join(f"{name} ({lines})" for name, lines in biggest)
        return (
            f"\n\nNote: this project's own documents state a limit of {budget} lines "
            f"of application code, and it now holds {total} - {total - budget} over. "
            f"The largest files are {largest}. A milestone review will block on "
            "this, so trimming now costs less than a review cycle: remove what is "
            "duplicated or unused rather than adding another file."
        )
    except Exception:  # noqa: BLE001 - a hint must never fail a write
        return ""

def _measure_sizes(
    files: list[Path], root: Path, orphans: set[str] | None = None
) -> tuple[list[tuple[int, str]], list[tuple[int, str]], list[tuple[int, str]], dict[str, int]]:
    """Count once, for both the report and the budget check.

    Separated so the number shown to a reviewer and the number judged against
    the brief cannot be arrived at differently. They already did once: finding
    06 was a size report counting abandoned probe scripts as product while the
    orphan check, in the same report, named them as strays. The two halves
    never spoke.
    """
    application: list[tuple[int, str]] = []
    tests: list[tuple[int, str]] = []
    stray: list[tuple[int, str]] = []
    counted_code: dict[str, int] = {}
    orphans = orphans or set()
    for path in files:
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in _COUNTED_SUFFIXES or _NOT_COUNTED.search(relative):
            continue
        try:
            text = _read(path)
        except Exception:  # noqa: BLE001 - a size report must never fail the checks
            continue
        lines = text.count("\n") + 1
        code = _code_lines(text)
        if relative in orphans:
            stray.append((lines, relative))
            continue
        counted_code[relative] = code
        # Split, because a brief capping "lines of code" almost never means the
        # test suite - and reporting one number invites the reviewer to judge
        # the wrong thing. On run-18c0e34c the application was 631 lines and the
        # tests the round installed were 1,558 more.
        (tests if (not is_application(relative)) else application).append((lines, relative))
    return application, tests, stray, counted_code


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
    application, tests, stray, counted_code = _measure_sizes(files, root, orphans)

    if not application and not tests and not stray:
        return ""
    application.sort(reverse=True)
    tests.sort(reverse=True)
    stray.sort(reverse=True)
    app_total = sum(n for n, _ in application)
    test_total = sum(n for n, _ in tests)

    listed = "\n".join(f"  {n:5d}  {name}" for n, name in application[:8])
    more = f"\n  ... and {len(application) - 8} more" if len(application) > 8 else ""
    code_total = sum(counted_code.get(name, 0) for _, name in application)
    report = (
        f"\n\nSize of the product as built. A brief that caps \"lines of code\" "
        f"means the second number, not the first:\n"
        f"  application: {app_total:,} lines across {len(application)} file(s)\n"
        f"               {code_total:,} of them code (neither blank nor comment)\n"
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
        elif not test_script:
            # A suite nobody can reach by the obvious command. Measured on
            # run-cbb1a5fc: 153 passing tests in `app.test.mjs`, a manifest with
            # no `scripts` at all, and `npm test` answering "missing script:
            # test". The placeholder case above has been covered since
            # run-95ca3f72; having no script is the same outcome with less to
            # see - and it reads as "this project has no tests".
            suites = sorted(
                str(p.relative_to(root)) for p in files
                if p.parent == path.parent and (not is_application(str(p.relative_to(root))))
            )
            if suites:
                named = ", ".join(suites[:3])
                problems.append(
                    f"{relative} declares no `test` script, and this project has "
                    f"tests ({named}). `npm test` answers \"missing script: test\", "
                    "so the suite is reachable only by someone who already knows "
                    "the command. Add the one that runs them."
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


def _orphans_quietly(files: list[Path], root: Path) -> set[str]:
    """The orphan set, or an empty one. Never raises."""
    try:
        return set(_orphaned_scripts(files, root))
    except Exception:  # noqa: BLE001
        return set()


#: Findings that mean a feature does nothing, as opposed to findings that mean
#: something is untidy. A reviewer given one list weighs them the same way.
#:
#: run-499c771a accepted its milestone with the note "The cross-file check
#: identified unused CSS classes; this does not affect functionality but could
#: be cleaned up" - a fair reading of dead CSS, and the reading this list
#: exists to stop being applied to a script hook that does not exist. Those two
#: findings look alike in a bullet list and are not alike at all: one is paint
#: nobody sees, the other is the submit button not working.
#: Each phrase is taken from a message this module actually emits, not guessed
#: at: a marker that matches nothing silently classifies every finding as
#: untidy, and one that matches too much makes a reviewer block on dead CSS.
_BREAKS_BEHAVIOUR = (
    "have never executed, and a passing suite",  # a false green suite
    "looks for the element id",          # a script hook no page provides
    "reads the attribute",               # a data-* attribute nothing sets
    "which does not exist in the workspace",  # a src/import pointing at nothing
    "The page loads it and gets nothing",     # an empty file that is loaded
    "so no tool can read it",            # a manifest that will not parse
    "calls its own copy rather",         # a redefinition instead of an import
    "relative to whatever directory",    # a path that depends on the cwd
    "declares no `test` script",         # `npm test` cannot run
    "placeholder test script",           # `npm test` fails by default
)


def _severity_of(problem: str) -> str:
    return "BREAKS" if any(mark in problem for mark in _BREAKS_BEHAVIOUR) else "untidy"


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
            + _hooks_javascript_reaches_for(files, root)
            + _tests_the_project_never_runs(files, root)
            + _dangling_class_selectors(files, root)
            + _documented_commands_that_cannot_run(files, root, root / "docs")
            + _broken_local_references(files, root)
            + _unreferenced_scripts(files, root)
            + _redefined_instead_of_imported(files, root)
            + _application_embedded_in_html(files, root)
            + _languages_sharing_a_directory(files, root)
            + _module_system_mismatch(files, root)
            + _tests_that_depend_on_the_working_directory(files, root)
            + _over_the_declared_budget(files, root, _orphans_quietly(files, root))
        )
    except Exception:  # noqa: BLE001
        return "The cross-file checks could not complete on this workspace."

    checked = (
        f"Cross-file checks ran over {len(files)} files: stylesheet id selectors "
        "and the ids and data attributes scripts reach for against declared "
        "element ids, HTML script and stylesheet references "
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
    breaking = [p for p in problems if _severity_of(p) == "BREAKS"]
    untidy = [p for p in problems if _severity_of(p) != "BREAKS"]
    sections = []
    if breaking:
        sections.append(
            f"{len(breaking)} of these {'means' if len(breaking) == 1 else 'mean'} "
            "a feature DOES NOT WORK. Nothing "
            "throws and no test fails, because the code path is simply never "
            "reached - so a passing suite is not evidence against them. Each is "
            "a blocking finding unless you can show it is not:\n"
            + "\n".join(f"- {problem}" for problem in breaking)
        )
    if untidy:
        sections.append(
            f"{len(untidy)} {'is' if len(untidy) == 1 else 'are'} untidy rather "
            "than broken - dead rules, unused files. Worth a minor finding, not "
            "a blocking one:\n"
            + "\n".join(f"- {problem}" for problem in untidy)
        )
    return (
        checked
        + f"\n\n{len(problems)} cross-file problem(s) found. Each is a real "
        "relationship between two files, not a style preference.\n\n"
        + "\n\n".join(sections)
        + sizes
    )


__all__ = ["summarise_integration"]
