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

    A command that NAMES files strands everything it does not name, whatever
    those files are called. Run f81808a4 reached its sixth milestone with
    `scripts.test` of `node --test main.test.js` and a second suite at
    `tests/filter.test.js` - a correct Node test name, in a directory bare
    `node --test` would recurse into, and never run once, because the command
    names one file. Every gate read "# tests 4  # pass 4" and none of the
    filter tests were among them.

    Verified rather than assumed, in the run image:

        node --test a.test.js  ->  # tests 1   (tests/b.test.js not run)
        node --test            ->  # tests 2   (tests/b.test.js run)

    so a bare command recurses through subdirectories and an explicit one does
    not, and both halves of this check follow from that.

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
        named = _paths_named_after_the_test_flag(command)
        searched, listed_files = _what_the_command_searches(named, project)
        # A named file that imports the suites runs them. Run f81808a4's
        # `run-tests.mjs` sets up a localStorage mock and then imports four
        # files from `tests/`; without following that, this reported all four
        # as never executed - four wrong findings out of ten, for tests that
        # run on every `npm test`.
        imported = _what_those_files_import(listed_files, project)
        tests = [
            path
            for path in files
            if path.suffix.lower() in {".js", ".mjs", ".cjs"}
            and is_test(str(path.relative_to(root)))
            and _is_within(path, project)
        ]
        stranded = [
            path
            for path in tests
            if not _node_runs(path, project, searched, listed_files)
            and path.resolve() not in imported
        ]
        if not stranded:
            continue
        if listed_files:
            why = (
                f"which names {', '.join(sorted(listed_files))}. A file given to "
                "`node --test` is run directly and nothing else is searched. "
                "Those files have never executed, and a passing suite is being "
                "read as evidence they did. Name them too, or give a directory "
                "instead - "
                "`node --test` with no arguments searches the whole project."
            )
        else:
            why = (
                "which does not collect them. Those files have never executed, "
                "and a passing suite is being read as evidence they did. Node's "
                "patterns are *.test.js, *-test.js, *_test.js, test-*.js, "
                "test.js, or anything under a test/ directory - note the prefix "
                "form takes a hyphen."
            )
        where = ", ".join(sorted(str(path.relative_to(project)) for path in stranded))
        problems.append(
            f"{manifest.relative_to(root)} runs `{command}`, {why} Stranded: {where}."
        )
    return problems


def _what_the_command_searches(
    named: list[str], project: Path
) -> tuple[list[Path], list[str]]:
    """The directories `node --test` searches, and the files it runs outright.

    Verified in the run image, with `badname.mjs` beside `a.test.js` and the
    same pair under `sub/`:

        node --test ./          -> 2   (both name matches, recursively)
        node --test sub/        -> 1   (the name match under sub only)
        node --test badname.mjs -> 1   (the file, name notwithstanding)
        node --test             -> 2   (as `./`)

    So a DIRECTORY argument recurses and applies Node's name patterns inside
    it, and a FILE argument runs that file whatever it is called. An earlier
    version of this check read every argument as a file, which made
    `node --test ./` look like it ran one path and stranded the suite.
    """
    if not named:
        return [project], []
    searched: list[Path] = []
    listed_files: list[str] = []
    for argument in named:
        target = (project / argument.strip()).resolve()
        if argument.strip().endswith("/") or target.is_dir():
            searched.append(target)
        else:
            listed_files.append(argument.strip())
    return searched, listed_files


def _what_those_files_import(listed_files: list[str], project: Path) -> set[Path]:
    """Every local file the named entry points reach, at any depth.

    An aggregator is a normal and correct way to run a suite: run f81808a4's
    `run-tests.mjs` installs a localStorage stub the individual files need and
    then imports them. Its tests run; they are not stranded.
    """
    from app.analysis.local_imports import _RELATIVE, _resolve

    reached: set[Path] = set()
    queue = [
        (project / name.strip("./")).resolve()
        for name in listed_files
        if (project / name.strip("./")).is_file()
    ]
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        try:
            text = current.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _RELATIVE.finditer(text):
            specifier = next((g for g in match.groups() if g), None)
            if not specifier:
                continue
            target = _resolve(current, specifier)
            if target is not None and target not in reached:
                queue.append(target)
    return reached


def _node_runs(
    path: Path, project: Path, searched: list[Path], listed_files: list[str]
) -> bool:
    """Whether `node --test` reaches this test file."""
    relative = path.relative_to(project).as_posix()
    if any(relative == name.strip("./") for name in listed_files):
        return True
    return any(_is_within(path, directory) for directory in searched) and bool(
        _NODE_COLLECTS.match(path.name)
    )


def _is_within(path: Path, directory: Path) -> bool:
    """Whether `path` sits under `directory` at any depth."""
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _paths_named_after_the_test_flag(command: str) -> list[str]:
    """Path arguments the `node --test` command names, ignoring its flags."""
    words = command.split()
    try:
        after = words[words.index("--test") + 1 :]
    except ValueError:
        return []
    return [
        word
        for word in after
        if not word.startswith("-") and word not in {"node", "&&", "||", ";"}
    ]





#: `<script ... src="app.js" ...>` with everything the tag declared, so the
#: `type` can be read off it.
_SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.I)
_TAG_SRC = re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']""", re.I)
_TAG_TYPE = re.compile(r"""\btype\s*=\s*["']([^"']+)["']""", re.I)


def _modules_loaded_as_plain_scripts(files: list[Path], root: Path) -> list[str]:
    """ES modules a page loads without `type="module"`.

    The browser parses the file as a classic script, hits `export` or `import`
    on the first line, and throws `Uncaught SyntaxError: Unexpected token
    'export'`. Nothing on the page works, and nothing in the test suite notices
    - `node --test` imports the module directly and never goes near the HTML.

    Found by run-01f03ed9's milestone reviewer, which read both files and
    called it blocking. It is decidable from those two files, so it should not
    have needed a model: `index.html` line 33 was `<script src="app.js">` and
    `app.js` opens with `export { addTask, ... }`.

    `_module_system_mismatch` checks module syntax against the *test*
    configuration. This is the same question asked of the page, which is where
    the user meets it.
    """
    problems: list[str] = []
    for page in files:
        if page.suffix.lower() not in {".html", ".htm"}:
            continue
        text = _read(page)
        for attributes in _SCRIPT_TAG.findall(text):
            src = _TAG_SRC.search(attributes)
            if not src:
                continue
            kind = _TAG_TYPE.search(attributes)
            if kind and kind.group(1).strip().lower() == "module":
                continue
            target = (page.parent / src.group(1).lstrip("/")).resolve()
            if not target.is_file() or target.suffix.lower() not in {".js", ".mjs"}:
                continue
            try:
                if not _ESM.search(_read(target)):
                    continue
            except Exception:  # noqa: BLE001
                continue
            problems.append(
                f"{page.relative_to(root)} loads {src.group(1)} with a plain "
                '<script> tag, and that file uses `import`/`export`. The browser '
                "parses it as a classic script and throws `Uncaught SyntaxError: "
                "Unexpected token 'export'` on the first line, so nothing on the "
                'page runs. Add type="module" to the tag. The test suite cannot '
                "catch this - it imports the module directly and never loads the "
                "page."
            )
    return problems


#: A line comment, a block comment, or a string literal - the three places a
#: token can appear without meaning anything.
_NOT_CODE = re.compile(
    r"""//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`""",
    re.S,
)


def _only_the_code(text: str) -> str:
    """`text` with comments and string literals blanked, newlines preserved.

    A `require` inside a comment is not a `require`. That matters most in
    exactly the situation these checks exist for: an agent converting a file
    from CommonJS to ES modules comments the old call out, and a check reading
    the raw text goes on reporting the file as broken after it has been fixed.

    Blanked rather than removed, so line numbers and structure survive for
    anything that reads them afterwards.
    """
    return _NOT_CODE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


#: CommonJS, which the browser has never had. `module`, `exports` and
#: `require` are Node's; a browser reaching any of them throws a ReferenceError.
_COMMONJS = re.compile(
    # No quote required after `require(`. This is matched against code whose
    # string literals have been blanked by `_only_the_code`, so a genuine
    # `require('y')` arrives as `require(   )` - insisting on the quote made
    # the stripper hide every real require it was meant to preserve.
    r"""^\s*module\.exports\s*=|^\s*exports\.\w+\s*=|"""
    r"""(?<![\w.$])require\s*\(""",
    re.M,
)

#: `typeof module !== 'undefined'` and friends. `typeof` on an undeclared
#: identifier is the one way to touch `module` or `require` without throwing,
#: so a file that tests for them is written to load under either module system
#: on purpose and must not be reported as contradicting one.
#:
#: Run 9ff00d's `todo-app/app.js` ends with
#:
#:     if (typeof module !== 'undefined' && module.exports) {
#:         module.exports = { Task, AppState, render };
#:     }
#:
#: under a manifest declaring `"type": "module"`. Verified in the worker image
#: on Node 20.20.2: that file loads and prints, because the branch is simply
#: not taken. Both checks below reported it as broken until this was added.
_FEATURE_DETECTS_COMMONJS = re.compile(
    r"""typeof\s+(?:module|require|exports)\s*[!=]==?\s*['"]undefined['"]"""
    r"""|['"]undefined['"]\s*[!=]==?\s*typeof\s+(?:module|require|exports)""",
)


def _commonjs_loaded_as_a_module(files: list[Path], root: Path) -> list[str]:
    """CommonJS behind `<script type="module">`, which the browser cannot run.

    The mirror of `_modules_loaded_as_plain_scripts`, and run d6297b2f built
    it: `index.html` carried

        <script type="module" src="app.js"></script>

    while `app.js` ended with

        module.exports = { loadTasks, saveTasks, addTask, ... };

    `module` does not exist in a browser under any script type, so the page
    throws `Uncaught ReferenceError: module is not defined` and nothing on it
    works. The test suite does not notice, and cannot: `node --test` loads the
    same file as CommonJS, where those exports are exactly right, and Node's
    interop even synthesises named ESM imports from them. Both halves pass
    their own check while the product is dead in the only place a user opens
    it.

    Silent when the file also uses `import`/`export`. A file mixing both is a
    different mistake, and one a bundler may legitimately be resolving.
    """
    problems: list[str] = []
    for page in files:
        if page.suffix.lower() not in {".html", ".htm"}:
            continue
        text = _read(page)
        for attributes in _SCRIPT_TAG.findall(text):
            src = _TAG_SRC.search(attributes)
            kind = _TAG_TYPE.search(attributes)
            if not src or not kind:
                continue
            if kind.group(1).strip().lower() != "module":
                continue
            target = (page.parent / src.group(1).lstrip("/")).resolve()
            if not target.is_file() or target.suffix.lower() not in {".js", ".mjs"}:
                continue
            try:
                body = _read(target)
            except Exception:  # noqa: BLE001
                continue
            code = _only_the_code(body)
            if not _COMMONJS.search(code) or _ESM.search(code):
                continue
            # Against the raw text, not the stripped code: the guard is
            # `typeof module !== 'undefined'`, and blanking string literals
            # removes the very quotes it is recognised by.
            if _FEATURE_DETECTS_COMMONJS.search(body):
                continue
            problems.append(
                f"{page.relative_to(root)} loads {src.group(1)} as "
                '`<script type="module">`, and that file is CommonJS - it uses '
                "`module.exports` or `require`, neither of which exists in a "
                "browser. The page throws `Uncaught ReferenceError: module is "
                "not defined` and nothing on it works. The test suite cannot "
                "catch this: `node --test` loads the same file as CommonJS, "
                "where those exports are correct. Use `export` in the file, or "
                "stop loading it as a module."
            )
    return problems


#: A path-looking token in a script: something with a slash or a file suffix.
_SCRIPT_PATH = re.compile(r"(?<![\w./-])((?:\./)?[\w.-]+(?:/[\w.-]+)*\.[cm]?[jt]sx?)")


def _manifest_scripts_that_cannot_resolve(files: list[Path], root: Path) -> list[str]:
    """Paths in `scripts` that do not exist from the manifest's own directory.

    `npm run` sets the working directory to the package directory, so a path in
    a script is relative to the manifest beside it. A model that writes the
    project directory into the path as well produces
    `todo-app/todo-app/app.test.mjs`, which exists nowhere.

    `strip_a_doubled_working_directory` catches that shape in a
    `run_terminal_command` argument, and cannot reach this one: a path written
    into `package.json` is persisted, and `npm test` fails the same way every
    time it is run, for the rest of the project's life.

    Measured on run-a7150a6c, whose manifest said

        "test": "node --test simple-to-do-list-app/app.test.mjs"

    inside `simple-to-do-list-app/`. `npm test` reported
    `Could not find '.../simple-to-do-list-app/simple-to-do-list-app/app.test.mjs'`
    while `app.test.mjs` sat beside the manifest.

    Reported only when the path does not resolve and something of that name is
    in the project, so a script naming a file that is about to be written is
    not called a defect.
    """
    problems: list[str] = []
    for manifest in files:
        if manifest.name != "package.json":
            continue
        try:
            scripts = (json.loads(_read(manifest)) or {}).get("scripts") or {}
        except Exception:  # noqa: BLE001 - a broken manifest is reported elsewhere
            continue
        project = manifest.parent
        for name, command in sorted(scripts.items()):
            for candidate in set(_SCRIPT_PATH.findall(str(command))):
                if (project / candidate).exists():
                    continue
                elsewhere = [
                    other.relative_to(project).as_posix()
                    for other in project.rglob(Path(candidate).name)
                    if other.is_file()
                    and not any(part in _SKIP for part in other.parts)
                ]
                if not elsewhere:
                    continue
                problems.append(
                    f"{manifest.relative_to(root)} runs `npm run {name}` as "
                    f"`{command}`, and `{candidate}` does not exist from "
                    f"{project.relative_to(root)}/ - which is where npm runs it. "
                    f"The file is at {', '.join(sorted(elsewhere)[:3])}. The "
                    "script fails every time it is run, and will keep failing: "
                    "this path is written into the manifest, not passed on a "
                    "command line."
                )
    return problems


#: `export function a`, `export const b =`, `export class C`, `export { d, e }`
_EXPORTED_DECLARED = re.compile(
    r"^\s*export\s+(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)",
    re.M,
)
_EXPORTED_LIST = re.compile(r"^\s*export\s*\{([^}]*)\}", re.M)


def _exports_of(text: str) -> set[str]:
    names = set(_EXPORTED_DECLARED.findall(text))
    for clause in _EXPORTED_LIST.findall(text):
        for part in clause.split(","):
            name = part.strip().split(" as ")[-1].strip()
            if name and name != "default":
                names.add(name)
    return names


def _exports_no_test_mentions(files: list[Path], root: Path) -> list[str]:
    """Exported functions that no test file names.

    The runs keep shipping a suite thinner than the product. run-740edb6b's
    `npm test` reported `# tests 1` for an application exporting five
    functions; run-01f03ed9 reported three; run-04576307 had seven test files
    of which one ran. None of that is visible in a passing suite, and a
    reviewer reading "all tests passed" has no way to tell a thorough one from
    a token one.

    Named rather than counted, because the names are what makes it actionable,
    and reported as evidence rather than as a fault: an export used only by
    other application code is legitimately exercised through it, and this
    cannot tell the difference. What it can say exactly is which names appear
    in no test at all.
    """
    tests = [
        path for path in files
        if path.suffix.lower() in {".js", ".mjs", ".cjs", ".ts"}
        and is_test(str(path.relative_to(root)))
    ]
    if not tests:
        return []
    mentioned: set[str] = set()
    for path in tests:
        mentioned.update(re.findall(r"[A-Za-z_$][\w$]*", _read(path)))

    problems: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".js", ".mjs", ".cjs"}:
            continue
        if is_test(str(path.relative_to(root))) or not is_application(str(path.relative_to(root))):
            continue
        exported = _exports_of(_read(path))
        if not exported:
            continue
        untested = sorted(exported - mentioned)
        if not untested:
            continue
        problems.append(
            f"{path.relative_to(root)} exports {len(exported)} name(s) and no "
            f"test mentions {', '.join(untested)}. A passing suite says nothing "
            "about those."
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


#: Importing Node's own builtins. A file that does this is not page code,
#: whatever else is true of it, so "the page never loads it" is not a fault.
_RUNS_ON_NODE = re.compile(
    r"""from\s+['"]node:|require\(\s*['"]node:"""
    r"""|from\s+['"](?:http|https|fs|path|os|net|child_process|crypto|url|zlib)['"]"""
    r"""|require\(\s*['"](?:http|https|fs|path|os|net|child_process|crypto|url|zlib)['"]""",
)


def _reached_only_by_its_tests(files: list[Path], root: Path) -> list[str]:
    """Application modules that nothing but a test ever loads.

    `_orphaned_scripts` asks whether anything references a module at all, and a
    test importing it counts - which is right for "is this file dead code" and
    wrong for "does the product run". A suite can exercise every function in a
    module the page never loads, and does: that is the shape of the failure.

    Run 7e960f06's milestone review found it by reading, which is luck rather
    than design: `index.html` carried no `<script>` tag of any kind, `app.js`
    was imported only by `app.test.mjs`, and the deterministic checks reported
    one untidy problem and nothing else. The suite was 5 of 5 green over a
    product that never loaded.

    Run 0afef410 is the same failure surviving to the end of a run, and this is
    the half of it `_a_page_no_script_ever_touches` does not cover: there the
    page loaded a script that ignored it, here the page loads nothing at all.

    Silent when there is no page, since a library or a CLI is not expected to
    be loaded by one, and silent for a module that imports Node's own builtins.
    Run bb1ee9b's `server.js` opens `import { createServer } from "http"` and is
    imported only by `server.test.mjs`; it is reached only by its tests, but
    "load it from the page" is the wrong thing to tell a server. Whether a
    browser-only product should have one at all is
    `_a_server_in_a_browser_only_product`, and whether anything starts it is
    `_manifest_scripts_that_cannot_resolve`.
    """
    pages = [p for p in files if p.suffix.lower() in {".html", ".htm"}]
    if not pages:
        return []

    loaded: set[str] = set()
    for page in pages:
        text = _read(page)
        loaded.update(Path(src).name for src in _SCRIPT_SRC.findall(text))
        # An inline `<script type="module">` that imports the file loads it
        # just as surely as a `src` attribute does, and is a normal way to
        # write an entry point. Counting only `src` reported that page as
        # never loading its own module.
        for attributes, block in re.findall(
            r"<script\b([^>]*)>(.*?)</script>", text, re.I | re.S
        ):
            if _TAG_SRC.search(attributes):
                continue
            for target in _IMPORT_TARGET.findall(block):
                if target.startswith("."):
                    loaded.add(Path(target).name)
                    loaded.add(Path(target).name + ".js")

    imported_by_product: set[str] = set()
    for path in files:
        if path.suffix.lower() not in {".js", ".mjs", ".cjs"}:
            continue
        relative = str(path.relative_to(root))
        if is_test(relative) or any(part in _SKIP for part in path.parts):
            continue
        for target in _IMPORT_TARGET.findall(_read(path)):
            if target.startswith("."):
                imported_by_product.add(Path(target).name)
                imported_by_product.add(Path(target).name + ".js")

    stranded: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".js", ".mjs", ".cjs"}:
            continue
        relative = str(path.relative_to(root))
        if is_test(relative) or any(part in _SKIP for part in path.parts):
            continue
        if not is_application(relative):
            continue
        if path.name in loaded or path.name in imported_by_product:
            continue
        if _RUNS_ON_NODE.search(_read(path)):
            continue
        # It is only a finding if a test does reach it - otherwise it is plain
        # dead code, which `_unreferenced_scripts` already reports as such.
        reached_by_a_test = any(
            path.name in {Path(t).name, Path(t).name + ".js"}
            for other in files
            if other.suffix.lower() in {".js", ".mjs", ".cjs"}
            and is_test(str(other.relative_to(root)))
            for t in _IMPORT_TARGET.findall(_read(other))
            if t.startswith(".")
        )
        if reached_by_a_test:
            stranded.append(relative)

    if not stranded:
        return []
    listed = ", ".join(sorted(stranded)[:4])
    pages_named = ", ".join(sorted(str(p.relative_to(root)) for p in pages)[:2])
    return [
        f"{listed} is imported by the test suite and by nothing else - no "
        f"`<script>` tag in {pages_named} loads it, and no other application "
        "file imports it. The tests exercise it and the page never runs it, so "
        "a green suite says nothing about whether the product works. Load it "
        "from the page, or the functions it exports reach no user."
    ]


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


#: `"type": "module"` in a manifest, whatever the spacing.
_DECLARES_ESM = re.compile(r'"type"\s*:\s*"module"')

#: How many offending files to name before the list stops being useful.
MAX_CONTRADICTING_FILES = 8


def _files_that_contradict_the_declared_module_type(
    files: list[Path], root: Path
) -> list[str]:
    """CommonJS left in `.js` files after the manifest declared ESM.

    `"type": "module"` reaches every `.js` file in the package at once, and
    `require` and `module` stop existing in all of them. Verified in the worker
    image on Node 20.20.2:

        ReferenceError: require is not defined in ES module scope, you can use
        import instead
        ReferenceError: module is not defined in ES module scope

    Run d6297b2f is what this is for. `specialist_testing_1` added
    `"type":"module"` to the manifest while four of its five test files still
    used `require('../app.js')`, and then converted them one at a time, each
    discovered by a separate failing `npm test`. It also tried three times to
    take the declaration back out with an `edit_artifact` that removed
    `"type":"module"` from a minified manifest and left `{...,,...}` behind,
    refused each time as invalid JSON.

    The declaration is the cheap thing to get right and the expensive thing to
    discover: one line decides how every other file is parsed. So this names
    every file that contradicts it in one finding, rather than letting a test
    run reveal them one by one.

    `.cjs` is the escape hatch and is exempt - verified in the same image, a
    `.cjs` file keeps `require` under `"type": "module"`.
    """
    manifests = [p for p in files if p.name == "package.json"]
    declaring = [p for p in manifests if _DECLARES_ESM.search(_read(p))]
    if not declaring:
        return []

    problems: list[str] = []
    for manifest in declaring:
        package = manifest.parent
        offenders: list[str] = []
        for path in files:
            if path.suffix.lower() != ".js" or not _is_within(path, package):
                continue
            if any(part in _SKIP for part in path.parts):
                continue
            # The nearest manifest wins: a nested package with its own
            # package.json is not governed by this one.
            nearer = [m for m in manifests if m != manifest and _is_within(path, m.parent)]
            if any(_is_within(m.parent, package) and m.parent != package for m in nearer):
                continue
            body = _read(path)
            if _COMMONJS.search(_only_the_code(body)) and not (
                # Raw text for the guard: see `_commonjs_loaded_as_a_module`.
                _FEATURE_DETECTS_COMMONJS.search(body)
            ):
                offenders.append(str(path.relative_to(root)))
        if not offenders:
            continue
        shown = ", ".join(sorted(offenders)[:MAX_CONTRADICTING_FILES])
        more = (
            ""
            if len(offenders) <= MAX_CONTRADICTING_FILES
            else f" and {len(offenders) - MAX_CONTRADICTING_FILES} more"
        )
        problems.append(
            f"{manifest.relative_to(root)} declares `\"type\": \"module\"`, "
            f"which makes every `.js` file in it an ES module, but {shown}"
            f"{more} still use `require` or `module.exports`. Those throw "
            "`ReferenceError: require is not defined in ES module scope` the "
            "moment they load, so the suite cannot run. The declaration governs "
            "all of them at once: either convert every listed file to "
            "`import`/`export`, rename each to `.cjs`, or drop the `\"type\"` "
            "line. Changing them one at a time costs a failing test run per file."
        )
    return problems


#: Runners that define `test`, `it` and `describe` as globals, so a file using
#: them without an import is correct. `node --test` is not one of them.
_PROVIDES_TEST_GLOBALS = ("jest", "vitest", "mocha", "jasmine", "karma", "cypress")

#: `test(`, `it(` or `describe(` called at the file's own top level.
_CALLS_A_SUITE_GLOBAL = re.compile(
    r"""^(?:await\s+)?(test|it|describe)\s*(?:\.\w+\s*)?\(""", re.M
)

#: The binding brought in from `node:test`, however it is spelled.
_IMPORTS_FROM_NODE_TEST = re.compile(
    r"""from\s+['"]node:test['"]|require\(\s*['"]node:test['"]\s*\)"""
    r"""|from\s+['"]test['"]""",
)

#: The file declaring `test`, `it` or `describe` itself. Run 44653b's
#: `Task.test.mjs` opens with its own four-line harness -
#: `function test(name, fn) { try { fn(); ... } }` - and calls it; nothing is
#: missing and nothing throws. A check that reported it would be telling a
#: working file to import a name it already has.
_DEFINES_ITS_OWN = re.compile(
    r"""^\s*(?:async\s+)?function\s+(test|it|describe)\b"""
    r"""|^\s*(?:const|let|var)\s+(test|it|describe)\s*=""",
    re.M,
)


def _suites_calling_a_global_node_does_not_define(
    files: list[Path], root: Path
) -> list[str]:
    """`test(...)` with nothing importing `test`, under `node --test`.

    Jest, Vitest and Mocha inject `test`, `it` and `describe` as globals.
    `node --test` does not: they are exports of `node:test` and a file that
    calls one without importing it throws on the first case. Verified in the
    worker image on Node 20.20.2 - a file whose only content is
    `test("x", () => assert.ok(true))` reports

        ReferenceError: test is not defined
        # tests 1   # pass 0   # fail 1

    Both of the runs that carried this were already deep in a module-system
    tangle when they hit it, and it cost each of them a round of its own. Run
    d6297b2f's `test_round_0` got `ReferenceError: describe is not defined` and
    "fixed" it by moving every case inside a default export, which
    `tests_the_runner_will_never_call` now catches. Run 0afef410's
    `specialist_backend_2` renamed `app.test.mjs` to `app.test.js` and got
    `ReferenceError: test is not defined` for its trouble.

    Silent when the project has a runner that does provide the globals, so
    this can only fire where it is true.
    """
    for path in files:
        if path.name == "package.json":
            manifest = _read(path).lower()
            if any(
                re.search(rf"(?<![\w-]){runner}(?![\w-])", manifest)
                for runner in _PROVIDES_TEST_GLOBALS
            ):
                return []
        elif path.name.lower().startswith(("jest.config", "vitest.config", ".mocharc")):
            return []

    problems: list[str] = []
    for path in files:
        if not is_test(str(path.relative_to(root))):
            continue
        if path.suffix.lower() not in {".js", ".mjs", ".cjs"}:
            continue
        content = _read(path)
        called = _CALLS_A_SUITE_GLOBAL.search(content)
        if not called or _IMPORTS_FROM_NODE_TEST.search(content):
            continue
        if _DEFINES_ITS_OWN.search(content):
            continue
        name = called.group(1)
        problems.append(
            f"{path.relative_to(root)} calls `{name}(...)` and nothing imports "
            f"`{name}`. Jest and Vitest inject it as a global; `node --test` "
            f"does not - it is an export of `node:test`, so every case in this "
            f"file throws `ReferenceError: {name} is not defined` and the suite "
            f"cannot run. Add `import {{ {name} }} from 'node:test';` at the top "
            "of the file."
        )
    return problems


#: Writing text into the page without parsing it as HTML. These cannot inject.
_SAFE_TEXT_INTO_THE_PAGE = re.compile(
    r"""\.textContent\s*=|\.innerText\s*=|createTextNode\s*\(|\.setAttribute\s*\("""
)

#: Writing markup into the page. These parse what they are given.
_MARKUP_INTO_THE_PAGE = re.compile(
    # The whitespace sits INSIDE the lookahead. With `\s*` before it, the
    # engine backtracks that to empty, evaluates the lookahead against the
    # space, and the negative trivially succeeds - so `innerHTML = ""` was
    # reported as markup, which is the exact opposite of what it is.
    r"""\.innerHTML\s*=(?!\s*['"`]\s*['"`])|\.outerHTML\s*=|insertAdjacentHTML\s*\("""
    r"""|document\s*\.\s*write\s*\("""
)


def how_the_page_receives_text(root: str | Path) -> str:
    """A statement of which DOM-writing APIs this product uses, or "".

    Decidable from the source, and stated so a reviewer does not have to infer
    it. Run 1c9854c7's milestone reviewer inferred it wrongly - it recorded a
    major XSS finding against a product whose only text write was
    `textSpan.textContent = task.text` and whose only `innerHTML` was `= ""` -
    and the run was stopped after three revisions over a defect that did not
    exist.

    `innerHTML = ""` is excluded deliberately: clearing a container parses
    nothing. Only an assignment with content in it can inject.
    """
    try:
        base = Path(root)
        files = [
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
            and not any(part in _SKIP for part in path.parts)
            and not is_test(str(path.relative_to(base)))
        ]
    except Exception:  # noqa: BLE001 - evidence that cannot be gathered says nothing
        return ""

    safe: list[str] = []
    markup: list[str] = []
    for path in files:
        body = _read(path)
        name = str(path.relative_to(base))
        if _MARKUP_INTO_THE_PAGE.search(body):
            markup.append(name)
        elif _SAFE_TEXT_INTO_THE_PAGE.search(body):
            safe.append(name)
    if not safe and not markup:
        return ""

    if markup:
        return (
            "\nHow this product writes to the page: "
            + ", ".join(sorted(markup)[:4])
            + " assign markup (`innerHTML` with content, `outerHTML`, "
            "`insertAdjacentHTML` or `document.write`), which parses what it is "
            "given. Whether any of it carries text a user typed is worth "
            "checking.\n"
        )
    return (
        "\nHow this product writes to the page: "
        + ", ".join(sorted(safe)[:4])
        + " put text into the DOM only through `textContent`, `innerText`, "
        "`createTextNode` or `setAttribute`. None of those parses HTML, so "
        "text a user typed cannot become markup this way. An injection finding "
        "about DOM insertion would be incorrect for this code as written "
        "(`innerHTML = \"\"`, which only clears a container, is not an "
        "exception to that).\n"
    )


#: Elements a user operates. A page carrying these is a page meant to do
#: something when they are used.
_A_CONTROL = re.compile(
    r"""<(?:button|input|select|textarea)\b[^>]*\bid\s*=\s*["']([^"']+)["']""",
    re.I,
)

#: Any id on the page, so a script that addresses a container counts too.
_ANY_ID = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)

#: Reaching for the document at all: a query, a listener, a render target.
#: Deliberately broad - the question is whether *anything* touches the page,
#: not whether it does so in a particular style.
_TOUCHES_THE_PAGE = re.compile(
    r"""(?<![\w.$])document\s*\.|(?<![\w.$])window\s*\.addEventListener"""
    r"""|\.addEventListener\s*\(|(?<![\w.$])customElements\b"""
    r"""|\.innerHTML\s*=|\.appendChild\s*\(|(?<![\w.$])createRoot\s*\("""
    r"""|ReactDOM|\bnew\s+Vue\b|\bmount\s*\(""",
)

#: Below this a page is a fragment or a placeholder, not a user interface.
MIN_CONTROLS_BEFORE_REPORTING = 2


def _a_page_no_script_ever_touches(files: list[Path], root: Path) -> list[str]:
    """Controls on the page, and nothing anywhere that operates them.

    The complement of `_page_hooks_that_do_not_exist`, which asks whether the
    ids a script reaches for exist. This asks the other direction: the page
    declares controls, and no script in the project addresses any of them or
    touches the document at all.

    Run 0afef410 completed on this. Its final sprint - "Finalize code,
    documentation, test coverage, and prepare for deployment" - reduced
    `app.js` from 6,388 bytes to 2,345 by removing every line of DOM code:
    no `getElementById`, no listener, no render, no `init`. What was left is
    five pure functions over `localStorage` and an `export`. `index.html`
    still carries `add-btn`, `task-input`, `filter-select` and `task-list`,
    each referenced zero times.

    The page loads, renders its markup, and does nothing at all when used.
    Every gate passed it: `npm test` reported `# tests 9 # pass 9 # fail 0`,
    because the suite imports those five functions directly and never opens the
    page, and the cross-file checks reported no problems because each file is
    individually fine.

    This is run 0c5aabdb's failure a layer down. That one shipped no HTML; this
    one ships HTML and JavaScript that never meet.

    Requires that nothing touches the document anywhere, not merely that these
    ids are unreferenced, so a page wired by class or by tag is left alone.
    """
    scripts = [
        path
        for path in files
        if path.suffix.lower() in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
        and not any(part in _SKIP for part in path.parts)
        and not is_test(str(path.relative_to(root)))
    ]

    problems: list[str] = []
    for page in files:
        if page.suffix.lower() not in {".html", ".htm"}:
            continue
        markup = _read(page)
        controls = _A_CONTROL.findall(markup)
        if len(controls) < MIN_CONTROLS_BEFORE_REPORTING:
            continue
        ids = set(_ANY_ID.findall(markup))

        # An inline script is part of the page and counts as wiring it.
        inline = "\n".join(
            block
            for attributes, block in re.findall(
                r"<script\b([^>]*)>(.*?)</script>", markup, re.I | re.S
            )
            if not _TAG_SRC.search(attributes)
        )
        bodies = [inline] + [_read(path) for path in scripts]
        if any(_TOUCHES_THE_PAGE.search(body) for body in bodies):
            continue
        if any(name in body for body in bodies for name in ids):
            continue

        named = ", ".join(f"`{name}`" for name in sorted(controls)[:4])
        problems.append(
            f"{page.relative_to(root)} carries {len(controls)} control(s) "
            f"({named}) and nothing in this project ever touches the page - no "
            "script reads any of its ids, adds a listener, or reaches for "
            "`document`. The page renders and then does nothing when a user "
            "operates it. A passing test suite is not evidence against this: "
            "the tests import the functions directly and never open the page. "
            "Wire the controls to the functions that exist."
        )
    return problems


#: `jest` as a whole word. `"jest" in text` also matches "pytest", which is how
#: a Python stack once silently satisfied a JavaScript check.
_USES_JEST = re.compile(r"(?<![\w-])jest(?![\w-])", re.I)


def _module_system_mismatch(files: list[Path], root: Path) -> list[str]:
    """ES module source under a test runner that genuinely cannot parse it.

    This check used to fire on any ESM source with no declared module type, and
    told the stage:

        A test that imports them gets "does not provide an export named ..." -
        the runner loads them as CommonJS and the exports are invisible.

    That is not true of the runtime this harness runs on. Measured directly in
    the worker image on Node 20.20.2: a project with `{"name":"p"}` for a
    manifest, `app.js` containing `export function addTask(...)`, and a test
    doing `import { addTask } from "./app.js"` reports

        # tests 1   # pass 1   # fail 0

    Node has detected module syntax in a typeless `.js` since 20.19 and simply
    reparses the file, printing a MODULE_TYPELESS_PACKAGE_JSON performance
    warning and working correctly. The original observation came from run
    da6c5e19, where the note "we can't directly import app.js" was written by
    the agent in its own test file - the agent's diagnosis, recorded here as
    Node's behaviour, and wrong.

    A check that is wrong is worse than a check that is missing: this one
    raised a blocking finding against a working project and sent a stage to fix
    it. So it now fires only for Jest, which really does need a `transform` to
    read ESM and really does fail with `SyntaxError: Cannot use import
    statement outside a module`.

    The browser half of this question is not affected and never was:
    `_modules_loaded_as_plain_scripts` catches `export` behind a classic
    `<script>` tag, which no browser reparses, and `_commonjs_loaded_as_a_module`
    catches the reverse.
    """
    esm_sources = [
        path
        for path in files
        if path.suffix.lower() in {".js", ".mjs"}
        and not (not is_application(str(path.relative_to(root))))
        and _ESM.search(_read(path))
    ]
    if not esm_sources:
        return []

    uses_jest = False
    for path in files:
        name = path.name.lower()
        if name == "package.json":
            manifest = _read(path)
            if '"type"' in manifest and '"module"' in manifest:
                return []
            if _USES_JEST.search(manifest):
                uses_jest = True
        elif name.startswith("jest.config"):
            if "transform" in _read(path):
                return []
            uses_jest = True

    # Anything else - `node --test`, vitest, a browser-only product - either
    # handles this or is covered by a check that is right about it.
    if not uses_jest:
        return []

    listed = ", ".join(sorted(str(p.relative_to(root)) for p in esm_sources)[:4])
    return [
        f"{listed} use ES module syntax, and this project runs Jest with no "
        "`transform` configured. Jest reads them as CommonJS and throws "
        "`SyntaxError: Cannot use import statement outside a module`, so the "
        'suite cannot run at all. Set `"type": "module"` in `package.json`, '
        "configure a `transform`, or write the sources as CommonJS."
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
            # `_a_test_runner_the_stack_did_not_choose` reports this exact
            # fact for JavaScript, naming the manifest and what goes wrong, and
            # as BREAKS rather than untidy - a suite written for a runner the
            # stack did not choose fails on that runner's setup. Reporting it
            # here too gave a reviewer the same finding twice at two different
            # severities. Python keeps this path; that check reads package.json.
            if field == "testing_framework" and ecosystem == "javascript":
                continue
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
    "starts an HTTP server, and this run's",  # a server a browser-only stack forbids
    "does not exist from",               # a manifest script naming a bad path
    "parses it as a classic script",     # ESM behind a plain <script> tag
    "looks for the element id",          # a script hook no page provides
    "reads the attribute",               # a data-* attribute nothing sets
    "which does not exist in the workspace",  # a src/import pointing at nothing
    "The page loads it and gets nothing",     # an empty file that is loaded
    "so no tool can read it",            # a manifest that will not parse
    "calls its own copy rather",         # a redefinition instead of an import
    "relative to whatever directory",    # a path that depends on the cwd
    "declares no `test` script",         # `npm test` cannot run
    "placeholder test script",           # `npm test` fails by default
    "as the testing framework",          # a runner installed over the chosen one
    "so the suite cannot fail",          # a test that makes no claim at all
    "throws `TypeError` the moment",     # assertions called on `node:test`
    "does not export it",                # the named form of the same import
    "is not defined` and the suite",     # a suite global nothing imported
    "does nothing when a user",          # a page no script ever wires
    "the page never runs it",            # a module only its tests load
    "only checks that something exists",  # a suite of existence checks
    "none of the cases execute",         # a suite the runner never calls
    "and nothing on it works",           # CommonJS behind a module script tag
    "so the suite cannot run",           # files against a declared module type
)


def _severity_of(problem: str) -> str:
    return "BREAKS" if any(mark in problem for mark in _BREAKS_BEHAVIOUR) else "untidy"


#: Storage that lives in the browser and nowhere else. A product whose data
#: layer is one of these has no server by definition.
_BROWSER_ONLY_STORAGE = ("localstorage", "sessionstorage", "indexeddb", "web storage")

#: Starting an HTTP listener, in the forms this harness's products use.
_STARTS_A_SERVER = re.compile(
    r"""(?<![\w.$])createServer\s*\("""
    r"""|(?<![\w.$])listen\s*\(\s*(?:\d|process\.env|PORT|port)"""
    r"""|(?<![\w.$])express\s*\(\s*\)"""
    r"""|Deno\.serve\s*\(|Bun\.serve\s*\("""
)


def _a_server_in_a_browser_only_product(files: list[Path], root: Path, stack: Any) -> list[str]:
    """A server in a product whose own stack says there is none.

    run-bb1ee9bb chose "Vanilla JavaScript" with "Web LocalStorage", and wrote
    its own rationale: "Web LocalStorage meets this requirement without any
    server or additional libraries ... the application runs entirely in the
    browser". A specialist then wrote a 3,696-byte `server.js` -
    `createServer` from `node:http`, persisting to `data.json`, with its own
    test file - and a second data layer the page never talks to.

    `describe_stack` tells every specialist not to introduce a different
    language, framework, database or test runner. A server is none of those
    four, so nothing said no.

    Only when the declared storage is browser-only: a product with a real
    database is expected to have a server, and this must not say a word about
    it.
    """
    if stack is None:
        return []
    database = str(getattr(stack, "database", "") or "").lower()
    if not any(marker in database for marker in _BROWSER_ONLY_STORAGE):
        return []

    problems: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts"}:
            continue
        if is_test(str(path.relative_to(root))):
            continue
        text = _read(path)
        if not _STARTS_A_SERVER.search(text):
            continue
        problems.append(
            f"{path.relative_to(root)} starts an HTTP server, and this run's "
            f"stack declares its storage as '{getattr(stack, 'database', '')}' - "
            "which lives in the browser, so the product it describes has no "
            "server and no server-side data. Either the stack is wrong or this "
            "file is a second data layer the page never talks to."
        )
    return problems


#: Test runners that arrive as a package, with the names a stack would use for
#: each. A stack naming one of these has chosen it; a project that installs one
#: the stack did not name has overruled the choice.
_TEST_RUNNERS: dict[str, tuple[str, ...]] = {
    "jest": ("jest",),
    "mocha": ("mocha",),
    "vitest": ("vitest", "vite test"),
    "jasmine": ("jasmine",),
    "ava": ("ava",),
    "tape": ("tape",),
    "qunit": ("qunit",),
    "karma": ("karma",),
    "cypress": ("cypress",),
    "playwright": ("playwright",),
    "@playwright/test": ("playwright",),
    "uvu": ("uvu",),
}


def _a_test_runner_the_stack_did_not_choose(files: list[Path], root: Path, stack: Any) -> list[str]:
    """A test framework installed over the one the stack selected.

    Measured on run 8d28ee3f. `stack_selector` chose
    `testing_framework: "Custom JS assert tests"` and wrote its reason: "A
    custom JS assertion suite is sufficient for headless testing in the current
    environment (no node test runners available), avoiding large dependencies."

    `specialist_ui_ux_0` then ran `npm install --save-dev jest`, wrote
    `app.test.js` against jest, and spent four `npm test` calls on
    `TextEncoder is not defined` and `TextEncoder is not a constructor` -
    jsdom failures that belong to the runner it had just installed and that
    the chosen approach could not have hit.

    Only fires when the stack named a runner and the project installed a
    *different* one. A stack that says "jest" and a project with jest is the
    normal case and must stay silent, as must a project with no manifest.
    """
    if stack is None:
        return []
    declared = str(getattr(stack, "testing_framework", "") or "").strip().lower()
    if not declared:
        return []

    problems: list[str] = []
    for path in files:
        if path.name != "package.json":
            continue
        try:
            manifest = json.loads(_read(path) or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(manifest, dict):
            continue
        installed = {
            *(manifest.get("dependencies") or {}),
            *(manifest.get("devDependencies") or {}),
        }
        for package in sorted(installed):
            aliases = _TEST_RUNNERS.get(package.lower())
            if not aliases:
                continue
            # On word boundaries, not as a substring. `"jest" in "pytest"` is
            # true, so a stack that chose pytest silently accepted jest - which
            # `test_the_wrong_test_runner_is_reported` caught.
            if any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", declared)
                   for alias in aliases):
                continue
            chosen = getattr(stack, "testing_framework", "")
            problems.append(
                f"{path.relative_to(root)} installs '{package}', but this run's "
                f"stack chose '{chosen}' as the testing framework. Tests written "
                "for a runner the stack did not choose fail on that runner's own "
                "setup, not on the product. Either use the chosen approach or "
                "change the stack."
            )
    return problems


def _tests_that_cannot_fail(files: list[Path], root: Path) -> list[str]:
    """Test files whose cases cannot fail, or never run at all.

    The write-time note fires when one is written; this is the reviewer's
    copy, for a suite assembled across several stages where no single write
    was the moment it became vacuous. See
    `app.analysis.test_discovery.a_test_that_asserts_nothing`.
    """
    from app.analysis.test_discovery import (
        a_suite_that_only_checks_things_exist,
        a_test_that_asserts_nothing,
        assertions_called_on_the_test_module,
        tests_the_runner_will_never_call,
    )

    problems: list[str] = []
    for path in files:
        relative = str(path.relative_to(root))
        content = _read(path)
        for problem in (
            assertions_called_on_the_test_module(relative, content),
            a_test_that_asserts_nothing(relative, content),
            tests_the_runner_will_never_call(relative, content),
            a_suite_that_only_checks_things_exist(relative, content),
        ):
            if problem:
                problems.append(problem)
    return problems


#: Every cross-file check, with the phrase that describes it to a reviewer.
#:
#: One list so the two cannot drift. The sentence naming what was checked was
#: hand-written and hand-maintained, and by the time four more checks had been
#: added it described none of them - a reviewer reading "here is what was
#: checked" got a list four items short. Deriving the sentence from the checks
#: that actually run makes that impossible rather than unlikely.
_CHECKS: tuple[tuple[str, Any], ...] = (
    ("the chosen stack against what is on disk",
     lambda files, root, stack: _stack_conflicts(files, root, stack)),
    ("test files that cannot fail, never run, or throw before they can",
     lambda files, root, stack: _tests_that_cannot_fail(files, root)),
    ("the installed test runner against the one the stack chose",
     lambda files, root, stack: _a_test_runner_the_stack_did_not_choose(files, root, stack)),
    ("CommonJS behind a module script tag, which no browser can run",
     lambda files, root, stack: _commonjs_loaded_as_a_module(files, root)),
    ("a server against a stack that says the product runs in the browser",
     lambda files, root, stack: _a_server_in_a_browser_only_product(files, root, stack)),
    ("manifests against the project they describe",
     lambda files, root, stack: _manifest_defects(files, root, stack)),
    ("stylesheet id selectors against declared element ids",
     lambda files, root, stack: _dangling_id_selectors(files, root)),
    ("the ids and data attributes scripts reach for against the page",
     lambda files, root, stack: _hooks_javascript_reaches_for(files, root)),
    ("test files against the project's own test command",
     lambda files, root, stack: _tests_the_project_never_runs(files, root)),
    ("module syntax against the script tag that loads it",
     lambda files, root, stack: _modules_loaded_as_plain_scripts(files, root)),
    ("paths in package.json scripts against where npm runs them",
     lambda files, root, stack: _manifest_scripts_that_cannot_resolve(files, root)),
    ("exported names against the names any test mentions",
     lambda files, root, stack: _exports_no_test_mentions(files, root)),
    ("stylesheet class selectors against the elements that carry them",
     lambda files, root, stack: _dangling_class_selectors(files, root)),
    ("commands the documents tell a reader to run",
     lambda files, root, stack: _documented_commands_that_cannot_run(files, root, root / "docs")),
    ("HTML script and stylesheet references against the files they name",
     lambda files, root, stack: _broken_local_references(files, root)),
    ("application modules against whatever loads them",
     lambda files, root, stack: _unreferenced_scripts(files, root)),
    ("tests against the module they should be importing",
     lambda files, root, stack: _redefined_instead_of_imported(files, root)),
    ("application code against the page it is embedded in",
     lambda files, root, stack: _application_embedded_in_html(files, root)),
    ("languages against the directory they share",
     lambda files, root, stack: _languages_sharing_a_directory(files, root)),
    ("application modules the page never loads, only the tests",
     lambda files, root, stack: _reached_only_by_its_tests(files, root)),
    ("a page whose controls no script anywhere operates",
     lambda files, root, stack: _a_page_no_script_ever_touches(files, root)),
    ("suite functions called without the import that defines them",
     lambda files, root, stack: _suites_calling_a_global_node_does_not_define(files, root)),
    ("files that contradict the module type their manifest declares",
     lambda files, root, stack: _files_that_contradict_the_declared_module_type(files, root)),
    ("module syntax against a test runner that cannot parse it",
     lambda files, root, stack: _module_system_mismatch(files, root)),
    ("tests against the directory they are run from",
     lambda files, root, stack: _tests_that_depend_on_the_working_directory(files, root)),
    ("the size of the product against the budget its own documents state",
     lambda files, root, stack: _over_the_declared_budget(files, root, _orphans_quietly(files, root))),
)


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
        problems = []
        for describe, check in _CHECKS:  # noqa: B007 - the description is used below
            problems.extend(check(files, root, stack))
    except Exception:  # noqa: BLE001
        return "The cross-file checks could not complete on this workspace."

    checked = (
        f"Cross-file checks ran over {len(files)} files: "
        + ", ".join(describe for describe, _ in _CHECKS)
        + "."
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
