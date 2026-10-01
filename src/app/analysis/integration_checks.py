"""Check that files written separately actually refer to each other.

Every specialist writes its own files and each one is defensible alone. What
no stage checks is whether they connect, and that is where this pipeline's
output keeps breaking.

Measured on one run, milestone 1 produced four files and three of these
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
from pathlib import Path, PurePosixPath
from typing import Any
from app.analysis.walk import files_under

#: Directories that are never the project's own source.
#: The harness's own files, never the product's. Read from one place.
_HARNESS_BOOKKEEPING = frozenset({
    ".project-directory", ".project-stack", ".project-memory.json", ".work-order-files.json",
})

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
    # Added 2026-09-19. A workspace holding only these came back "No HTML, CSS
    # or JavaScript files were found to cross-check" - no size count, no
    # evidence block, and a milestone reviewer that cannot block because it
    # was handed nothing. The list had grown once already, for Python and Go,
    # and stopped at the languages in front of it at the time.
    #
    # Collection is deliberately wider than any single check: each check
    # filters this list by the suffixes it understands, so a language here
    # costs nothing until something knows what to do with it, and a language
    # absent here is invisible to all of them at once.
    ".kt", ".kts", ".scala", ".swift", ".dart", ".ex", ".exs",
    ".c", ".h", ".cpp", ".cc", ".hpp", ".m", ".mm",
    ".pl", ".lua", ".sql", ".sh", ".bash", ".less", ".pyi",
})


def _source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in files_under(root, _SKIP):
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
        if path.name in _HARNESS_BOOKKEEPING:
            continue
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


#: Where a test runner writes markdown of its own. A Playwright failure leaves
#: `test-results/<case>/error-context.md`, which records a run rather than
#: telling anybody to do anything.
_RUNNER_OUTPUT_OF_A_TEST = frozenset({
    "test-results", "playwright-report", "coverage", "htmlcov",
    ".pytest_cache", "allure-results", "cypress",
})


_DOC_COMMAND = re.compile(
    r"`(?:node|python3?|bash|sh)\s+([\w./-]+\.(?:js|mjs|cjs|py|sh))`"
)


def _documented_commands_that_cannot_run(files: list[Path], root: Path, docs: Path) -> list[str]:
    """Documentation telling a reader to run a file the project does not have.

    A document is the one artefact nobody executes, so a wrong instruction in it
    survives every test round and reaches whoever tries to use the product.

    Measured on one run, whose `docs/deployment.md` said "Run with
    `node server.js`, then open http://localhost:3000" for a product whose
    files are `app.js`, `app.test.mjs`, `index.html`, `package.json` and
    `style.css`. Four milestone reviews read that document and none tried the
    command. One run shipped the same shape - a README citing
    `npm run build-static`, which did not exist.

    Only a bare filename in a code span, so prose about a hypothetical server
    and a command with a real path elsewhere are both left alone.

    Every markdown file in the workspace, not only `docs/*.md`. It scanned
    `root/docs` alone, which is the *workflow's* directory - the nine documents
    it renders from structured responses, and the one directory every agent is
    refused a write to, with the writing rules telling them documentation that
    ships with the product "goes inside the project folder beside the code it
    describes". So a product README was the one place this could never look, and
    a README is what its own evidence is about: one run "shipped the same
    shape - a README citing `npm run build-static`".

    It had no test and fired on none of the 76 stored workspaces. Those hold
    `workspace-one run/README.md`, `.../task-manager/README.md` and
    `.../simple-to-do-list-app/README.md`, none of which it read.

    Test output is skipped: a Playwright failure writes
    `test-results/<case>/error-context.md`, which is a record of a run rather
    than an instruction to anybody.
    """
    present = {p.name for p in files} | {str(p.relative_to(root)) for p in files}

    documents: list[Path] = []
    try:
        for path in sorted(files_under(root, _SKIP, "*.md")):
            if not path.is_file():
                continue
            parts = path.relative_to(root).parts
            if any(part in _SKIP for part in parts):
                continue
            if any(part in _RUNNER_OUTPUT_OF_A_TEST for part in parts):
                continue
            documents.append(path)
    except Exception:  # noqa: BLE001 - a workspace that cannot be walked says nothing
        return []

    problems = []
    for document in documents:
        text = _read(document)
        missing = sorted({
            name for name in _DOC_COMMAND.findall(text)
            if Path(name).name not in present and name not in present
        })
        if not missing:
            continue
        listed = ", ".join(f"`{name}`" for name in missing[:3])
        problems.append(
            f"{document.relative_to(root)} tells a reader to run {listed}, and no "
            "such file exists in this project. A document is the one artefact "
            "nobody executes, so the instruction survives every test round and "
            "reaches whoever tries to use the product."
        )
    return problems


def _dangling_class_selectors(files: list[Path], root: Path) -> list[str]:
    """Stylesheet rules for a class nothing ever puts on an element.

    Unlike an id, a class is often added at runtime - so this counts any
    mention of the name anywhere in the scripts, not only a `classList.add`.
    A rule survives if the word appears at all; it is reported only when no
    page and no script contains it in any form.

    Measured on one run's second sprint, where the reviewer found this by
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


#: The ways a script gives an element an id. None of them contains a `#`, which
#: is what the CSS selector pattern matches - so reading script text with
#: `_ID_SELECTOR` found only ids the script *queries*, never one it *creates*,
#: and every dynamically built element read as undeclared.
#:
#: Demonstrated on four normal spellings, all of which were flagged: `n.id =
#: 'error-notice'`, `n.setAttribute('id', 'error-notice')`, an `id="..."` inside
#: a template literal, and the genuine case of an id nothing creates. Only the
#: last should be reported.
_JS_ASSIGNS_AN_ID = re.compile(r"""\.id\s*=\s*["'`]([A-Za-z][\w-]*)["'`]""")
_JS_SETS_AN_ID = re.compile(
    r"""setAttribute\s*\(\s*["']id["']\s*,\s*["']([A-Za-z][\w-]*)["']"""
)


#: DOM events that do not bubble, and the bubbling event to use instead. A
#: handler attached to a container for one of these never fires for a child, so
#: event delegation with it is dead code that throws nothing.
_DOES_NOT_BUBBLE = {
    "blur": "focusout",
    "focus": "focusin",
    "mouseenter": "mouseover",
    "mouseleave": "mouseout",
}

#: `container.addEventListener('blur', ...`, capturing the target and the event.
_A_LISTENER = re.compile(
    r"""(\w+)\s*\.addEventListener\s*\(\s*['"](\w+)['"]""",
)

#: How far past the call to look for the delegation tell. A handler longer than
#: this is not the shape this reads.
_HANDLER_WINDOW = 900

#: What says a handler is delegating rather than handling its own element:
#: it looks at what the event came from.
_DELEGATES = re.compile(r"""\.target\b""")


def _a_delegated_handler_for_an_event_that_does_not_bubble(
    files: list[Path], root: Path
) -> list[str]:
    """A container listening for an event that never reaches it, or [].

    Event delegation works because the event bubbles from the child to the
    container. `blur`, `focus`, `mouseenter` and `mouseleave` do not bubble, so a
    delegated handler for one of them is never called - and nothing throws, no
    test fails, and the feature is simply dead.

    Measured on one run, which failed at the milestone revision limit. Its
    `task-manager/app.js` line 151 held

        listContainer.addEventListener('blur', e => { ... e.target ... })

    for inline editing, and the reviewer found it:

        [blocking] correctness: The blur-based save for inline editing is still
        broken ... the `blur` event does not bubble in the DOM event flow. When a
        user clicks outside or tabs away from the inline edit input, the blur
        fires on the input element itself and never reaches `listContainer`, so
        the handler never executes and changes are silently lost.

    Three revisions later the run stopped. The reviewer read it correctly; nothing
    in the harness could.

    Reported only when the handler looks at `event.target`, which is what says it
    is delegating rather than handling its own element. A `blur` handler attached
    to the input itself is correct and common, and must stay silent.
    """
    problems: list[str] = []
    for path in files:
        if path.suffix.lower() not in _CLIENT_LOGIC_SUFFIXES:
            continue
        relative = str(path.relative_to(root))
        if is_test(relative):
            continue
        text = _read(path)
        for match in _A_LISTENER.finditer(text):
            target, event = match.group(1), match.group(2).lower()
            instead = _DOES_NOT_BUBBLE.get(event)
            if not instead:
                continue
            handler = text[match.end() : match.end() + _HANDLER_WINDOW]
            # Only as far as the next listener, so one handler's body is not read
            # as another's.
            following = handler.find(".addEventListener")
            if following > 0:
                handler = handler[:following]
            if not _DELEGATES.search(handler):
                continue
            line = text.count("\n", 0, match.start()) + 1
            problems.append(
                f"{relative} line {line} attaches a `{event}` handler to "
                f"`{target}` and the handler reads `event.target`, so it is "
                f"delegating - but `{event}` does not bubble. The event fires on "
                f"the child and never reaches `{target}`, so this handler never "
                f"runs: nothing throws, no test fails, and the feature is simply "
                f"dead. Use `{instead}`, which is the bubbling counterpart, or "
                f"attach the `{event}` handler to the element itself when it is "
                f"created."
            )
    return problems


#: `describe('name'`, `test('name'` and `it('name'` at a test file's top level.
#: `[ \t]*`, not `\s*`: `\s` matches a newline, so the match could start on the
#: line before and every reported line number came out one too low. The message
#: tells a reader which block to delete, so the number has to be the real one.
#:
#: The name runs to the quote that opened it. `([^'"`]+)` stopped at the first
#: quote of any kind, so one run's `describe("filterTasks('all')", ...)`,
#: `describe("filterTasks('active')", ...)` and `describe("filterTasks('completed')", ...)`
#: were all read as `filterTasks(`, reported as one suite registered three
#: times, and cost a milestone revision renaming three distinct suites.
_A_SUITE_NAME = re.compile(
    r"""^[ \t]*(?:test\s*\.\s*)?(describe|suite)\s*\(\s*(['"`])((?:\\.|(?!\2).)+)\2""", re.M
)


def _a_suite_registered_twice(files: list[Path], root: Path) -> list[str]:
    """A test file registering the same suite name twice, or [].

    Both copies run. The count the gates read is inflated by the duplicate, and a
    reader comparing "tests passed" against the suite cannot reconcile them.

    Measured on one run, whose `task-manager/app.test.mjs` declares
    `describe('editTask', ...)` at line 167 and again at line 245. Its milestone
    review found it:

        [minor] code_quality: Duplicate test describe block in app.test.mjs. The
        `describe('editTask', ...)` block appears twice, causing the same set of
        unit tests to be registered and run twice by node:test, wasting CI time
        and cluttering test output.

    Named because it is the kind of thing a whole-file rewrite produces - a block
    appended rather than replaced - and the run had six specialists writing that
    project.
    """
    problems: list[str] = []
    for path in files:
        relative = str(path.relative_to(root))
        if not is_test(relative):
            continue
        if path.suffix.lower() not in _CLIENT_LOGIC_SUFFIXES:
            continue
        seen: dict[str, list[int]] = {}
        text = _read(path)
        for match in _A_SUITE_NAME.finditer(text):
            name = match.group(3).strip()
            seen.setdefault(name, []).append(text.count("\n", 0, match.start()) + 1)
        for name, lines in seen.items():
            if len(lines) < 2:
                continue
            where = ", ".join(str(line) for line in lines)
            problems.append(
                f"{relative} registers the suite `{name}` {len(lines)} times, at "
                f"lines {where}. Every copy runs, so the case count every gate in "
                f"this pipeline reads is inflated by the duplicates and no reader "
                f"can reconcile it with the suite. Keep one and delete the rest."
            )
    return problems


def _dangling_id_selectors(files: list[Path], root: Path) -> list[str]:
    """Stylesheet rules that target an element id nothing ever creates.

    Ids only. A class may legitimately be added at runtime by script, and
    `_dangling_class_selectors` above reasons about those separately.

    An id a script creates counts as declared. That was the intent from the
    start - the comment said so - but the pattern used to look for it was
    `_ID_SELECTOR`, which matches CSS `#name`. A script writes `n.id = 'name'`,
    `setAttribute('id', 'name')` or `id="name"` inside markup it builds, and none
    of those contains a `#`, so the only thing that ever counted was an id the
    script *queried* by selector. Every element built at runtime read as
    undeclared.

    Latent rather than realised: across the 77 stored workspaces this check
    produces 2 findings and both are genuine, because those products happen to
    put every styled id in their markup. A product that renders its UI from
    script - which is most of what this harness is asked to build - would have
    been told its live rules were dead.

    TypeScript and the component suffixes are read too. The class check beside
    this one already read them; this one listed only `.js`, `.mjs` and `.cjs`, so
    a product whose logic is in `.ts` had none of its ids counted at all.
    """
    declared: set[str] = set()
    for path in files:
        suffix = path.suffix.lower()
        if suffix in {".html", ".htm"}:
            declared.update(_HTML_ID.findall(_read(path)))
        elif suffix in _CLIENT_LOGIC_SUFFIXES:
            text = _read(path)
            # Queried, assigned, set, or written into markup the script builds.
            declared.update(_ID_SELECTOR.findall(text))
            declared.update(_JS_ASSIGNS_AN_ID.findall(text))
            declared.update(_JS_SETS_AN_ID.findall(text))
            declared.update(_HTML_ID.findall(text))

    problems = []
    for path in files:
        if path.suffix.lower() not in {".css", ".scss", ".sass"}:
            continue
        targeted = set(_ID_SELECTOR.findall(_css_selectors_only(_read(path))))
        for identifier in sorted(targeted - declared):
            problems.append(
                f"{path.relative_to(root)} styles `#{identifier}`, and no page "
                "declares it and no script creates it. The rule never applies - "
                "either it is dead, or the element it was written for was never "
                "built."
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

#: `setAttribute("data-field", "title")` - the other way a script gives an
#: element an attribute it will later read. `_JS_ASSIGNS_ID` has had the
#: `setAttribute` form since it was written and the data-attribute side did
#: not, which is the §1-B mistake again: a rule covering part of the set it
#: governs. One run built inline editing whose inputs carry
#: `setAttribute('data-field', 'title')` and whose handler reads
#: `[data-field="title"]`, and was reported as reading an attribute "which no
#: HTML element sets" - a blocking finding against working code.
_JS_SETS_DATA_ATTRIBUTE = re.compile(
    r"""setAttribute\(\s*["']data-([A-Za-z][\w-]*)["']"""
)
_HTML_DATA_ATTR = re.compile(r"""\bdata-([A-Za-z][\w-]*)\s*=""")

#: `data-id="${task.id}"` inside a string or template literal the script turns
#: into markup. A hyphenated name cannot be a JavaScript identifier, so this
#: shape in a script is always markup - except inside an attribute selector,
#: `[data-id="3"]`, which reads the attribute; `_markup_data_attributes` skips
#: those.
_MARKUP_DATA_ATTR = re.compile(r"""\bdata-([A-Za-z][\w-]*)\s*=\s*["'`$\\]""")


def _markup_data_attributes(script: str) -> set[str]:
    """The data attributes a script writes into markup it builds.

    Measured on one run: `render()` built each row with
    `innerHTML = filtered.map(task => `<li ... data-id="${task.id}">`)`, the
    delegated click handler read `dataset.id`, and the check reported
    "reads the attribute `data-id`, which no HTML element sets" - at the tier
    handed to the test round as already proven, against code that worked. Only
    `dataset.x =` and `setAttribute` counted as setting an attribute, and the
    most common way a script creates elements was neither.
    """
    found: set[str] = set()
    for match in _MARKUP_DATA_ATTR.finditer(script):
        before = script[:match.start()].rstrip()
        if before.endswith("["):
            continue
        found.add(match.group(1))
    return found
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

    Measured on one run, the first run of this harness to reach `complete`.
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

        set_here = {_camel_to_dashed(n) for n in _JS_ASSIGNS_DATASET.findall(text)}
        set_here.update(_JS_SETS_DATA_ATTRIBUTE.findall(text))
        set_here.update(_markup_data_attributes(text))
        read_here = {
            _camel_to_dashed(name) for name in set(_JS_DATASET.findall(text))
        }
        for selector in _JS_QUERY.findall(text):
            read_here.update(_JS_DATA_SELECTOR.findall(selector))
        # `set_here` is subtracted once, at the end, rather than from the
        # `dataset` reads alone. Subtracting it early left the selector path -
        # `querySelector('[data-field="title"]')` - to put the attribute back,
        # so a script that set an attribute and then looked it up by selector
        # was still reported for reading what nothing sets.
        for attribute in sorted(read_here - declared_data - set_here):
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


def _looks_like_a_test_command(body: str) -> bool:
    """Whether an npm script runs tests, by what it invokes."""
    text = (body or "").lower()
    return any(
        runner in text
        for runner in ("playwright", "jest", "vitest", "mocha", "node --test", "cypress", "ava")
    )


#: Imports that mean a test file belongs to a runner other than `node --test`.
#: Each of these throws under `node --test` rather than merely failing.
_ANOTHER_RUNNERS_IMPORT = re.compile(
    r"""from\s+['"](@playwright/test|vitest|@jest/globals|cypress|mocha|ava)['"]""",
    re.I,
)


#: A suite written for Node's own runner. `node:test` is the only import that
#: settles it - a file using bare `describe` could belong to any of four
#: runners, and guessing would strand a suite that runs perfectly well.
_IMPORTS_NODE_TEST = re.compile(r"""(?:from|require\()\s*['"]node:test['"]""")


def _node_suites_nothing_runs(files: list[Path], root: Path) -> list[str]:
    """`node:test` suites in a project whose scripts never invoke `node --test`.

    `_tests_the_project_never_runs` asks this question only of a manifest whose
    `scripts.test` already contains `node --test`, for a good reason it states:
    Jest, Vitest and Playwright decide discovery in their own configuration,
    which it cannot read, so a claim about them could be wrong.

    The effect is that the check gets weaker the worse the problem gets.
    Changing the runner does not answer it - it exempts the manifest from being
    asked.

    Measured live on one run. `scripts.test` was
    `node --test main.test.js storage.test.js`, and this harness refused that
    write, correctly, because it left `main.crud.test.js` unrun. The next write
    made `scripts.test` be `npx playwright test`, which runs none of the three,
    and every check fell silent - `_tests_the_project_never_runs` and
    `_manifest_defects` both returned nothing against that workspace. The
    ledger shows the suite the gates measured going 13 tests to 1:

        09:21:25  npm test       tests=13  passed=6   failed=7
        09:26:50  npm test       tests=13  passed=9   failed=4
        09:39:18  npm test       tests=13  passed=9   failed=4
        09:40:21  playwright     tests=1   passed=0   failed=1
        09:41:05  npm run test   tests=1   passed=0   failed=1

    Ten test cases dropped out of what the gates measured and nothing said so.
    Later in the same run, with `scripts.test` still `npx playwright test`, the
    two commands disagreed outright:

        09:54:09  node --test    tests=17  passed=10  failed=7
        09:59:34  npm run test   tests=3   passed=2   failed=1

    Fourteen cases outside the only number any gate reads. The claim here is
    that disagreement and not a stronger one: Playwright's default `testMatch`
    does pick these filenames up, so some of their assertions do run, and
    "never executed" would be false. A blocking finding that is false is the
    worst shape a check can take - see `_belongs_to_another_runner` - so this
    says what is certain, which is that the count the gates measure is not the
    count these files hold.

    The same false green as two runs reached from the
    opposite direction, and it borrows their words.

    Decided without reading any runner's configuration. A file importing
    `node:test` needs `node --test`; if no script in the manifest invokes it,
    that file is not run by anything, whatever Playwright's `testMatch` happens
    to say. Every script is consulted, not only `test`, so a suite reachable
    through `npm run unit` is not reported as unreachable.
    """
    problems: list[str] = []
    for manifest in files:
        if manifest.name != "package.json":
            continue
        try:
            scripts = (json.loads(_read(manifest)) or {}).get("scripts") or {}
        except Exception:  # noqa: BLE001 - a broken manifest is reported elsewhere
            continue
        if any("node --test" in str(body) for body in scripts.values()):
            continue
        command = str(scripts.get("test") or "")
        if not command:
            continue
        project = manifest.parent
        orphans = sorted(
            str(path.relative_to(root))
            for path in files
            if path.suffix.lower() in {".js", ".mjs", ".cjs"}
            and is_test(str(path.relative_to(root)))
            and _is_within(path, project)
            and _IMPORTS_NODE_TEST.search(_read(path))
        )
        if not orphans:
            continue
        names = ", ".join(orphans)
        problems.append(
            f"{manifest.relative_to(root)} has no script that runs {names} - "
            f"they import `node:test`, which needs `node --test`, and no script "
            f"in this manifest invokes it. `scripts.test` is `{command}`, which "
            "is the one command every gate in this pipeline measures the suite "
            "by, and whatever it collects from these files is not what Node's "
            "runner would: the number the gates read is not the number of "
            "assertions these files hold. Add `node --test` to `test`, or have "
            "`test` run both suites, so one command proves the whole product."
        )
    return problems


def _belongs_to_another_runner(path: Path) -> str:
    """The runner that owns this test file, or "" for a plain `node --test` one.

    `node --test` does not merely fail on another runner's spec, it throws
    before a single assertion runs. Verified in this image on 2026-09-21::

        $ node --test e2e/task-manager.spec.js
        Error: Playwright Test did not expect test.describe() to be called here.

    That matters because `_tests_the_project_never_runs` tells a stage to "name
    them too" in `scripts.test`. For a Playwright spec that instruction is not
    merely unhelpful, it breaks a suite that was passing: the run that found
    this had twenty Playwright assertions green under `npx playwright test`, and
    the check was recommending a change that would have thrown on all of them.

    A blocking finding whose remedy breaks the product is the worst shape a
    check can have, because the stage will do as it is told.
    """
    found = _ANOTHER_RUNNERS_IMPORT.search(_read(path))
    return found.group(1) if found else ""


#: The command that runs each runner's specs, keyed by the import that
#: identifies them. Not derived from the package name: see
#: `other_scripts_that_run_them`.
_RUNNER_COMMANDS = {
    "@playwright/test": "playwright",
    "@jest/globals": "jest",
    "vitest": "vitest",
    "cypress": "cypress",
    "mocha": "mocha",
    "ava": "ava",
}


def other_scripts_that_run_them(scripts: dict, owned: dict) -> list[str]:
    """Manifest scripts that invoke the runners these specs belong to.

    A project with `"test:e2e": "npx playwright test"` does run its Playwright
    specs, and saying otherwise would be the false positive this whole change
    exists to remove. What the pipeline gates on is a separate question, and
    `_tests_the_project_never_runs` already reports that for the languages
    `node --test` cannot parse.
    """
    # Mapped explicitly, not derived from the package name. `@playwright/test`
    # ends in "test", and taking the last path segment made that the word
    # searched for - which matches `node --test`, so a manifest whose only
    # script was `node --test` was read as running its Playwright specs and the
    # genuine finding was swallowed.
    wanted = {_RUNNER_COMMANDS.get(owner, owner).lower() for owner in owned.values()}
    return sorted(
        name
        for name, body in scripts.items()
        if any(runner in str(body).lower() for runner in wanted)
    )


def _tests_the_project_never_runs(files: list[Path], root: Path) -> list[str]:
    """Test files the project's own `npm test` will not execute.

    Decided by the manifest, not by a convention: `scripts.test` says what runs,
    and everything `classify_file` calls a test and that command does not reach
    has never executed once.

    One run reached its third milestone round with seven test files -
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
    those files are called. One run reached its sixth milestone with
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
        # A named file that imports the suites runs them. One run's
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
        # A spec another runner owns is not stranded by `scripts.test`; it is
        # simply not that runner's file. Reported separately below, because the
        # remedy this check would otherwise give - "name them too" - throws.
        owned_elsewhere = {
            path: owner
            for path in tests
            if not _node_runs(path, project, searched, listed_files)
            and path.resolve() not in imported
            and (owner := _belongs_to_another_runner(path))
        }
        stranded = [
            path
            for path in tests
            if not _node_runs(path, project, searched, listed_files)
            and path.resolve() not in imported
            and path not in owned_elsewhere
        ]
        if owned_elsewhere and not other_scripts_that_run_them(scripts, owned_elsewhere):
            names = ", ".join(
                sorted(str(p.relative_to(root)) for p in owned_elsewhere)
            )
            runners = ", ".join(sorted(set(owned_elsewhere.values())))
            problems.append(
                f"{manifest.relative_to(root)} has no script that runs {names} - "
                f"they are {runners} specs, and nothing in this manifest invokes "
                f"{runners}. `scripts.test` cannot be made to run them: "
                "`node --test` throws on another runner's spec rather than "
                "failing. Add a script that calls the right runner."
            )
        # A suite in a language `scripts.test` cannot run at all, reachable
        # only through another script. `node --test` will not parse
        # TypeScript, so a `.ts` suite is never stranded by accident - it is
        # stranded by design, and the design is the problem.
        #
        # Measured on one run, which COMPLETED: `scripts.test` is
        # `node --test tests/` and collected 34 passing tests, while
        # `tests/app.test.ts` held five Playwright tests reachable only
        # through `scripts["test:e2e"]`. No stage in this pipeline runs
        # anything but `scripts.test`, so those five never ran at a gate, and
        # every review read "# pass 34  # fail 0" as evidence the UI works.
        # Run directly afterwards, all five failed.
        other_scripts = sorted(
            name for name, body in scripts.items()
            if name != "test" and _looks_like_a_test_command(str(body))
        )
        unrunnable = [
            path
            for path in files
            if path.suffix.lower() in {".ts", ".tsx", ".jsx"}
            and is_test(str(path.relative_to(root)))
            and _is_within(path, project)
        ]
        if unrunnable:
            names = ", ".join(sorted(str(p.relative_to(root)) for p in unrunnable))
            through = (
                f" They are reachable through `npm run {other_scripts[0]}`, and no "
                "stage in this pipeline runs anything but `test`."
                if other_scripts
                else " Nothing in the project runs them at all."
            )
            problems.append(
                f"{manifest.relative_to(root)} runs `{command}`, which cannot run "
                f"{names} - `node --test` does not parse TypeScript or JSX."
                + through
                + " A suite no gate executes is not evidence: make `test` run "
                "both, so one command proves the whole product."
            )
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
        # Scratch scripts are reported by `_scratch_scripts_left_behind`, which
        # tells the stage to delete them. Listing them here under "name them
        # too" is the opposite instruction for the same file.
        where = ", ".join(
            sorted(
                str(path.relative_to(project))
                for path in stranded
                if not _A_SCRATCH_SCRIPT.search(path.name)
            )
        )
        if not where:
            continue
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

    An aggregator is a normal and correct way to run a suite: one run's
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
    """Path arguments the `node --test` command names, ignoring its flags.

    Split the way a shell would, not on whitespace. A manifest may quote its
    arguments - and one that does was, until this used `shlex`, reported as
    running no files at all.

    Measured live on 2026-09-21. `task-manager/package.json` held::

        "test": "node --test \\"app.test.mjs\\" \\"line-budget.test.mjs\\""

    so `command.split()` produced `'"app.test.mjs"'` with the quote characters
    still attached. `_node_runs` then compared that against the real relative
    path `app.test.mjs`, found no match, and declared both suites stranded -
    while the very same message listed them as the files the command names. The
    finding read:

        runs `node --test "app.test.mjs" "line-budget.test.mjs"`, which names
        "app.test.mjs", "line-budget.test.mjs". ... Stranded: app.test.mjs,
        e2e/task-manager.spec.js, line-budget.test.mjs.

    Named and stranded at once, and marked BLOCKING - "1 of these means a
    feature DOES NOT WORK". A false blocking finding is worse than a missed one
    here: it sends a defect-fix stage to repair something that is not broken,
    and it teaches a reviewer that the check cannot be trusted.

    `shlex.split` also drops the shell escaping npm writes into a manifest, so
    `\\"app.test.mjs\\"` and `'app.test.mjs'` and bare `app.test.mjs` all resolve
    to the same path, which is what the check has always meant to compare.
    """
    import shlex

    try:
        words = shlex.split(command)
    except ValueError:
        # An unbalanced quote is a broken manifest, reported elsewhere. Fall
        # back rather than lose the whole check.
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

    Found by one run's milestone reviewer, which read both files and
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


#: Comments alone, leaving string literals where they are.
_A_COMMENT = re.compile(r"""//[^\n]*|/\*.*?\*/""", re.S)


def _without_comments(text: str) -> str:
    """`text` with comments blanked and every string literal left intact.

    `_only_the_code` is wrong for anything that reads the literals themselves.
    `innerHTML = ""` is a clearing and `innerHTML = `<li>${t}</li>`` is markup,
    and blanking both to `innerHTML = ;` loses exactly the difference the
    caller is asking about.
    """
    return _A_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


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

    The mirror of `_modules_loaded_as_plain_scripts`, and one run built
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

    Measured on one run, whose manifest said

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
                    for other in files_under(project, _SKIP, Path(candidate).name)
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

    The runs keep shipping a suite thinner than the product. One run's
    `npm test` reported `# tests 1` for an application exporting five
    functions; one run reported three; one run had seven test files
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
            "about those." + _but_a_browser_test_may_reach_them(tests, root)
        )
    return problems


#: A runtime being handed a file to execute: `node server.mjs`,
#: `python -u app.py`, `deno run --allow-net main.ts`, `bun start.ts`,
#: `dotnet Program.dll`. The command may be in a config, a manifest, a CI
#: workflow, a Dockerfile, a Makefile or a README - all of them are callers.
_A_RUNTIME_LAUNCHES = re.compile(
    r"\b(?:node|nodemon|deno\s+run|bun|tsx|ts-node|python3?|ruby|php|perl|dotnet|java)\b"
    # Separators cover the shell form (`node -u app.py`) and the exec form a
    # Dockerfile or a CI matrix writes (`["python", "-u", "app.py"]`).
    r"(?:[\s'\",]{1,4}|-{1,2}[A-Za-z][\w-]*){1,8}"
    r"([^\s'\"`;&|()\[\],]+\.[A-Za-z][\w]*)"
)


def _files_a_command_launches(text: str) -> set[str]:
    """Base names a command string in `text` hands to a runtime to execute.

    `_orphaned_scripts` knows two kinds of caller: a `<script>` tag and an
    `import`. A third kind is as real as either and was invisible to it - a
    command that runs the file, wherever that command is written down.

    Measured on one run, whose `TESTABILITY_RULE` told the model to "let
    Playwright manage the server itself - declare a `webServer` in
    `playwright.config.ts`". The model did exactly that, with
    `command: 'node server.mjs'`, and the orphan check then reported
    `server.mjs` as a blocking finding: "never loaded by a page or imported by
    another module. Nothing runs it." Playwright ran it on every test.

    Deliberately not a Playwright rule. A CI workflow, a Dockerfile `CMD`, a
    Procfile, a Makefile recipe, a compose `command:` and a README's "run it
    with" line all say the same thing in the same shape, in every language the
    regex names, and none of them were counted either.
    """
    return {Path(target).name for target in _A_RUNTIME_LAUNCHES.findall(text)}


#: Files whose whole job is to say how the product is run. None of them are
#: source in any language, so `_source_files` does not collect them - and the
#: one question they answer is exactly the one the orphan check asks.
_A_RUN_DESCRIPTION = re.compile(
    r"^(?:Dockerfile|Containerfile|Procfile|Makefile|Justfile|Taskfile\.ya?ml"
    r"|(?:docker-)?compose(?:\.\w+)?\.ya?ml|\w[\w.-]*\.ya?ml|README(?:\.\w+)?"
    r"|\w[\w.-]*\.(?:sh|bat|ps1|cmd))$",
    re.I,
)


def _how_the_product_is_run(root: Path) -> str:
    """Every run description in the project, concatenated. Never raises.

    A Dockerfile `CMD`, a Procfile line, a Makefile recipe, a compose
    `command:`, a CI workflow step, a shell script and a README's "run it
    with" all name the file that gets executed, and none of them are source in
    any language, so nothing collected them.

    Walks once, pruning the same directories every other check prunes, so a
    `node_modules` with forty thousand files costs nothing here.
    """
    import os

    texts: list[str] = []
    try:
        for parent, directories, names in os.walk(root):
            directories[:] = [d for d in directories if d not in _SKIP]
            for name in names:
                if _A_RUN_DESCRIPTION.match(name):
                    texts.append(_read(Path(parent) / name))
    except OSError:
        return ""
    return "\n".join(texts)


#: A suite that drives the product through a page rather than importing it.
#: Its tests name buttons and selectors, never the functions behind them.
_A_BROWSER_SPEC = re.compile(
    r"@playwright/test|from\s+['\"]playwright|cy\.(?:visit|get)\s*\(|"
    r"browser\.url\s*\(|page\.(?:goto|locator|click)\s*\("
)


def _but_a_browser_test_may_reach_them(tests: list[Path], root: Path) -> str:
    """The caveat this finding's own docstring holds and its message did not.

    "A passing suite says nothing about those" is true of a suite that imports
    the module and false of one that drives the page. A browser spec names
    `.edit-btn` and `page.locator`, never `editTask`, so every export a page
    reaches is missing from it by construction.

    Measured on one run, which shipped `editTask` and a Playwright test
    `test('edits a task title')` that clicks the edit button, asserts the
    input appears and checks the new title. The finding said no test mentions
    `editTask` - correct - and that a passing suite says nothing about it,
    which was wrong, and it said it to a reviewer whose job is to act on it.

    The other machine's §3.3 records the cost of this shape in one sentence:
    a check two consecutive reviewers have to overrule is the check's problem.
    So the message now says what it knows and what it does not, and lets the
    reviewer look. Deliberately no inference from a selector to a function:
    that guess would be wrong often enough to be worse than the caveat.
    """
    if not any(_A_BROWSER_SPEC.search(_read(path)) for path in tests):
        return ""
    return (
        " A browser test is present in this suite, and a browser test drives "
        "the page rather than importing the module - it names buttons and "
        "selectors, never the functions behind them. So a name missing here "
        "may still be covered end to end. Check whether a browser test "
        "exercises it before treating this as a gap."
    )


def _orphaned_scripts(files: list[Path], root: Path) -> list[str]:
    """Application scripts that nothing loads or imports, as relative paths."""
    referenced: set[str] = set()
    referenced.update(_files_a_command_launches(_how_the_product_is_run(root)))
    for path in files:
        text = _read(path)
        referenced.update(_files_a_command_launches(text))
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

    One run's milestone review found it by reading, which is luck rather
    than design: `index.html` carried no `<script>` tag of any kind, `app.js`
    was imported only by `app.test.mjs`, and the deterministic checks reported
    one untidy problem and nothing else. The suite was 5 of 5 green over a
    product that never loaded.

    One run is the same failure surviving to the end of a run, and this is
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
    """The orphan finding, phrased for a reviewer.

    Scratch scripts are left out. "Nothing runs it" is the definition of a
    throwaway an agent wrote to print something once, so reporting it says
    nothing a reviewer can act on, and
    `_scratch_scripts_left_behind` already names those files with the
    instruction that fits them.

    Measured on one run, whose report ran to 14 findings of which 10 were
    about its own temp files - four real problems buried in a list three times
    their length.
    """
    return [
        f"{relative} is never loaded by a page or imported by another "
        "module. Nothing runs it."
        for relative in _orphaned_scripts(files, root)
        if not _A_SCRATCH_SCRIPT.search(Path(relative).name)
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

    Measured on one run, whose stack was Python/FastAPI/pytest: its
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

    Measured on one run, whose specification described pure functions, a
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
    one run the suite read `'./todo-app/index.html'`, and the test round
    ran it as `node --test todo-app/app.test.mjs` from the workspace root,
    where that path resolves. It passed eight times. From inside the project
    directory - `cd todo-app && node --test app.test.mjs`, which is how anyone
    who is handed the project runs it - every test fails with ENOENT.

    So the workflow cannot find this by running the tests: they pass. It is
    only visible by reading how the path is built.

    One run hit the same thing with `path.resolve('./script.js')`, where
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


#: A browser-driver helper: its first parameter is Playwright's or Puppeteer's
#: page handle, or its body works the page rather than the data.
_DRIVES_A_BROWSER = re.compile(
    r"""\(\s*(?:page|browser|context)\b|:\s*Page\b|"""
    r"""\bpage\s*\.\s*(?:goto|locator|getBy\w+|click|fill|waitFor)""",
    re.I,
)


def _a_browser_helper_of_the_same_name(text: str, name: str) -> bool:
    """Whether `name` here drives a browser rather than copying the application.

    An end-to-end helper called `addTask(page, title)` types into a form and
    clicks a button. It shares a name with the application's
    `addTask(title, description)` and nothing else: different parameters,
    different job, and importing the application's version in its place would
    defeat the test.

    One run's `tests/fixtures.ts` was reported for exactly that, and one
    run's milestone reviewer had already rebutted the same finding in its
    own words - "importing the JS module would defeat the purpose of end-to-end
    verification and is not required or expected". Two reviewers pushing back on
    a blocking finding is the signal that the finding is wrong, and a specialist
    sent to fix working code is what cost one run its life.
    """
    found = re.search(
        rf"(?:function\s+{re.escape(name)}|{re.escape(name)}\s*[:=]\s*(?:async\s*)?\()",
        text,
    )
    if not found:
        return False
    window = text[found.start() : found.start() + 400]
    return bool(_DRIVES_A_BROWSER.search(window))


def _redefined_instead_of_imported(files: list[Path], root: Path) -> list[str]:
    """Test files that define the application's own functions rather than import them.

    A test that reimplements what it is testing passes whatever the application
    does. It is the same defect as `expect(1 + 1).toBe(2)` wearing a much better
    disguise: the assertions are real, the logic is real, and none of it is
    connected to the product.

    Measured on one run. `app.js` calls `init()` at module scope, so
    importing it in Node runs DOM code and throws. The testing specialist said
    so in its own header - "it cannot be directly imported in a headless Node
    environment. Instead, this test file defines the same pure logic functions
    inline" - and six tests passed against a copy. Nothing in the workflow
    noticed, because six tests did pass.

    Fires per NAME, not per file. One run shipped the same defect wearing
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
            name
            for name in defined
            if name in application
            and name not in imported
            and not _a_browser_helper_of_the_same_name(text, name)
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
            # A leading slash is root-relative to whatever serves the page, and
            # `Path("proj") / "/src/main.jsx"` is `/src/main.jsx` - pathlib
            # discards the left side, so every such reference resolved to a
            # path outside the workspace and was reported as missing. That is
            # Vite's own convention for an entry point, so a React or Vue
            # product tripped this on its first file. The two sibling checks
            # above already strip it; this one did not.
            referenced = path.parent / target.lstrip("/")
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
            # Measured on one run: index.html linked `style.css` on line
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

    One run is what this is for. `specialist_testing_1` added
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
            if _A_SCRATCH_SCRIPT.search(path.name):
                # A scratch script's remedy is deletion, not conversion; see
                # `_scratch_scripts_left_behind`, which names it with that.
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
_PROVIDES_TEST_GLOBALS = (
    "jest", "vitest", "mocha", "jasmine", "karma", "cypress",
    # Playwright does not inject globals - it exports them - but a project
    # that depends on it is one whose `.spec` files import from
    # `@playwright/test`, and this check has no business judging them. It
    # blocked one run's `app.spec.js`, which opens
    # `import { test, expect } from '@playwright/test';` and passes 24 of 24.
    "playwright",
)

#: `test(`, `it(` or `describe(` called at the file's own top level.
_CALLS_A_SUITE_GLOBAL = re.compile(
    r"""^(?:await\s+)?(test|it|describe)\s*(?:\.\w+\s*)?\(""", re.M
)

#: The binding brought in from `node:test`, however it is spelled.
_IMPORTS_FROM_NODE_TEST = re.compile(
    r"""from\s+['"]node:test['"]|require\(\s*['"]node:test['"]\s*\)"""
    r"""|from\s+['"]test['"]""",
)


def _imports_the_name(content: str, name: str) -> bool:
    """Whether this file binds `name` by importing it from anywhere.

    The question is whether `test` is defined when the file runs, and the
    module it came from is beside the point. Matching only `node:test` made
    this check blind to every other runner that exports rather than injects.

    Measured live on one run: `app.spec.js` opens
    `import { test, expect } from '@playwright/test';` and passes 24 of 24
    under `npx playwright test`. The check called it a file where "every case
    throws ReferenceError" and, being blocking, held the sprint - and its
    remedy, "add `import { test } from 'node:test'`", would have broken the
    working suite.

    A false positive on a blocking check whose fix makes things worse is the
    most expensive shape a check can have.
    """
    escaped = re.escape(name)
    return bool(
        # import { test } from '...'   /  import { test as t } from '...'
        re.search(rf"import\s*\{{[^}}]*(?<![\w$]){escaped}(?![\w$])[^}}]*\}}\s*from", content)
        # import test from '...'
        or re.search(rf"import\s+(?<![\w$]){escaped}(?![\w$])\s*(?:,|from)", content)
        # const { test } = require('...')  /  = await import('...')
        or re.search(
            rf"(?:const|let|var)\s*\{{[^}}]*(?<![\w$]){escaped}(?![\w$])[^}}]*\}}\s*=", content
        )
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
    tangle when they hit it, and it cost each of them a round of its own. One
    run's `test_round_0` got `ReferenceError: describe is not defined` and
    "fixed" it by moving every case inside a default export, which
    `tests_the_runner_will_never_call` now catches. One run's
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
        # Imported from anywhere at all, not only `node:test`. See
        # `_imports_the_name`: the question is whether the name is bound when
        # the file runs, and which module bound it does not change the answer.
        if _imports_the_name(content, name):
            continue
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
    it. One run's milestone reviewer inferred it wrongly - it recorded a
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
            for path in files_under(base, _SKIP)
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
        # Comments blanked, string literals kept. A commented-out `innerHTML`
        # read as markup withholds the one sentence this exists to provide -
        # that an injection finding would be incorrect - which is what one
        # run was killed for the want of. But the literals have to stay:
        # `innerHTML = ""` is a clearing and ``innerHTML = `<li>${t}</li>` `` is
        # markup, and blanking both loses that distinction entirely.
        code = _without_comments(_read(path))
        name = str(path.relative_to(base))
        if _MARKUP_INTO_THE_PAGE.search(code):
            markup.append(name)
        elif _SAFE_TEXT_INTO_THE_PAGE.search(code):
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


#: Names an agent gives a throwaway script while it is debugging. Narrow on
#: purpose: a product file is not called `tmp_debug5`.
_A_SCRATCH_SCRIPT = re.compile(
    r"""^(?:tmp|temp|scratch|debug)[_.-]|^test[_-]debug|[_-]debug\d*\.[cm]?js$"""
    # `test2.mjs`, `test4.mjs` - a numbered throwaway, which one run left
    # two of. Anchored and digit-suffixed so `app.test.js` and `test.mjs` are
    # untouched: a bare `test.mjs` is a plausible entry point, `test2` is not.
    r"""|^test\d+\.[cm]?js$""",
    re.I,
)


def _scratch_scripts_left_behind(files: list[Path], root: Path) -> list[str]:
    """Throwaway debugging scripts still sitting in the product.

    A stage that cannot see why a test fails writes a small script, runs it,
    and learns something. That is good practice and this does not discourage
    it - what it reports is the ones never cleaned up.

    One run's `defect_fix_2_1` left twelve: `tmp_debug2.mjs` through
    `tmp_debug6.mjs`, `tmp_full_test.mjs`, `tmp_run_test.mjs`,
    `tmp_print_tnew.mjs` and more, beside an application of three files. Across
    the stored workspaces five of fifty-five carry them.

    They are not harmless. Four of that run's twelve end in `_test.mjs`, which
    is one of the patterns `node --test` collects, so they became part of the
    suite the gates read. And the stranded-tests finding listed them alongside
    real test files under "name them too", which is the wrong instruction for a
    file whose place is the bin.
    """
    scratch = [
        str(path.relative_to(root))
        for path in files
        if path.suffix.lower() in {".js", ".mjs", ".cjs"}
        and not any(part in _SKIP for part in path.parts)
        # A file under `tools/` or `scripts/` was put there deliberately. Run
        # cbd22a3's `tools/debug-linecount.mjs` counts the product's lines
        # against the brief's 500-line cap - a utility the project meant to
        # keep, not a throwaway someone forgot.
        and not any(part in {"tools", "scripts", "bin"} for part in path.parts)
        and _A_SCRATCH_SCRIPT.search(path.name)
    ]
    if not scratch:
        return []
    listed = ", ".join(sorted(scratch)[:6])
    more = "" if len(scratch) <= 6 else f" and {len(scratch) - 6} more"
    return [
        f"{listed}{more} look like debugging scripts left behind. Writing one "
        "to find out why a test fails is the right move; leaving it in the "
        "product is not. They are counted against the size of what was built, "
        "a reviewer reads them as part of it, and any whose name matches a test "
        "pattern is collected into the suite. Delete the ones that have served "
        "their purpose."
    ]


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

    One run completed on this. Its final sprint - "Finalize code,
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

    This is one run's failure a layer down. That one shipped no HTML; this
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
    warning and working correctly. The original observation came from one
    run, where the note "we can't directly import app.js" was written by
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

    Measured on one run, whose selection was Python / FastAPI /
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
#: Suffixes the size report counts as the product.
#:
#: This was ten entries, all of them HTML, CSS, JavaScript or Python, so a Go,
#: Rust, Java, C#, Ruby, PHP, Kotlin, Swift or Dart product reported a size of
#: zero. A brief capping "lines of code" was therefore enforced for two
#: ecosystems and silently unenforced for the rest - B1, and root-cause class
#: H: a rule written for the stack that happened to be in front of it.
#:
#: Counting lines needs no per-language analyser. Every language has files,
#: lines, blanks and comments, and `_code_lines` already strips `//` and `#`
#: line comments and `/* */` and `<!-- -->` blocks, which between them cover
#: every language below. The languages that need more than that - a full
#: reference graph, an entry-point rule - are B1's remaining work; a size
#: count is not, and it is what the milestone budget check actually reads.
_COUNTED_SUFFIXES = frozenset({
    # Web.
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    # Python.
    ".py", ".pyi",
    # Compiled and JVM.
    ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".cs", ".swift",
    ".c", ".h", ".cpp", ".cc", ".hpp", ".m", ".mm",
    # Scripting.
    ".rb", ".php", ".pl", ".lua", ".dart", ".ex", ".exs", ".sh", ".bash",
    # Data and query languages that are part of a product rather than config.
    ".sql",
})
_NOT_COUNTED = re.compile(r"(^|/)(package-lock\.json|.*\.min\.(js|css))$")


_LINE_COMMENT = re.compile(r"^\s*(//|#)")
_BLOCK_COMMENT_EDGES = (("/*", "*/"), ("<!--", "-->"))


def _code_lines(text: str) -> int:
    """Lines that are neither blank nor comment.

    "Maximum 500 lines of code" does not mean 500 lines of file. Reporting only
    the raw count leaves the reviewer comparing a number against a limit that
    means something else, and on one run that ambiguity is why nothing
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
    brief and can compare, but only if someone counts." one run shows the
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
    specialist is re-delegated, and the code is rewritten. One run spent
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
        # Not on a test file. The number below is application code only - the
        # docstring's whole point - but a note is delivered to whoever is
        # writing *this* file, and a testing specialist told "you are 80 lines
        # over" while holding `app.test.mjs` has one obvious way to comply,
        # which is to cut the file in its hand. That is the reaction this
        # note's own comment warns about, arriving through the addressee
        # rather than through the total.
        #
        # 7 of its 27 firings across the stored runs landed on a test file.
        if is_test(relative_path):
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
        # one run where the reviewer would say 628, because one 797-line
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
        # the wrong thing. On one run the application was 631 lines and the
        # tests the round installed were 1,558 more.
        (tests if (not is_application(relative)) else application).append((lines, relative))
    return application, tests, stray, counted_code


def _size_report(files: list[Path], root: Path, orphans: set[str] | None = None) -> str:
    """How many lines of code this project is, per file and in total.

    Reported rather than judged. A brief that caps the product at a number of
    lines - `brief_low` says "Maximum 500 lines of code" - is a constraint no
    stage ever checked against what was built: one run shipped 627 lines,
    390 of them CSS, and passed every review. The reviewer has the brief and
    can compare, but only if someone counts.

    Scripts nothing loads are counted apart from the application. They are not
    the product - they are the probes and verifiers an agent left behind - and
    including them makes the one number the reviewer judges the brief against
    wrong in both directions: it can fail a product that is within its cap, and
    it can hide an overrun behind a total nobody trusts. On one run the
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

    # State the verdict, not two numbers and a hint about which to use.
    #
    # One run failed on this. Its milestone review blocked with
    # "Application source files total 631 lines across 3 files, exceeding the
    # brief's stated constraint of 'Maximum 500 lines of code'. The
    # deterministic size check confirms this violates the size budget." The
    # deterministic check said no such thing: 413 lines of code against a
    # declared 500, comfortably inside, which is why `budget_note_for_a_write`
    # stayed silent through every write of the run. 631 is the raw total,
    # blanks and comments included.
    #
    # The reviewer then required changes three times over, the rerun limit
    # fired, and the run ended - 199 model calls and five million tokens - on a
    # finding the harness's own measurement contradicts. The line above already
    # said which number to use and was read past anyway, so the number this
    # project is actually judged against is now stated with its verdict
    # attached and nothing left to pick between.
    budget = _declared_line_budget(root)
    if budget:
        if code_total > budget:
            report += (
                f"\n  Against the {budget:,}-line limit this project's own documents "
                f"state: OVER by {code_total - budget:,} lines. This is a stated "
                "acceptance criterion and a reviewer should block on it."
            )
        else:
            report += (
                f"\n  Against the {budget:,}-line limit this project's own documents "
                f"state: WITHIN budget, {budget - code_total:,} lines to spare. The "
                f"raw total of {app_total:,} is not the figure to judge - it counts "
                "blank lines and comments, which the limit does not."
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

    - one run shipped `"dependencies": {"jsdom": "^29.1.1"}` against a
      brief reading "No external dependencies beyond basic HTML/CSS/JS". The
      application itself loaded nothing - jsdom was only used by the tests - but
      the manifest declared it a runtime dependency of the product.
    - one run also kept npm's `"test": "echo \"Error: no test specified\"
      && exit 1"` placeholder, the same artefact that cost one run its
      entire sprint when `npm test` resolved to it.
    - one run's `"main": "index.js"` named a file that does not exist.
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
            # one run: 153 passing tests in `app.test.mjs`, a manifest with
            # no `scripts` at all, and `npm test` answering "missing script:
            # test". The placeholder case above has been covered since
            # one run; having no script is the same outcome with less to
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
            # one run's reviewer found it declared as a production
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

    # Nothing above runs when there is no manifest at all, and that is the
    # worse version of the same fault: `npm test` answers ENOENT rather than
    # "missing script", so not one suite in the project can be reached by the
    # command every stage is told to use. One run reached 699 events with
    # two suites on disk and no `package.json`; three runs ended that way.
    #
    # Reported here rather than at the write of a test file, because the write
    # order does not settle it: across the stored transcripts the manifest
    # comes first in 12 runs and second in 11, so a note at the write would be
    # premature about half the time. By the end of a sprint it is decidable.
    if not any(path.name == "package.json" for path in files):
        suites = sorted(
            str(path.relative_to(root))
            for path in files
            if is_test(str(path.relative_to(root)))
        )
        if suites:
            named = ", ".join(suites[:3])
            problems.append(
                f"This project has tests ({named}) and no `package.json` at "
                "all. `npm test` fails with ENOENT before reaching any of "
                "them, so nothing that runs the project's test command has "
                "ever executed a single assertion. Add a `package.json` whose "
                "`test` script runs them."
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
#: One run accepted its milestone with the note "The cross-file check
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
    # The same false green, reached the other way: a suite the gating command
    # cannot run at all. One run COMPLETED with five Playwright tests
    # that had never executed once, because `scripts.test` is `node --test`
    # and they are TypeScript; all five failed when run afterwards. Classified
    # untidy at first for want of a phrase in this tuple, which is the stale
    # -marker failure this file is most exposed to - see
    # `test_every_blocking_check_is_classified_as_blocking`.
    "does not parse TypeScript or JSX",
    # The third way to the same false green, and the one that reached a live
    # review as tidiness. One run shipped a three-file suite in which
    # `task-manager/ui.pw.test.mjs` is a Playwright spec and `scripts.test` is
    # `node --test`, which throws on another runner's spec rather than running
    # it. No gate in this pipeline ran that file once, and the finding whose
    # own words are "no script that runs" it was filed under "untidy rather
    # than broken - dead rules, unused files".
    #
    # That is the stale-marker failure the comment above predicts, caught in
    # production rather than by the test that exists to catch it - which
    # checks that every marker matches some message, and cannot check that
    # every breaking message matches some marker.
    "has no script that runs",
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
    "asserts only constants",            # a suite that can only ever pass
    "none of the cases execute",         # a suite the runner never calls
    # A page that throws on load. Both of these were graded untidy the day
    # they were written - the summary invited the milestone reviewer to wave
    # through a product whose every control was dead - which is the third
    # time this tuple has gone stale behind a new check.
    "A module script has no global fallback",  # a name the page never imported
    "is `undefined` every time the application",  # an argument only the tests pass
    # Its own message says "This BREAKS regression detection. You MUST",
    # and it was being filed under "worth a minor finding, not a blocking
    # one" - the summary contradicting the finding it was quoting. One
    # run is the evidence that the message had it right: that product
    # had no browser test, and its page threw `ReferenceError` on load.
    "This BREAKS regression detection",  # a UI with no end-to-end test
    # A capability the run's own acceptance criteria enumerate and the
    # product never built. "Untidy" is dead rules and unused files; a
    # requirement delivered as far as the documents and no further is the
    # product not doing what it was asked to do.
    "Either build it or record why it was dropped",  # a dropped criterion
    # The same criterion, descoped by a decision the run wrote itself.
    "the deferral carries no authority",  # a self-authorised descope
    # A requirement no test covers. The suite is green because it was
    # written from the code, which cannot miss what the code does not do.
    "the only thing here that remembers",  # a requirement nothing tests
    "and nothing on it works",           # CommonJS behind a module script tag
    "so the suite cannot run",           # files against a declared module type
)


#: Findings that break nothing and are not untidiness either: the product
#: works, and it does not meet a criterion the project was given.
#:
#: The two-bucket summary had no home for these, so they were filed under
#: "untidy rather than broken - dead rules, unused files. Worth a minor
#: finding, not a blocking one" - in the same report whose size section says,
#: of the same number, "This is a stated acceptance criterion and a reviewer
#: should block on it". A reviewer reads both and is left to guess which the
#: harness means.
#:
#: Seen on one run (538 lines against 500) and one run (580 against
#: 500). Not folded into `_BREAKS_BEHAVIOUR`, because that bucket's own
#: heading says "a feature DOES NOT WORK ... the code path is simply never
#: reached", and a product eighty lines over its budget works perfectly well.
#: Grading it there would make the heading false, which is the mistake
#: `test_a_ui_with_no_browser_test_blocks` exists to prevent.
_MISSES_A_STATED_CRITERION = (
    "maximum this project's own documents state",
)


def _severity_of(problem: str) -> str:
    if any(mark in problem for mark in _BREAKS_BEHAVIOUR):
        return "BREAKS"
    if any(mark in problem for mark in _MISSES_A_STATED_CRITERION):
        return "CRITERION"
    return "untidy"


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


#: Config files belonging to a browser test runner. A file one of these
#: launches is the harness, not the product.
_A_TEST_RUNNER_CONFIG = re.compile(
    r"^(?:playwright|cypress|wdio|karma|nightwatch|testcafe|vitest|jest"
    r"|web-test-runner|protractor|codecept)[.\w-]*\.(?:c|m)?(?:j|t)s(?:on)?$",
    re.I,
)


def _servers_started_by_a_test_runner(files: list[Path], root: Path) -> set[Path]:
    """Files a test runner's own config starts, resolved against the project.

    `TESTABILITY_RULE` tells the model, in these words, to "let Playwright
    manage the server itself - declare a `webServer` in
    `playwright.config.ts`". One run's model did exactly that, with
    `command: 'node server.mjs'`, and two checks then reported `server.mjs` as
    blocking: one because the stack stores data in the browser and therefore
    "has no server", the other because no page loads it. The harness asked for
    the file and then refused the sprint for containing it.

    A server the test runner starts is test infrastructure. It ships to
    nobody, holds no product data and disappears when the suite ends, so
    neither "this product has no backend" nor "no page imports this" is a
    fault of it.

    Not a Playwright rule: Cypress, WebdriverIO, Karma, Nightwatch, TestCafe
    and Web Test Runner all declare a server the same way, and every one of
    them would have been reported the same.

    Never raises. An exemption that throws turns a false finding into a lost
    check.
    """
    started: set[Path] = set()
    by_name: dict[str, list[Path]] = {}
    for path in files:
        by_name.setdefault(path.name, []).append(path)
    try:
        for path in files:
            if not _A_TEST_RUNNER_CONFIG.match(path.name):
                continue
            for name in _files_a_command_launches(_read(path)):
                started.update(candidate.resolve() for candidate in by_name.get(name, ()))
    except Exception:  # noqa: BLE001 - an exemption must never fail a check
        return set()
    return started


def _a_server_in_a_browser_only_product(files: list[Path], root: Path, stack: Any) -> list[str]:
    """A server in a product whose own stack says there is none.

    One run chose "Vanilla JavaScript" with "Web LocalStorage", and wrote
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

    # A server the test runner starts is the one `TESTABILITY_RULE` asks for,
    # not a product server. See `_servers_started_by_a_test_runner`.
    exempt = _servers_started_by_a_test_runner(files, root)

    problems: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts"}:
            continue
        if is_test(str(path.relative_to(root))):
            continue
        if path.resolve() in exempt:
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

    Measured on one run. `stack_selector` chose
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
        a_suite_that_asserts_only_constants,
        a_suite_that_only_checks_things_exist,
        a_test_that_asserts_nothing,
        assertions_called_on_the_test_module,
        tests_the_runner_will_never_call,
    )

    problems: list[str] = []
    for path in files:
        relative = str(path.relative_to(root))
        # Only test files. These four ask whether a suite can fail, which is
        # not a question about application code - and one run's `app.js`
        # was reported as a suite of existence checks because its ordinary
        # `typeof window !== 'undefined'` guards were read as assertions.
        if not is_test(relative):
            continue
        content = _read(path)
        for problem in (
            assertions_called_on_the_test_module(relative, content),
            a_test_that_asserts_nothing(relative, content),
            tests_the_runner_will_never_call(relative, content),
            a_suite_that_only_checks_things_exist(relative, content),
            a_suite_that_asserts_only_constants(relative, content),
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
#: A width-based media query. `prefers-color-scheme` and `print` are not about
#: viewport width and do not depend on the meta tag.
_WIDTH_MEDIA_QUERY = re.compile(r"@media[^{]*\(\s*(?:min|max)-width", re.I)

_VIEWPORT_META = re.compile(
    r"""<meta\b[^>]*\bname\s*=\s*["']viewport["']""", re.I
)


#: Any technique that makes a layout answer to the width it is given. A
#: breakpoint is the obvious one and it is not the only one: one run's
#: stylesheet has no `@media` at all and is legitimately fluid, built out of
#: `clamp()`, `min()` and viewport units, which is why this check asks whether
#: the product does anything responsive rather than whether it has breakpoints.
_RESPONSIVE_TECHNIQUE = re.compile(
    r"@media[^{]*\(\s*(?:min|max)-(?:width|inline-size)"   # a breakpoint
    r"|@container"                                          # container queries
    r"|\bclamp\s*\("                                       # fluid type and space
    r"|\b(?:min|max)\s*\([^)]*\b\d+(?:vw|vh|vmin|vmax|%)"  # fluid bounds
    r"|\b\d+(?:\.\d+)?(?:vw|vh|vmin|vmax)\b"               # viewport units
    r"|\bminmax\s*\("                                      # responsive grid
    r"|auto-fit|auto-fill"
    r"|flex-wrap\s*:\s*wrap",
    re.I,
)

#: The word a brief uses when it wants this. Looked for in the project's own
#: documents and in the brief, because either may be where it is stated.
_ASKS_FOR_RESPONSIVE = re.compile(r"responsive|mobile\s+and\s+desktop", re.I)


def _a_responsive_criterion_nothing_implements(
    files: list[Path], root: Path, brief: str = ""
) -> list[str]:
    """A product asked to be responsive whose styles never mention a width.

    Nothing verified this. `_responsive_css_the_page_cannot_use` asks whether
    an existing `@media` block can apply, and says nothing about a product
    that has no responsive handling at all - so "Responsive design for mobile
    and desktop", one of four acceptance criteria in the brief these runs are
    given, was the one criterion with no check behind it in either direction.

    Deliberately broad about what counts. Breakpoints are the obvious
    technique and not the only one: one run's stylesheet has no `@media`
    in it and is fluid throughout - `font-size: clamp(0.875rem, 2vw, 1rem)`,
    `max-width: min(48rem, calc(100% - 2 * var(--container-padding)))` - and a
    check that demanded `@media` would have filed a blocking finding against
    the best product this harness has produced. That is the failure mode to
    avoid here, so anything that answers to the width of the window counts.

    The viewport tag is required with it, for the reason its neighbour
    documents: without one a phone renders into a virtual 980px window and
    scales the result down, and every technique above answers to the wrong
    number.

    Fires on none of the eight stored workspaces. That is the point - it is a
    guard for a criterion nothing was checking, not a finding waiting to
    happen.
    """
    if not _ASKS_FOR_RESPONSIVE.search(brief or "") and not any(
        _ASKS_FOR_RESPONSIVE.search(_read(document))
        for folder in (root / "docs", root)
        if folder.is_dir()
        for document in sorted(folder.glob("*.md"))
    ):
        return []

    pages = [f for f in files if f.suffix.lower() in {".html", ".htm"}]
    if not pages:
        return []

    styles = [_read(f) for f in files if f.suffix.lower() == ".css"]
    for page in pages:
        styles.extend(_INLINE_STYLE.findall(_read(page)))
    if not styles:
        # No stylesheet at all is a different finding, and the size report
        # already says the product is a page and a script.
        return []
    if any(_RESPONSIVE_TECHNIQUE.search(sheet) for sheet in styles):
        return []

    named = ", ".join(
        sorted(str(f.relative_to(root)) for f in files if f.suffix.lower() == ".css")
    ) or "the page's own <style> block"
    missing_meta = [p for p in pages if not _VIEWPORT_META.search(_read(p))]
    viewport = (
        f" {missing_meta[0].relative_to(root)} also declares no "
        "`<meta name=\"viewport\">`, without which a phone renders into a "
        "virtual 980px window and scales the result down, so a layout that "
        "did answer to the width would still answer to the wrong one."
        if missing_meta
        else ""
    )
    return [
        f"This project is required to be responsive and {named} contains "
        "nothing that answers to the width of the window - no media query, no "
        "container query, no `clamp()`, no viewport units, no `minmax()` and "
        f"no wrapping flex row.{viewport} The page will render at one size and "
        "be scrolled sideways on a phone. Nothing here fails and no test "
        "catches it: a layout is only wrong on a screen nobody in this "
        "pipeline looks at."
    ]


#: The body of a `<style>` block, so a page that carries its own CSS is read
#: the same way as one that links a stylesheet.
_INLINE_STYLE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.I | re.S)


def _responsive_css_the_page_cannot_use(files: list[Path], root: Path) -> list[str]:
    """Width media queries on a page with no viewport meta tag.

    A mobile browser renders a page with no `<meta name="viewport">` into a
    virtual window about 980 CSS pixels wide and then scales the picture down.
    Every `max-width` query written for a phone therefore evaluates against 980,
    never fires, and the responsive stylesheet is dead code. Nothing throws and
    nothing fails: the page just looks like a shrunken desktop.

    Found on the completed run of 2026-09-21, against a brief whose acceptance
    criteria included "Responsive design for mobile and desktop".
    `specialist_ui_ux_0` wrote the tag correctly. `specialist_ui_ux_1` then ran::

        replace_lines(relative_path="task-manager/index.html",
                      start_line=5, end_line=5,
                      content='  <meta http-equiv="Content-Security-Policy" ...>')

    with no `expect_start`. Line 5 was the viewport tag, so the CSP tag replaced
    it instead of joining it. The stylesheet kept three width queries, two of
    them below 360px, which from then on could never match.

    It shipped. Forty-seven Playwright end-to-end tests passed, because
    Playwright's default viewport is desktop-sized; a security review passed;
    five milestone reviews passed. This is the shape every check in this module
    exists for - a real relationship between two files that no suite exercises -
    and it is the one relationship none of them covered.
    """
    pages = [f for f in files if f.suffix.lower() in {".html", ".htm"}]
    sheets = [f for f in files if f.suffix.lower() == ".css"]
    if not pages or not sheets:
        return []

    responsive = [
        sheet for sheet in sheets if _WIDTH_MEDIA_QUERY.search(_read(sheet))
    ]
    if not responsive:
        return []

    problems: list[str] = []
    for page in pages:
        text = _read(page)
        if not text.strip() or _VIEWPORT_META.search(text):
            continue
        # Only a page that actually loads one of the responsive stylesheets.
        loads = [
            sheet for sheet in responsive
            if sheet.name in text or sheet.relative_to(root).as_posix() in text
        ]
        if not loads:
            continue
        queries = sum(len(_WIDTH_MEDIA_QUERY.findall(_read(sheet))) for sheet in loads)
        named = ", ".join(sorted(str(sheet.relative_to(root)) for sheet in loads))
        problems.append(
            f"{page.relative_to(root)} has no `<meta name=\"viewport\">`, and "
            f"{named} contains {queries} width-based media "
            f"{'query' if queries == 1 else 'queries'} that therefore never "
            "match on a phone. Without the tag a mobile browser lays the page "
            "out at about 980px and scales it down, so every `max-width` rule "
            "written for a small screen is dead. Nothing fails - a desktop-sized "
            "end-to-end run cannot see this. Add "
            "`<meta name=\"viewport\" content=\"width=device-width, "
            "initial-scale=1.0\">` to the page head."
        )
    return problems


#: A call of a bare identifier - `name(`, not `obj.name(`. Matched against text
#: whose comments and string literals have been blanked by `_only_the_code`.
_BARE_CALL = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")

#: Keywords that take a parenthesis without being a call.
_NOT_A_CALL = frozenset({
    "if", "for", "while", "switch", "catch", "return", "typeof", "new",
    "function", "await", "delete", "void", "do", "else", "in", "of",
    "instanceof", "yield", "import", "super", "this", "case", "throw", "with",
})

#: Names the script itself introduces: declarations, classes and parameters of
#: its own functions. Anything here is bound when the script runs.
_DECLARED_LOCALLY = re.compile(
    r"""(?:^|[;{}\n])\s*(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"""
    r"""|(?:^|[;{}\n])\s*class\s+([A-Za-z_$][\w$]*)"""
    r"""|(?:^|[;{}\n(,])\s*(?:const|let|var)\s+([A-Za-z_$][\w$]*)""",
    re.M,
)


def _called_without_being_imported(files: list[Path], root: Path) -> list[str]:
    """A page calls a name its own module exports and its import clause omits.

    An inline `<script type="module">` is a module: an identifier it neither
    imports nor declares is not a global lookup that might work, it is a
    `ReferenceError` on the line that reaches it. When that line runs at
    `DOMContentLoaded`, the page is dead before the user touches anything.

    Found on one run of 2026-09-20, against `tests/brief_low.md`. The page
    imported six names::

        import { addTask, toggleTask, deleteTask, setFilter,
                 getFilteredTasks, setRenderCallback } from './app-logic.mjs';

    and then called five different ones - `addTaskAndPersist`,
    `toggleTaskAndPersist`, `deleteTaskAndPersist`, `loadPersistedTasks` and
    `getFilteredTasksFromState` - every one of them exported by the very module
    already being imported, none of them in the clause. Four of the six names it
    did import were never used. `init()` calls `loadPersistedTasks()` on
    `DOMContentLoaded`, so the application threw on load and no button in it
    ever worked.

    The suite could not see it: it reaches `app-logic.mjs` directly through
    `import * as appLogic`, so every pure function passed, and that run wrote no
    browser test at all. The page is the only place the wiring exists.

    Both reviewers did catch this one, and said so precisely - the security
    review graded it `critical` and named the failing path `init() ->
    loadPersistedTasks()`; the milestone review graded it `Blocking`, listed all
    five names and wrote out the corrected import clause. So this check is not
    here because the reviewers are blind to it. It is here because it is
    deterministic and free, it fires when the file is written rather than at the
    end of a sprint, and a reviewer is a model: one run's missing viewport
    tag passed a security review and five milestone reviews. A check that always
    fires is worth having behind a reviewer that usually does.

    Deliberately narrow: only a name the imported module *exports* is reported.
    A bare call to something else may be a browser global, so the certain case
    is the one where the fix is already on disk and only the clause is wrong.
    """
    problems: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        text = _read(path)
        for script in _INLINE_SCRIPT.finditer(text):
            body = script.group(1)
            # Two strippings, deliberately. `_only_the_code` blanks string
            # literals, which is right for finding calls and fatal for finding
            # imports - the module path *is* a string literal, and reading the
            # targets off the blanked text found none at all.
            code = _only_the_code(body)
            declarations = _without_comments(body)
            targets = [
                t for t in _IMPORT_TARGET.findall(declarations) if t.startswith(".")
            ]
            if not targets:
                continue

            exported: dict[str, str] = {}
            for target in targets:
                module = (path.parent / target).resolve()
                if not module.is_file():
                    continue
                for name in _exports_of(_read(module)):
                    exported.setdefault(name, module.name)
            if not exported:
                continue

            bound = _names_bound_from_a_relative_module(declarations)
            for match in _DECLARED_LOCALLY.finditer(code):
                bound.update(name for name in match.groups() if name)

            # Where each name is first called, so the message can point at a
            # line rather than assert an execution order it cannot know. The
            # first version named `sorted(...)[0]` as "the first of these to
            # run", which on the run that motivated this check named
            # `addTaskAndPersist` when the call that actually throws first is
            # `loadPersistedTasks()` in `DOMContentLoaded`. Alphabetical order
            # is not execution order, and a message that guesses at one is
            # evidence a reader cannot check.
            first_call: dict[str, int] = {}
            for match in _BARE_CALL.finditer(code):
                name = match.group(1)
                if name not in _NOT_A_CALL:
                    first_call.setdefault(name, match.start(1))

            missing = sorted((set(first_call) & set(exported)) - bound)
            if not missing:
                continue

            earliest = min(missing, key=lambda name: first_call[name])
            line = text.count("\n", 0, script.start(1) + first_call[earliest]) + 1

            named = ", ".join(f"`{name}`" for name in missing)
            module_names = ", ".join(sorted({exported[n] for n in missing}))
            plural = len(missing) > 1
            problems.append(
                f"{path.relative_to(root)} calls {named} inside "
                f'`<script type="module">` and imports '
                f"{'none of them' if plural else 'it'} from {module_names}, "
                f"which exports {'them all' if plural else 'that name'}. "
                "A module script has no global fallback, so line "
                f"{line} throws `ReferenceError: {earliest} is not defined` "
                "and every line after it in that handler is skipped. Add the "
                f"{'names' if plural else 'name'} to the existing `import "
                "{ ... }` clause."
            )
    return problems


#: `export function name(params)` and `export const name = (params) =>`.
_EXPORTED_FUNCTION = re.compile(
    r"""export\s+(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(""",
)
_EXPORTED_ARROW = re.compile(
    r"""export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"""
    r"""(?:async\s+)?(?:function\s*\*?\s*)?\(""",
)


def _scan(text: str, start: int, stop_at_depth_zero: str = ""):
    """Walk `text` from `start`, yielding `(index, char, depth)` outside strings.

    Quote-aware because it is given text whose string literals are intact:
    `f("a, b", c)` passes two arguments, and a splitter blind to quotes reads
    three. Template literals are treated as strings; a `${...}` inside one is
    bracket-balanced anyway, so nothing it contains can close the call early.
    """
    depth = 0
    quote = ""
    i = start
    while i < len(text):
        char = text[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
        else:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            yield i, char, depth
            if depth == 0 and char in stop_at_depth_zero:
                return
        i += 1


def _balanced(text: str, opening: int) -> tuple[str, int]:
    """The contents of the bracket at `opening`, and the index just past it.

    Returns `("", -1)` when the bracket never closes, so a truncated file is
    skipped rather than half-read.
    """
    if opening >= len(text) or text[opening] not in "([{":
        return "", -1
    for index, char, depth in _scan(text, opening, stop_at_depth_zero=")]}"):
        if depth == 0 and char in ")]}":
            return text[opening + 1 : index], index + 1
    return "", -1


def _split_at_top_level(text: str) -> list[str]:
    """`text` split on commas that are outside any bracket and any string."""
    parts: list[str] = []
    last = 0
    for index, char, depth in _scan(text, 0):
        if char == "," and depth == 0:
            parts.append(text[last:index])
            last = index + 1
    tail = text[last:]
    if parts or tail.strip():
        parts.append(tail)
    return parts


def _required_parameters(params: str) -> list[tuple[int, str]]:
    """`(position, name)` for each parameter with no default and no rest.

    A parameter with a default is never undefined, and a rest parameter is an
    array whatever the caller sends. Destructuring is skipped: whether it is
    satisfied is not a question of argument count.
    """
    required: list[tuple[int, str]] = []
    for position, piece in enumerate(_split_at_top_level(params)):
        piece = piece.strip()
        if not piece or "=" in piece or piece.startswith("...") or piece[0] in "{[":
            continue
        if _IDENTIFIER.match(piece):
            required.append((position, piece))
    return required


def _exported_signatures(text: str) -> dict[str, str]:
    """Exported function name to its parameter list, as written."""
    signatures: dict[str, str] = {}
    for pattern in (_EXPORTED_FUNCTION, _EXPORTED_ARROW):
        for match in pattern.finditer(text):
            params, _ = _balanced(text, match.end() - 1)
            if params or text[match.end() - 1 : match.end() + 1] == "()":
                signatures.setdefault(match.group(1), params)
    return signatures


#: `import * as appLogic from "./app-logic.mjs"`. The namespace is the only
#: thing bound, so every use of the module reads `appLogic.something(...)`.
_NAMESPACE_IMPORT = re.compile(
    r"""import\s*\*\s*as\s+([A-Za-z_$][\w$]*)\s*from\s*["']\.[^"']*["']""",
)


def _namespace_bindings(text: str) -> set[str]:
    """Names a file binds a whole relative module to."""
    return set(_NAMESPACE_IMPORT.findall(text))


def _argument_counts(
    code: str, name: str, namespaces: set[str] | None = None, literals: str | None = None
) -> list[int]:
    """How many arguments each call of `name` passes.

    Bare calls always count. A member call counts only when its receiver is a
    namespace this file bound from a relative module - `appLogic.addTask(...)`
    is a call of the export, `storage.getItem(...)` is not, and only the import
    clause tells the two apart.

    `code` has its string literals blanked, which is what makes finding a call
    safe; `literals` is the same text with only its comments blanked, which is
    what makes *counting* the arguments right. Both strippers replace characters
    one for one, so an index means the same thing in either. Counting against
    the blanked text alone read `addTaskAndPersist('New Task', 'desc', storage)`
    as one argument, because two of the three had been emptied.

    A call spreading an iterable is recorded as `-1`: the count is not knowable
    from the text, so nothing may be concluded from it.
    """
    source = literals if literals is not None and len(literals) == len(code) else code
    receivers = "|".join(re.escape(ns) for ns in sorted(namespaces or ()))
    prefix = rf"(?:(?:{receivers})\s*\.\s*)?" if receivers else ""
    counts: list[int] = []
    pattern = rf"(?<![.\w$])(?:new\s+)?{prefix}{re.escape(name)}\s*\("
    for match in re.finditer(pattern, code):
        args, closing = _balanced(source, match.end() - 1)
        if closing == -1:
            continue
        pieces = [piece.strip() for piece in _split_at_top_level(args)]
        counts.append(
            -1 if any(piece.startswith("...") for piece in pieces) else len(pieces)
        )
    return counts


def _required_arguments_only_the_tests_supply(
    files: list[Path], root: Path
) -> list[str]:
    """A parameter the suite always passes and the application never does.

    The signature of code that was unit-tested and never wired. A module written
    to take its collaborator as an argument is testable by construction - the
    suite hands it a fake and every case passes - and the application is the one
    caller that has to hand it the real thing. When it does not, the parameter is
    `undefined` on every path a user can reach, and the suite cannot see it.

    Found on one run of 2026-09-20. `app-logic.mjs` exported::

        export function addTaskAndPersist(title, description = '', storage)

    `app-logic.test.mjs` called it as
    `addTaskAndPersist('x', 'y', createMockStorage())` and passed. `index.html`
    called it as `addTaskAndPersist(title, description)`, so `storage` was
    `undefined`, `saveTasks(tasks, undefined)` reached `undefined.setItem` and
    threw. `loadPersistedTasks()` took the quieter path - `loadTasks(undefined)`
    throws inside a `try` that returns `[]` - so the page simply never restored
    anything. The brief's acceptance criteria required "Tasks persist between
    page refreshes"; nothing in that product ever wrote a byte.

    No reviewer caught this one. The security review and the milestone review
    both dissected the import clause on the same file in the same sprint and
    neither mentioned `storage`; the milestone review's acceptance evidence
    praised the "mock-storage adapter pattern" and "thorough test coverage of
    the data layer", which is exactly the arrangement that hid it. When the
    import clause was then fixed, `loadPersistedTasks(localStorage)` was
    corrected and the three write paths - add, toggle and delete - were left
    exactly as they were, so the product could read a saved list and never write
    one.

    Only reported where the tests *do* supply the argument. That is what makes
    the parameter's purpose unambiguous: it is wanted, it is exercised, and the
    product forgot it.
    """
    application = [
        path for path in files
        if not is_test(str(path.relative_to(root)))
        and path.suffix.lower() in _CLIENT_LOGIC_SUFFIXES | {".html", ".htm"}
    ]
    tests = [
        path for path in files
        if is_test(str(path.relative_to(root)))
        and path.suffix.lower() in _CLIENT_LOGIC_SUFFIXES
    ]
    if not application or not tests:
        return []

    modules = [
        path for path in files
        if path.suffix.lower() in _CLIENT_LOGIC_SUFFIXES
        and not is_test(str(path.relative_to(root)))
    ]

    problems: list[str] = []
    for module in modules:
        signatures = _exported_signatures(_only_the_code(_read(module)))
        if not signatures:
            continue
        for name, params in sorted(signatures.items()):
            required = _required_parameters(params)
            if not required:
                continue

            from_tests: list[int] = []
            for path in tests:
                text = _read(path)
                from_tests.extend(_argument_counts(
                    _only_the_code(text), name, _namespace_bindings(text),
                    _without_comments(text),
                ))
            from_application: list[int] = []
            callers: set[str] = set()
            for path in application:
                if path == module:
                    continue
                text = _read(path)
                bodies = (
                    _INLINE_SCRIPT.findall(text)
                    if path.suffix.lower() in {".html", ".htm"}
                    else [text]
                )
                for body in bodies:
                    counts = _argument_counts(
                        _only_the_code(body), name, _namespace_bindings(body),
                        _without_comments(body),
                    )
                    if counts:
                        callers.add(str(path.relative_to(root)))
                    from_application.extend(counts)

            if not from_tests or not from_application:
                continue
            if -1 in from_tests or -1 in from_application:
                continue

            for position, parameter in required:
                if not all(count <= position for count in from_application):
                    continue
                if not any(count > position for count in from_tests):
                    continue
                named = ", ".join(sorted(callers))
                most = max(from_application)
                problems.append(
                    f"{module.relative_to(root)} exports `{name}(...)` whose "
                    f"`{parameter}` parameter has no default, and {named} calls "
                    f"it with {most} argument{'' if most == 1 else 's'} - so "
                    f"`{parameter}` is `undefined` every time the application "
                    f"runs it. The test suite does pass that argument, which is "
                    f"why nothing fails: the suite hands `{name}` a stand-in and "
                    "the product hands it nothing. Pass the real one at the call "
                    f"site in {named}, or give `{parameter}` a default the "
                    "product can rely on."
                )
    return problems


#: A run of user actions written as a list - "add/edit/delete",
#: "add, edit and delete", "create, read, update, delete". Only a delimited run
#: of bare verbs counts: prose mentioning one verb is not an enumeration, and it
#: is the enumeration that makes the omission of one member legible.
_ACTION_LIST = re.compile(
    r"(?<![\w-])((?:[a-z]{3,10})(?:\s*(?:/|,|\s+and\s+|\s+or\s+)\s*[a-z]{3,10}){1,5})(?![\w-])"
)

#: Verbs that name something a user does to a record. Deliberately a closed set:
#: an open one turns every comma-separated phrase in a document into a
#: requirement, and "simple, fast and lightweight" is not a feature list.
_USER_ACTIONS = frozenset({
    "add", "create", "edit", "update", "modify", "rename", "delete", "remove",
    "complete", "filter", "search", "sort", "archive", "duplicate", "reorder",
})

#: Words that count as evidence the capability exists. Narrow on purpose: a
#: synonym earns its place only if a developer would write it *because* the
#: feature is there.
#:
#: The first version accepted `update`, `change`, `new`, `append` and `check`,
#: and one run - which has no way to edit a task - was reported clean
#: because one comment in it reads "update closure so subsequent ops work".
#: `change` is a DOM event, `new` is an operator, `append` and `check` are
#: `appendChild` and `checkbox`. None of them says a user can do anything.
#:
#: `active` and `completed` were in the `filter` row for the same reason and
#: were worse: they are the CSS class names every to-do list has whether or not
#: it filters by them.
_SAME_ACTION = {
    "add": ("add", "create"),
    "create": ("create", "add"),
    "edit": ("edit", "rename"),
    "update": ("update", "edit", "rename"),
    "modify": ("modify", "edit", "rename"),
    "rename": ("rename", "edit"),
    "delete": ("delete", "destroy"),
    "remove": ("remove", "delete", "destroy"),
    "complete": ("complete", "completed", "toggle", "done"),
    "filter": ("filter",),
    "search": ("search", "query"),
    "sort": ("sort",),
    "archive": ("archive",),
    "duplicate": ("duplicate", "clone"),
    "reorder": ("reorder", "drag"),
}


#: How an action word may end when a *test* names it. A suite describes
#: behaviour in English - `test('adds a task')`, `it('renames inline')` - while
#: an implementation spells it as an identifier, `addTask`. Matching only the
#: identifier form against a suite reported every action of every product as
#: untested, `add` included, with `test('adds a task')` in the file.
#:
#: Still refuses an unrelated longer word: `add` does not match `address`,
#: because `r` is not one of these endings and the lookahead then rejects it.
_INFLECTED = r"(?:s|es|ed|d|ing)?"


def _names_the_action(text: str, words: tuple[str, ...], inflected: bool = False) -> bool:
    """Whether `text` names this action, by any of its accepted spellings.

    Two shapes count, and both are needed.

    **At the start of a name** - `editTask`, `edit-btn`, `edit_task`,
    `deleteTask(id)`. The lookbehind refuses a preceding `.` so a built-in
    method of the same name is not evidence: `tasks.filter(...)` is
    `Array.prototype.filter` and it vouched for three dead buttons once
    already.

    **At a camelCase boundary inside one** - `saveEdit`, `cancelEdit`,
    `handleEditClick`. One run's product implements inline editing in
    full: a double-click handler on `.task-title`, `saveEdit()`, `cancelEdit()`,
    Enter to commit, Escape to cancel, blur to save, and
    `updateTask(id, { title })` underneath. Not one of those names starts with
    `edit`, so the first shape alone reported the product as having no way to
    edit a task, and that finding went to the reviewer as blocking.

    It was harmless while `edit` only entered the required set when the run's
    own documents kept the word. Now the brief puts it there on every run, so
    the gap fires on every product that names its handlers this way.

    The boundary has to be a *capital* after a lowercase letter, which is what
    keeps this narrow: `credit` and `discredit` contain `edit` after a
    lowercase letter and are not camelCase boundaries, so they still do not
    count. `editing` and `editor` are still refused by the trailing
    `(?![a-z])`.
    """
    tail = _INFLECTED if inflected else ""
    for word in words:
        starts_a_name = rf"(?<![\w.-])(?i:{word}){tail}(?![a-z])"
        inside_a_name = rf"(?<=[a-z0-9]){word.capitalize()}{tail}(?![a-z])"
        if re.search(starts_a_name, text) or re.search(inside_a_name, text):
            return True
    return False


def _actions_required_in(text: str, required: dict[str, str]) -> dict[str, str]:
    """Add every user action one document's acceptance criteria enumerate.

    Maps the action to the line it was read from, so a finding can quote its
    source rather than assert it. Shared by the two callers below, which differ
    only in what they read: the run's own documents, and the brief it was given.
    """
    in_requirements = False
    for line in text.splitlines():
        if _A_HEADING.match(line):
            in_requirements = bool(_A_REQUIREMENT_SECTION.match(line))
            continue
        lowered = line.lower()
        if not in_requirements:
            if "acceptance" not in lowered and "criteria" not in lowered:
                if not _LOOKS_LIKE_A_CRITERION.search(lowered):
                    continue
        for match in _ACTION_LIST.finditer(lowered):
            parts = [
                piece.strip()
                for piece in re.split(r"/|,|\s+and\s+|\s+or\s+", match.group(1))
            ]
            named = [piece for piece in parts if piece in _USER_ACTIONS]
            # Two or more, so a single verb in prose is never a list.
            if len(named) < 2:
                continue
            for action in named:
                required.setdefault(action, line.strip())
    return required


#: The workflow documents that state what the product must do. The other four -
#: `architecture_review`, `security_review`, `milestone_review` and the sprint
#: summaries - exist to comment on the work, and a comment is not a requirement.
#:
#: Every `*.md` under `docs/` used to be read, which put a reviewer's own prose
#: into the requirement set. Measured on one run, whose blocking finding was
#:
#:     This project's own documents require that a user can `edit`: "- The test
#:     suite `app.test.mjs` only clears local storage and lacks tests for core
#:     CRUD operations (add, edit, delete) or filtering tasks, failing to meet
#:     the a[cceptance criteria]"
#:
#: The quoted line is a review finding about missing *tests*. The word `edit`
#: inside it was read as the documents requiring that a user can edit, and the
#: result graded BREAKS.
#:
#: Worse than one false positive: it is a loop. A review's text becomes the next
#: round's requirements, so each revision can manufacture blocking findings from
#: the previous review's complaints, and the run reaches its revision limit
#: having been told to implement things nobody asked for. Across the 76 stored
#: workspaces these two checks produce 111 of about 190 breaking findings, which
#: is where that pressure comes from.
#:
#: `sprint_plan` and `milestone_plan` are kept: they say what the run will build,
#: which is a statement of intent about the product, and a plan naming a feature
#: nothing implements is the finding these checks exist for.
_DOCUMENTS_THAT_STATE_REQUIREMENTS = (
    "product_intake.md",
    "technical_specification.md",
    "technology_stack.md",
    "tools_and_models.md",
    "milestone_plan.md",
    "sprint_plan.md",
)


def _actions_the_documents_require(root: Path) -> dict[str, str]:
    """Every user action this project's own acceptance criteria enumerate.

    Read from the documents that state requirements, not from the ones that
    review the work - see `_DOCUMENTS_THAT_STATE_REQUIREMENTS`.

    A `.md` in the workspace root is still read whatever it is called: that is
    where an operator's own brief lands when a run is given one, and the brief
    outranks everything here.
    """
    required: dict[str, str] = {}
    documents: list[Path] = []
    folder = root / "docs"
    if folder.is_dir():
        documents.extend(
            folder / name
            for name in _DOCUMENTS_THAT_STATE_REQUIREMENTS
            if (folder / name).is_file()
        )
    if root.is_dir():
        documents.extend(sorted(root.glob("*.md")))
    for document in documents:
        try:
            text = _read(document)
        except Exception:  # noqa: BLE001 - a missing document requires nothing
            continue
        _actions_required_in(text, required)
    return required


def _actions_the_brief_requires(brief: str) -> dict[str, str]:
    """Every user action the operator's own brief enumerates.

    The documents above are the run's restatement of this. A restatement can
    lose a requirement, and when it does, every check that reads only the
    restatement agrees with the loss.

    Measured on one run. `tests/brief_low.md` states "Users can add, edit,
    delete tasks". The run's technical specification records:

        Q3: Is inline editing of title/description desired beyond toggling
        completion status? The acceptance criteria mention 'edit' but the core
        workflows only describe marking complete/incomplete. Decision recorded:
        'Edit' refers to toggling completion status. Inline text editing is
        deferred.

    From that point the documents enumerate create, update, complete and
    delete - never edit - so `_actions_the_documents_require` returns a set
    with no `edit` in it, `_a_required_action_nothing_implements` finds nothing
    missing, and the run completes with no way to edit a task. Four of the
    eight stored products have no edit for this reason or its cousins.

    Note what this is not: the run is allowed to *defer* a requirement, and
    `_where_the_run_deferred_it` already reports that with the right words.
    What it may not do is redefine one out of existence, because then nothing
    reports anything.
    """
    return _actions_required_in(brief or "", {})


#: A bullet that reads as a delivered-capability claim even without the word
#: "acceptance" on it - the intake writes these as plain list items.
_LOOKS_LIKE_A_CRITERION = re.compile(
    r"users? can|must be able|delivered|supports?\b|able to"
)

#: A heading under which every bullet is a requirement, whatever it is worded
#: like. The per-line test alone was too narrow: one run's intake stated
#: "All four CRUD operations (add, edit, delete, mark complete) work without
#: errors" under `## Success measures`, which names no actor and so matched
#: nothing, and the run shipped without editing while this check said nothing.
#: A section heading is the more reliable signal, because the document's own
#: structure is what says these lines are requirements.
_A_REQUIREMENT_SECTION = re.compile(
    r"^#{1,6}\s.*\b(acceptance|criteri|success measure|requirement|"
    r"must have|definition of done|mvp)", re.I
)

#: Ends a requirement section: the next heading at any level.
_A_HEADING = re.compile(r"^#{1,6}\s")


#: A decision record that drops something: "ADR-08 - Inline Editing: Deferred",
#: "out of scope for the MVP", "not implemented in this release".
_A_DEFERRAL = re.compile(
    r"defer\w*|out of scope|post-?mvp|not implemented|won't ship|will not ship"
    # A capability declared away rather than postponed. One run's specification:
    # 'There is no separate "edit" mode - the title and description are
    # immutable after creation (future work may...)', for a brief requiring
    # "Users can add, edit, delete tasks". None of the words above is in it.
    r"|future (?:work|release|version|iteration|enhancement|sprint)s?"
    r"|no (?:separate |dedicated )?[\"'`\w-]+ (?:mode|feature|capability|support)"
    r"|(?:cannot|can't|can not) be (?:edited|changed|modified|updated|renamed)"
    r"|not (?:editable|modifiable|supported)|immutable after",
    re.I,
)


def _where_the_run_deferred_it(root: Path, action: str, words: tuple[str, ...]) -> str:
    """The line in this run's own documents that drops `action`, or "".

    A run may decide not to build something and record why - that is what a
    decision record is for. What it may not do is make that decision about a
    criterion the brief states, on its own authority, and this finds the line
    where it did.
    """
    for folder in (root / "docs", root):
        if not folder.is_dir():
            continue
        for document in sorted(folder.glob("*.md")):
            try:
                text = _read(document)
            except Exception:  # noqa: BLE001 - a missing document defers nothing
                continue
            for line in text.splitlines():
                if not _A_DEFERRAL.search(line):
                    continue
                if _names_the_action(line, words, inflected=True):
                    return f"{document.name}: {line.strip()[:160]}"
    return ""


#: The action a required-action finding is about, in either check's wording.
_A_REQUIRED_ACTION_FINDING = re.compile(r"a user can `([a-z]+)`|No test names `([a-z]+)`")


def _own_spellings(action: str) -> tuple[str, ...]:
    """The action's own word, with the `-ing` form of a word ending in a silent e."""
    return (action, action[:-1] + "ing") if action.endswith("e") else (action,)


def _group_spellings(action: str) -> tuple[str, ...]:
    """Every accepted spelling of the action, silent-e `-ing` forms included."""
    words = list(_SAME_ACTION.get(action, (action,)))
    words += [word[:-1] + "ing" for word in words if word.endswith("e")]
    return tuple(dict.fromkeys(words))


def _the_claim(finding: str) -> str:
    """A review finding's first sentence, without the text it quotes.

    The claim is what the finding says is wrong; the rest is remediation. A
    quotation is what it cites - one review's finding about editing quoted the
    success measure "Users can add, edit, delete tasks", which names three
    actions the claim was not about.
    """
    first = re.split(r"(?<=[.!?])\s", str(finding or "").strip(), maxsplit=1)[0]
    return re.sub(r'"[^"]*"|\u201c[^\u201d]*\u201d', " ", first)


def later_sprint_work_in(finding: str, this_sprint: str, later_sprints: str) -> list[str]:
    """The actions a review finding is about, when they are later sprints' work; else [].

    A milestone review is given the brief, and reads it as the milestone's
    requirement. One run's sprint 1 - "basic UI skeleton, state management,
    persistence, and addTask", with "Editing, deleting or toggling tasks"
    listed as out of scope and sprint 2 building exactly those - was blocked
    twice: "The application does not support editing of existing tasks" and
    "lacks the ability to delete tasks". That review would have had sprint 1
    build sprint 2.

    Returned only when every action the claim names by its own word is built
    by a later sprint and named nowhere in this sprint's goal, scope or
    acceptance criteria - a finding about work this sprint does stays exactly
    as it was. Nothing here names a product; the actions are the table of user
    actions every other check reads.
    """
    if not (later_sprints or "").strip():
        return []
    claim = _the_claim(finding)
    claimed = [action for action in _SAME_ACTION if _names_the_action(claim, _own_spellings(action), inflected=True)]
    if not claimed:
        return []
    for action in claimed:
        spellings = _group_spellings(action)
        if not _names_the_action(later_sprints, spellings, inflected=True):
            return []
        if _names_the_action(this_sprint or "", spellings, inflected=True):
            return []
    return claimed


#: A file named in prose: a lower-case name with an extension of two or more
#: characters, optionally under directories. Lower case so that a technology
#: written with a dot - "a Node.js module", which one run's blocking finding
#: about a browser module began with - and "e.g." are never read as files.
#: Several dotted parts are one name: `state.test.js` is not `state.test`.
_A_FILE_NAMED = re.compile(
    r"(?<![\w/.-])((?:[\w-]+/)*[a-z0-9_-]+(?:\.[a-z0-9_-]+)*\.[a-z][a-z0-9]{1,5})(?![\w/-]|\.\w)"
)


def later_sprint_files_in(finding: str, this_sprint: str, later_sprints: str) -> list[str]:
    """The files a review finding is about, when a later sprint makes them; else [].

    `later_sprint_work_in` reads the claim for user actions, and a finding about
    a missing file names none. Measured on one run: sprint 1 built the task
    store alone, sprint 2's scope read "Add index.html in the project root",
    and sprint 1's review raised "The repository contains no index.html or
    other HTML entry point" as blocking - on the third revision, which ended
    the run.

    Returned only when every file the claim names is named in a later sprint's
    goal, scope or acceptance criteria and nowhere in this sprint's; a finding
    that names any file this sprint makes stays as it was.
    """
    if not (later_sprints or "").strip():
        return []
    named = {PurePosixPath(match).name for match in _A_FILE_NAMED.findall(_the_claim(finding))}
    if not named:
        return []
    later = (later_sprints or "").lower()
    now = (this_sprint or "").lower()
    for name in named:
        spelled = re.compile(rf"(?<![\w-]){re.escape(name.lower())}(?![\w-])")
        if not spelled.search(later) or spelled.search(now):
            return []
    return sorted(named)


def planned_for_a_later_sprint(problem: str, later_sprints: str) -> bool:
    """Whether `problem` is a missing action a later sprint of the plan builds.

    `_a_required_action_nothing_implements` and `_a_required_action_no_test_covers`
    read the whole project's requirements and run in every test round, so they
    reported sprint two's work as sprint one's defect. Measured on one run: the
    specification described inline editing (ADR-08) and the sprint plan put it
    in sprint 2, and sprint 1's first test round reported "Edit feature required
    by product_intake.md but not implemented" as major. `defect_fix_1_0` then
    built editing inside sprint 1, outside any plan.

    Deferring to a later sprint is what a sprint plan is for; the final gate at
    the last sprint (`_a_brief_requirement_the_run_never_built`) is what catches
    a requirement no sprint ever builds. `later_sprints` is the goal, in-scope
    work and acceptance criteria of every sprint after this one - never their
    `out_of_scope`, which names work in order to exclude it.
    """
    match = _A_REQUIRED_ACTION_FINDING.search(problem or "")
    if not match or not (later_sprints or "").strip():
        return False
    action = match.group(1) or match.group(2)
    return _names_the_action(later_sprints, _SAME_ACTION.get(action, (action,)), inflected=True)


def brief_actions_the_text_defers(brief: str, text: str) -> list[tuple[str, str, str]]:
    """Each action the brief requires that `text` defers, as (action, brief line, text line).

    The same judgement `_where_the_run_deferred_it` makes about a finished
    workspace, made about one document before anything is built - for the
    architecture review, which is the last point where dropping a requirement
    costs nothing to undo.

    Measured on one run. `tests/brief_low.md` states "Users can add, edit,
    delete tasks". Its specification wrote "ADR-03 - 'Edit' means toggle
    completion only" and "Inline description editing is deferred", the
    architecture review accepted that as a trade-off, and every sprint-one
    test round was then told by `_a_required_action_nothing_implements` that
    the deferral carried no authority. The defect-fix stages it went to are
    scoped to a milestone that never included editing, so none of them could
    act on it: one added "edit" to a test name, and three test rounds ran.

    Only the first deferring line per action, and only actions the brief
    itself enumerates - the run's restatement of the brief is what this is
    checking, so it cannot be the source.
    """
    required = _actions_the_brief_requires(brief)
    found: list[tuple[str, str, str]] = []
    for action in sorted(required):
        words = _SAME_ACTION.get(action, (action,))
        for line in _without_html_comments(text).splitlines():
            if any(
                _names_the_action(part, words, inflected=True)
                for part in _what_a_line_defers(line)
            ):
                found.append((action, required[action], line.strip()[:200]))
                break
    return found


def _without_html_comments(text: str) -> str:
    """`text` without its HTML comments.

    Every rendered document ends with the workflow's own footer, "Editing this
    file does not change what the pipeline reads", which names `edit` in a
    line of its own and read as a specification describing editing.
    """
    return re.sub(r"<!--.*?-->", "", text or "", flags=re.S)


def brief_actions_the_text_never_describes(brief: str, text: str) -> list[tuple[str, str]]:
    """Each action the brief requires that `text` only ever lists, as (action, brief line).

    The silent half of `brief_actions_the_text_defers`. One run's
    specification described create, toggle, delete and filter each as a flow -
    a handler, the data change, the re-render - and named editing only in
    "full CRUD operations (create, read, update, delete tasks)" and in the
    success measure it restated, "add, edit, delete tasks". Nothing deferred
    it, so nothing said so; the sprint plan raised it as an open question and
    answered it itself: "treat as toggle-only".

    A line counts as describing an action when it names that action and at most
    one other user action. A line naming three is a list of requirements, and
    repeating a requirement is not saying how it will be met.
    """
    required = _actions_the_brief_requires(brief)
    missing: list[tuple[str, str]] = []
    for action in sorted(required):
        words = _SAME_ACTION.get(action, (action,))
        others = [
            other for other in _USER_ACTIONS
            if other not in words and action not in _SAME_ACTION.get(other, (other,))
        ]
        described = False
        for line in _without_html_comments(text).splitlines():
            if not _names_the_action(line, words, inflected=True):
                continue
            named = sum(
                1 for other in others if _names_the_action(line, (other,), inflected=True)
            )
            if named <= 1:
                described = True
                break
        if not described:
            missing.append((action, required[action]))
    return missing


#: Where the thing deferred stops and the reason for deferring it starts.
#: A modal starts one too: "future work may add it" is a plan, not what is dropped.
_A_REASON = re.compile(
    r"\b(?:to|because|since|as|so|for|until|due|given|may|might|could|would|will|can)\b",
    re.I,
)


def _what_a_line_defers(line: str) -> list[str]:
    """The part of each sentence in `line` that names what is being deferred.

    The words before the deferral and the words after it, up to the reason.
    The whole line was too much: "Inline description editing is deferred to
    avoid adding complexity" reads as deferring `add` as well as `edit`,
    because `adding` is in the reason.
    """
    parts: list[str] = []
    for sentence in re.split(r"[.;]\s+|[.;]$", line):
        match = _A_DEFERRAL.search(sentence)
        if not match:
            continue
        after = sentence[match.end():]
        reason = _A_REASON.search(after)
        parts.append(sentence[: match.start()])
        # The phrase itself can name what it drops: 'no separate "edit" mode'.
        parts.append(match.group(0))
        parts.append(after[: reason.start()] if reason else after)
    return parts


def _a_required_action_nothing_implements(
    files: list[Path], root: Path, brief: str = ""
) -> list[str]:
    """An action the run's own documents enumerate and the product never names.

    The workflow captures acceptance criteria correctly and then loses one.
    `tests/brief_low.md` lists its features as "Add new tasks", "Mark tasks as
    complete/incomplete", "Delete tasks", "Filter tasks by status" - and states
    separately, under Acceptance Criteria, "Users can add, edit, delete tasks".
    Editing appears in the second list and not the first.

    Two of three runs against that brief shipped no way to edit a task. One
    run's own `product_intake.md` had it right - "All four acceptance
    criteria delivered together: add/edit/delete, persistence, filtering, and
    responsive design" - and the product it then built has no edit control, no
    edit handler and no test mentioning one. Neither the security review nor the
    milestone review raised it; one run, from the same brief, implemented
    editing with a double-click handler and an Edit button, so this is what the
    workflow drops rather than what it cannot do.

    Deliberately literal. It reports only an action the documents *enumerate*
    alongside at least one other, and only when neither that word nor any of its
    ordinary synonyms appears anywhere in the application, the page or the
    tests. A product that implements editing and calls it `update` is silent
    here, and so is a criterion like "responsive design", which names no action.
    """
    required = _actions_the_documents_require(root)
    # The brief outranks the run's restatement of it. An action the operator
    # asked for and the documents no longer mention is still required - see
    # `_actions_the_brief_requires` for the run that proved it.
    from_the_brief = _actions_the_brief_requires(brief)
    redefined = {
        action: line
        for action, line in from_the_brief.items()
        if action not in required
    }
    required = {**from_the_brief, **required}
    if not required:
        return []

    # Evidence is behaviour, so the corpus is script, not markup: every script
    # and test file, plus the bodies of any inline `<script>` - which is where
    # a page that embeds its whole application keeps it - and no CSS and no
    # markup at all.
    #
    # One run is why. Its milestone review found "Filter buttons
    # (All/Active/Completed) are present in index.html with data-filter
    # attributes and CSS styling, but no JavaScript handler exists for them".
    # It was right and this check was silent, because `id="filter-buttons"` in
    # the page and `.filter-btn` in the stylesheet read as `filter` being
    # delivered. Three buttons that do nothing are the opposite of delivered.
    pieces: list[str] = []
    for path in files:
        suffix = path.suffix.lower()
        # Tests excluded. This check asks whether the *product* does it, and a
        # suite naming a feature is not the product having one - one run
        # was reported clean for `edit` because `app.test.mjs` mentions it,
        # while `app.js` has no edit anywhere. `_a_required_action_no_test_covers`
        # asks the other question and reads only the suites, so the two are
        # complementary and neither may borrow the other's evidence.
        #
        # The same mistake, in a different check, gave one run's dead
        # filter buttons an alibi from the Playwright spec that located them.
        if is_test(str(path.relative_to(root))):
            continue
        if suffix in _CLIENT_LOGIC_SUFFIXES:
            pieces.append(_read(path))
        elif suffix in {".html", ".htm"}:
            pieces.extend(_INLINE_SCRIPT.findall(_read(path)))
    if not pieces:
        return []
    # Not lowered. The camelCase boundary is the whole point of the matcher
    # below - `addTask` is `add` followed by a capital - and `.lower()` turned
    # it into `addtask`, where `add` is followed by a lowercase letter and every
    # action in every product read as missing.
    corpus = "\n".join(pieces)

    problems: list[str] = []
    for action in sorted(required):
        words = _SAME_ACTION.get(action, (action,))
        # `(?![a-z])` rather than a word boundary. The capability is almost
        # always spelled as part of an identifier - `addTask`, `delete-btn`,
        # `editTask` - and `\b` matches none of those, so the first version
        # reported every action of every product as missing, `add` included,
        # with `function addTask` sitting in the file. Refusing only a
        # following lowercase letter keeps `address` and `additional` from
        # counting as `add`.
        # The case-insensitivity is scoped to the word with `(?i:...)` rather
        # than passed as `re.I`. A global flag makes `[a-z]` match capitals too,
        # so `(?![a-z])` rejected the capital in `addTask` - the very boundary
        # it exists to accept - and every action still read as missing.
        # The lookbehind refuses a preceding `.` as well, so a built-in method
        # is not evidence of a feature. `tasks.filter(t => t.id !== taskId)`
        # inside `deleteTask` is `Array.prototype.filter`, and it was the only
        # thing standing between one run's three dead filter buttons and
        # this finding.
        if _names_the_action(corpus, words):
            continue
        alternatives = ", ".join(f"`{word}`" for word in words[1:])
        deferral = _where_the_run_deferred_it(root, action, words)
        if action in redefined:
            # The brief asked for it and this run's own documents no longer do.
            # That is not a deferral - a deferral leaves the requirement
            # standing and records a decision against it, which
            # `_where_the_run_deferred_it` reports in the branch below. This is
            # the requirement being rewritten, after which nothing in the run
            # disagrees with the product, because the product matches the
            # rewrite.
            because = f" The run recorded why: {deferral}." if deferral else ""
            problems.append(
                f"The brief requires that a user can `{action}` - "
                f"\"{redefined[action][:140]}\" - and this run's own documents "
                f"no longer ask for it.{because} Nothing in the product names "
                f"it, and no check in this workspace was going to say so, "
                "because every one of them reads the documents rather than the "
                "brief. Restating a brief is not the same as changing it: a "
                "requirement can be deferred, with the operator's answer on "
                "the record, but it cannot be defined away by the run that was "
                "given it. Build it, or put the descope to the operator."
            )
            continue
        # Whose words to quote. The run's documents outrank the brief in
        # `required` so a finding can point at the file the run acts on - but a
        # document that restates the requirement narrowly carries the
        # narrowing with it. One run's intake wrote "Users can add, edit
        # (toggle complete/incomplete), and delete tasks" for a brief saying
        # "Users can add, edit, delete tasks". The final gate quoted the
        # intake, and the technical lead it was sent back to read "edit" as
        # toggling, found toggling built, and assigned a documentation fix.
        # The run escalated with editing still unbuilt.
        who, quoted = "This project's own documents require", f"\"{required[action][:160]}\""
        if action in from_the_brief:
            who, quoted = "The operator's brief requires", f"\"{from_the_brief[action][:160]}\""
            if " ".join(required[action].split()) != " ".join(from_the_brief[action].split()):
                quoted += (
                    f" (this run's documents restate it as \"{required[action][:140]}\"; a "
                    "restatement that narrows it to something already built does not "
                    "satisfy the brief's own words)"
                )
        if deferral:
            # Recorded, not forgotten - which is better, and still not the
            # run's decision to make. One run captured "Users can
            # successfully add, edit, and delete tasks without errors" in its
            # intake, then wrote "ADR-08 - Inline Editing: Deferred - not
            # implemented in MVP", and its milestone reviewer cited that ADR to
            # accept the milestone and called this check a false positive. The
            # ADR was real and the reasoning was sound; the authority was not.
            # A decision record the run wrote cannot descope a criterion the
            # brief states.
            problems.append(
                f"{who} that a user can "
                f"`{action}` - {quoted} - and also defer it: "
                f"{deferral}. Nothing in the product names it. Deferring is a "
                "decision a person makes, not one this run may make about a "
                "criterion it was given: the same workflow wrote both lines, so "
                "the deferral carries no authority the requirement does not. "
                "Build it, or put the descope to the operator and record their "
                "answer."
            )
            continue
        problems.append(
            f"{who} that a user can `{action}`: "
            f"{quoted}. Nothing in the product names it - "
            f"not {alternatives} either, in any source file, page or test. "
            "Every other action in that list is implemented, so this is one "
            "acceptance criterion delivered as far as the documents and no "
            "further. Either build it or record why it was dropped."
        )
    return problems


#: A clickable control carrying a `data-*` attribute: the whole tag, the
#: attribute's name, and its value. A `data-` attribute on a button exists to be
#: read by script - that is what the attribute is for - so one no script names
#: is the clearest form of a control that does nothing.
_CLICKABLE_WITH_DATA = re.compile(
    r"""<(?:button|a|input)\b[^>]*\bdata-([a-z][\w-]*)\s*=\s*["'][^"']*["'][^>]*>""",
    re.I,
)

#: A radio or checkbox that belongs to a named group: the whole tag and the
#: group's name. The other common way to build a set of controls, and the one
#: `_CLICKABLE_WITH_DATA` cannot see, because it carries no `data-` attribute.
#:
#: One run's filter bar is three of these. It wired them, so nothing was
#: lost there - but one run's dead filter bar was caught only because that
#: run happened to spell its buttons `data-filter`, and the same bar written
#: this way would have shipped dead and unreported.
_INPUT_IN_A_GROUP = re.compile(
    r"""<input\b[^>]*\btype\s*=\s*["'](?:radio|checkbox)["'][^>]*"""
    r"""\bname\s*=\s*["']([^"']+)["'][^>]*>"""
    r"""|<input\b[^>]*\bname\s*=\s*["']([^"']+)["'][^>]*"""
    r"""\btype\s*=\s*["'](?:radio|checkbox)["'][^>]*>""",
    re.I,
)

#: The `class` and `id` of a tag, so a control wired by either is left alone.
_TAG_CLASSES = re.compile(r"""\bclass\s*=\s*["']([^"']+)["']""", re.I)
_TAG_ID = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)

#: Two, so a single decorative `data-` attribute is never a feature.
MIN_DEAD_CONTROLS = 2


def _enclosing_ids(markup: str, start: int, end: int) -> set[str]:
    """Ids of the elements a control at `start`..`end` sits inside.

    Wiring by delegation happens on a container, so a container's id is
    evidence for the controls within it - and only for those. An element whose
    closing tag comes before the control is not a container, it is a sibling.

    Both halves of that were learned the hard way. The first version accepted
    any referenced id anywhere on the page, so on one run `task-list`
    vouched for filter buttons at the other end of the document. The second
    took the nearest preceding id, which is the same mistake with a smaller
    radius: `<ul id="task-list"></ul>` closes immediately and still stood in
    front of the next thing written after it.
    """
    found: set[str] = set()
    for opening in re.finditer(r"<([a-zA-Z][\w-]*)\b[^>]*>", markup[:start]):
        name = opening.group(1).lower()
        declared = _TAG_ID.findall(opening.group(0))
        if not declared:
            continue
        closing = re.search(rf"</{re.escape(name)}\s*>", markup[opening.end():])
        if closing and opening.end() + closing.start() >= end:
            found.update(declared)
    return found


def _enclosing_classes(markup: str, start: int, end: int) -> set[str]:
    """Every class on an element that encloses this span.

    The companion to `_enclosing_ids`. A group of radios is usually reached
    through the thing around it - `.filter-bar input`, `.filters label` - and
    the inputs themselves carry no class, so without this an ordinary wiring
    reads as no wiring.
    """
    classes: set[str] = set()
    depth = 0
    for match in reversed(list(re.finditer(r"<(/?)([a-zA-Z][\w-]*)\b([^>]*)>", markup[:start]))):
        closing, _name, attributes = match.groups()
        if closing:
            depth += 1
            continue
        if depth:
            depth -= 1
            continue
        for clause in _TAG_CLASSES.findall(attributes):
            classes.update(clause.split())
    return classes


def _a_control_group_no_script_operates(files: list[Path], root: Path) -> list[str]:
    """Clickable controls sharing a `data-*` handle nothing in any script reads.

    `_a_page_no_script_ever_touches` asks whether a page is wired at all, and
    says so in its own docstring: it "requires that nothing touches the document
    anywhere". A page that is wired for most of itself and dead in one corner is
    outside it by design, and that is the shape this catches.

    One run shipped exactly that. Its `index.html` carries

        <nav id="filter-buttons" aria-label="Filter tasks by status">
          <button data-filter="all" class="filter-btn active">All</button>
          <button data-filter="active" class="filter-btn">Active</button>
          <button data-filter="completed" class="filter-btn">Completed</button>

    styled in `style.css`, and no script in the project mentions `data-filter`,
    `filter-btn` or `filter-buttons`. The only `filter` anywhere in its
    JavaScript is `tasks.filter(t => t.id !== taskId)` inside `deleteTask` -
    `Array.prototype.filter`, nothing to do with the feature. The rest of the
    page works: tasks render, toggle and delete. Three buttons appear, respond
    to hover, and do nothing at all.

    "Filter functionality works correctly" is one of that brief's four
    acceptance criteria. Its milestone review found this and rated it Minor.

    A control is left alone if any script names its `data-` attribute, its id,
    any of its classes, or its parent's id, so delegation and class-based wiring
    are all evidence. Only a control with no handle referenced anywhere is
    reported.
    """
    scripts: list[str] = []
    for path in files:
        suffix = path.suffix.lower()
        if any(part in _SKIP for part in path.parts):
            continue
        # Tests excluded, exactly as `_a_page_no_script_ever_touches` excludes
        # them. A suite that locates a control does not operate it: one
        # run's `app.pw.spec.ts` holds
        # `filterNav.locator('[data-filter="all"]')` for three buttons its
        # product never wires, and reading that as wiring is how a dead control
        # acquires an alibi from the very suite that should have caught it.
        if suffix in _CLIENT_LOGIC_SUFFIXES and not is_test(
            str(path.relative_to(root))
        ):
            scripts.append(_read(path))
    if not scripts:
        return []

    problems: list[str] = []
    for page in files:
        if page.suffix.lower() not in {".html", ".htm"}:
            continue
        markup = _read(page)
        inline = _INLINE_SCRIPT.findall(markup)
        code = "\n".join(scripts + inline)
        if not _TOUCHES_THE_PAGE.search(code):
            # Nothing is wired at all; that is the other check's finding, and
            # reporting it twice in different words helps nobody.
            continue

        dead: dict[str, list[str]] = {}
        for match in re.finditer(r"<[^>]+>", markup):
            tag = match.group(0)
            found = _CLICKABLE_WITH_DATA.match(tag)
            if not found:
                continue
            attribute = found.group(1).lower()
            # The two spellings a script reads the attribute by, and not the
            # bare name. `filter` on its own matched `tasks.filter(t => ...)`
            # in one run's `deleteTask` - `Array.prototype.filter` - and
            # vouched for the very buttons this was written to find.
            handles = {f"data-{attribute}", f"dataset.{attribute}"}
            handles.update(_TAG_ID.findall(tag))
            for clause in _TAG_CLASSES.findall(tag):
                handles.update(clause.split())
            handles.update(_enclosing_ids(markup, match.start(), match.end()))
            if any(
                re.search(rf"(?<![\w-]){re.escape(handle)}(?![\w-])", code)
                for handle in handles
                if handle
            ):
                continue
            dead.setdefault(attribute, []).append(tag.strip())

        # The same question for a control group built the other common way:
        # radios or checkboxes sharing a `name`, which carry no `data-`
        # attribute and so are invisible to the pattern above.
        grouped: dict[str, list[str]] = {}
        for match in _INPUT_IN_A_GROUP.finditer(markup):
            tag = match.group(0)
            group = (match.group(1) or match.group(2) or "").strip()
            if not group:
                continue
            # The spellings a script reaches a named group by - never the bare
            # word. `filter` on its own matches `tasks.filter(t => ...)`, which
            # is the trap this file has already fallen into once.
            handles = {
                f'name="{group}"',
                f"name='{group}'",
                f"name={group}",
                f'getElementsByName("{group}")',
                f"getElementsByName('{group}')",
            }
            handles.update(_TAG_ID.findall(tag))
            for clause in _TAG_CLASSES.findall(tag):
                handles.update(clause.split())
            handles.update(_enclosing_ids(markup, match.start(), match.end()))
            # And the classes of whatever encloses them: `.filter-bar input`
            # is how a group inside a labelled section is usually reached, and
            # the inputs themselves often carry no class at all.
            handles.update(_enclosing_classes(markup, match.start(), match.end()))
            if any(
                handle in code
                or re.search(rf"(?<![\w-]){re.escape(handle)}(?![\w-])", code)
                for handle in handles
                if handle
            ):
                continue
            grouped.setdefault(group, []).append(tag.strip())

        for group, tags in sorted(grouped.items()):
            if len(tags) < MIN_DEAD_CONTROLS:
                continue
            problems.append(
                f"{page.relative_to(root)} has {len(tags)} inputs in the "
                f"`{group}` group, and no script in this project reaches them "
                f"- not by `name=\"{group}\"`, not by their ids or classes, "
                "and not by the id or class of anything they sit inside. A "
                "radio group exists to be read when it changes, so these "
                "render, take the click and change nothing. The first is "
                f"`{tags[0][:90]}`. Either wire them or take them off the page."
            )

        for attribute, tags in sorted(dead.items()):
            if len(tags) < MIN_DEAD_CONTROLS:
                continue
            problems.append(
                f"{page.relative_to(root)} has {len(tags)} clickable controls "
                f"carrying `data-{attribute}`, and no script in this project "
                f"mentions `data-{attribute}`, their classes or their ids. A "
                "`data-` attribute on a button exists to be read by script, so "
                "these render, respond to hover and do nothing when clicked. "
                f"The first is `{tags[0][:90]}`. Either wire them or take them "
                "off the page - a control that looks live and is not is worse "
                "than one that is absent."
            )
    return problems


def _a_required_action_no_test_covers(
    files: list[Path], root: Path, brief: str = ""
) -> list[str]:
    """An action the documents require that no test anywhere names.

    Every verification this harness performs reads the implementation. Unit
    tests import the module that exists; browser tests drive the page as built;
    reviewers read the code in front of them. Nothing is derived from the
    requirement list, so a requirement that was never built has no failing test
    - it has no test at all, and a green suite says so with confidence.

    One run is the clean demonstration. Its Playwright suite is good: 72
    assertions, 22 of them `toHaveCount`, four page reloads checking that tasks
    survive a refresh. It ran six times, caught real failures - `2 failed, 10
    passed` early in the run - and finished green at 14 tests. It grew from 12
    tests to 14 as features were built, so the tests for filtering arrived in
    the sprint that wired the filter buttons, and never existed while they were
    dead. `edit`, which that product never built at all, has no test in any of
    its four files.

    This is the companion to `_a_required_action_nothing_implements`, and the
    two ask different questions on purpose. That one asks whether the product
    does it. This asks whether anything would notice if it stopped - which is
    the question a suite exists to answer, and the one that goes unasked when
    the suite is written from the code rather than from the brief.

    Silent when the project has no tests at all: that is a different finding and
    `_tests_the_project_never_runs` and its neighbours already make it.
    """
    # The brief outranks the run's restatement of it here too: a suite
    # written from documents that dropped a requirement cannot miss it.
    from_the_documents = _actions_the_documents_require(root)
    from_the_brief = _actions_the_brief_requires(brief)
    required = {**from_the_brief, **from_the_documents}
    if not required:
        return []

    suites = [
        path for path in files
        if path.suffix.lower() in _CLIENT_LOGIC_SUFFIXES
        and is_test(str(path.relative_to(root)))
    ]
    if not suites:
        return []
    corpus = "\n".join(_read(path) for path in suites)

    problems: list[str] = []
    for action in sorted(required):
        words = _SAME_ACTION.get(action, (action,))
        # Inflected here and not above: a suite says "adds a task" where an
        # implementation says `addTask`.
        if _names_the_action(corpus, words, inflected=True):
            continue
        named = ", ".join(sorted(str(p.relative_to(root)) for p in suites))
        # Named accurately. An action that survives only in the brief is not
        # something "this project's own documents require" - the documents are
        # where it was lost, and a finding that misattributes its own source
        # invites the reviewer to go and check the wrong file.
        source = (
            "this project's own documents require"
            if action in from_the_documents
            else "the brief requires"
        )
        problems.append(
            f"No test names `{action}`, which {source} "
            f"a user can do: \"{required[action][:140]}\". Searched "
            f"{named}. A suite written from the code cannot miss a feature the "
            "code does not have, so it passes and reports nothing - which is "
            "how a requirement leaves the intake and never arrives. Write the "
            f"test for `{action}` even if it fails today: a failing test is the "
            "only thing here that remembers."
        )
    return problems


#: Turning stored bytes back into values, in the languages this harness
#: builds in. Every one of these raises on input it cannot parse.
_DESERIALISES = re.compile(
    r"(?<![\w.$])(?:JSON\.parse|json\.loads|json\.load|yaml\.safe_load|yaml\.load"
    r"|pickle\.loads|toml\.loads|plist\.loads|Marshal\.load|JSON\.parse!"
    r"|serde_json::from_str|json\.Unmarshal|JsonSerializer\.Deserialize)\s*[(<]"
)

#: Reading something that outlived the process, and therefore something a
#: user, another program or a previous version of this one could have left in
#: any state at all.
_READS_PERSISTED_DATA = re.compile(
    r"(?<![\w.$])(?:localStorage|sessionStorage)\s*\.\s*getItem\s*\("
    r"|(?<![\w.$])indexedDB\b"
    r"|(?<![\w.$])readFileSync\s*\(|(?<![\w.$])readFile\s*\("
    r"|(?<![\w.$])read_text\s*\(|(?<![\w.$])\bopen\s*\([^)]*['\"]r"
    r"|(?<![\w.$])os\.ReadFile\s*\(|(?<![\w.$])File\.read\s*\("
)

#: Any error handling at all, in any of those languages. A file that has one
#: is left alone: this check asks whether the author thought about failure,
#: not whether every call site is individually wrapped.
_HANDLES_AN_ERROR = re.compile(
    r"(?<![\w.$])(?:try\s*[{:]|catch\s*[({]|except\b|rescue\b|recover\s*\("
    r"|\.catch\s*\(|if\s+err\s*!=\s*nil|match\s+.*\{)"
)


def _persisted_data_parsed_without_a_guard(files: list[Path], root: Path) -> list[str]:
    """Product code that deserialises stored data and handles no failure.

    Stored data is the one input a product cannot vouch for. It outlived the
    process that wrote it, and a half-written write, a schema change between
    versions, another tab, a quota error or a user with developer tools can
    each leave it as something the parser will not accept. Every parser named
    in `_DESERIALISES` raises on that input rather than returning a default.

    Measured across the stored workspaces: of 73 product files that parse
    JSON, **17 contain no error handling of any kind**. Two of them read as:

        const stored = getLocalStorage().getItem('tasks');
        return stored ? JSON.parse(stored) : [];

    The ternary guards `null`, which is the case that cannot happen twice, and
    not the case that can - storage holding something that is not JSON. When
    it does, load throws, and a page whose whole state comes from that call
    renders nothing at all.

    Deliberately whole-file, not per-call-site. A file that handles an error
    anywhere is left alone, even if this particular call is bare: the question
    is whether failure was considered, and answering it per call site needs
    the enclosing block, which no regex gets right across six languages. It
    under-reports on purpose - a new check that is wrong costs a sprint, and
    this one has to earn a reviewer's attention 17 times before it spends any.

    Not blocking. The product works; it works until its storage is damaged.
    """
    problems: list[str] = []
    for path in files:
        relative = str(path.relative_to(root))
        if path.suffix.lower() not in _COUNTED_SUFFIXES:
            continue
        if is_test(relative) or not is_application(relative):
            continue
        text = _read(path)
        if not text:
            continue
        parse = _DESERIALISES.search(text)
        if not parse or not _READS_PERSISTED_DATA.search(text):
            continue
        if _HANDLES_AN_ERROR.search(text):
            continue
        line = text[: parse.start()].count("\n") + 1
        problems.append(
            f"{relative} reads stored data and parses it at line {line} with no "
            "error handling anywhere in the file. Stored data outlived the "
            "process that wrote it, so a half-written write, a schema change "
            "between versions or anything a user put there by hand leaves it "
            "as something the parser rejects - and the parser raises rather "
            "than returning a default. A null check does not cover that: null "
            "is the case that cannot happen twice. Wrap the parse, and decide "
            "what the product does with damaged storage - start empty, or say "
            "so - because today it stops loading entirely."
        )
    return problems


#: Checks whose finding is a broken feature whatever their message happens to
#: say, keyed by the function. `_severity_of` grades a *string*, by matching a
#: phrase against `_BREAKS_BEHAVIOUR`, so rewording a message silently
#: downgrades it to "untidy rather than broken - dead rules, unused files. Worth
#: a minor finding, not a blocking one". This file's own comments record that
#: happening three times, and call it "the stale-marker failure this file is
#: most exposed to"; the test that guards it checks every marker matches some
#: message and, as its comment says, "cannot check that every breaking message
#: matches some marker".
#:
#: A floor declared here cannot be lost to an edit of the prose, because it is
#: attached to the check rather than to its words.
#:
#: One run is the fourth instance. `_a_control_group_no_script_operates`
#: found `todo-app/index.html`'s three `data-filter` buttons, reported that they
#: "render, respond to hover and do nothing when clicked", and was graded untidy
#: - the marker is "does nothing when a user", and this message says "do nothing
#: when clicked". `problems_that_break_the_product` therefore returned nothing,
#: so the test round was never told, and the milestone reviewer raised the same
#: thing itself as
#:
#:     [blocking] correctness: Filter functionality is entirely missing despite
#:     UI elements existing. Users see clickable filter buttons that do nothing.
#:
#: three times, until the run hit the revision limit. The harness proved the
#: defect and then talked itself out of it.
#: Keyed on the registry description, which is this registry's own identifier -
#: seven test files assert against these strings, so it is a maintained contract
#: rather than incidental prose. Every check is registered as a lambda, so there
#: is no function name to key on.
#:
#: A rename would drop a floor silently, which is the failure this mechanism
#: exists to end, so `test_every_declared_floor_names_a_real_check` fails loudly
#: instead.
_FLOORS: dict[str, str] = {
    "clickable controls against the scripts that should operate them": "BREAKS",
    # A handler that never runs is a feature that does not work, which is this
    # bucket's own heading. One run's reviewer graded the same finding
    # blocking and the run died on it.
    "delegated handlers against the events that do not bubble to them": "BREAKS",
}

BREAKS_WHATEVER_IT_SAYS = "BREAKS"


def _floor_of(entry: tuple) -> str:
    """The severity a registry entry declares, or "" to grade it by its message."""
    return _FLOORS.get(entry[0], "")


_CHECKS: tuple[tuple[str, Any], ...] = (
    ("names a page calls against the import clause that should bind them",
     lambda files, root, stack, brief: _called_without_being_imported(files, root)),
    ("stored data a product parses without handling a parse failure",
     lambda files, root, stack, brief: _persisted_data_parsed_without_a_guard(files, root)),
    ("required arguments the suite supplies and the product does not",
     lambda files, root, stack, brief: _required_arguments_only_the_tests_supply(files, root)),
    ("actions the run's own acceptance criteria require against what it built",
     lambda files, root, stack, brief: _a_required_action_nothing_implements(files, root, brief)),
    ("clickable controls against the scripts that should operate them",
     lambda files, root, stack, brief: _a_control_group_no_script_operates(files, root)),
    ("delegated handlers against the events that do not bubble to them",
     lambda files, root, stack, brief: _a_delegated_handler_for_an_event_that_does_not_bubble(files, root)),
    ("suites a test file registers more than once",
     lambda files, root, stack, brief: _a_suite_registered_twice(files, root)),
    ("actions the documents require against the tests that should cover them",
     lambda files, root, stack, brief: _a_required_action_no_test_covers(files, root, brief)),
    ("the chosen stack against what is on disk",
     lambda files, root, stack, brief: _stack_conflicts(files, root, stack)),
    ("a responsive criterion against styles that answer to no width",
     lambda files, root, stack, brief: _a_responsive_criterion_nothing_implements(
         files, root, brief)),
    ("responsive stylesheets against the viewport tag that lets them apply",
     lambda files, root, stack, brief: _responsive_css_the_page_cannot_use(files, root)),
    ("test files that cannot fail, never run, or throw before they can",
     lambda files, root, stack, brief: _tests_that_cannot_fail(files, root)),
    ("the installed test runner against the one the stack chose",
     lambda files, root, stack, brief: _a_test_runner_the_stack_did_not_choose(files, root, stack)),
    ("CommonJS behind a module script tag, which no browser can run",
     lambda files, root, stack, brief: _commonjs_loaded_as_a_module(files, root)),
    ("a server against a stack that says the product runs in the browser",
     lambda files, root, stack, brief: _a_server_in_a_browser_only_product(files, root, stack)),
    ("manifests against the project they describe",
     lambda files, root, stack, brief: _manifest_defects(files, root, stack)),
    ("stylesheet id selectors against declared element ids",
     lambda files, root, stack, brief: _dangling_id_selectors(files, root)),
    ("the ids and data attributes scripts reach for against the page",
     lambda files, root, stack, brief: _hooks_javascript_reaches_for(files, root)),
    ("test files against the project's own test command",
     lambda files, root, stack, brief: _tests_the_project_never_runs(files, root)),
    ("node:test suites against a manifest that never invokes node --test",
     lambda files, root, stack, brief: _node_suites_nothing_runs(files, root)),
    ("module syntax against the script tag that loads it",
     lambda files, root, stack, brief: _modules_loaded_as_plain_scripts(files, root)),
    ("paths in package.json scripts against where npm runs them",
     lambda files, root, stack, brief: _manifest_scripts_that_cannot_resolve(files, root)),
    ("exported names against the names any test mentions",
     lambda files, root, stack, brief: _exports_no_test_mentions(files, root)),
    ("stylesheet class selectors against the elements that carry them",
     lambda files, root, stack, brief: _dangling_class_selectors(files, root)),
    ("commands the documents tell a reader to run",
     lambda files, root, stack, brief: _documented_commands_that_cannot_run(files, root, root / "docs")),
    ("HTML script and stylesheet references against the files they name",
     lambda files, root, stack, brief: _broken_local_references(files, root)),
    ("application modules against whatever loads them",
     lambda files, root, stack, brief: _unreferenced_scripts(files, root)),
    ("tests against the module they should be importing",
     lambda files, root, stack, brief: _redefined_instead_of_imported(files, root)),
    ("application code against the page it is embedded in",
     lambda files, root, stack, brief: _application_embedded_in_html(files, root)),
    ("languages against the directory they share",
     lambda files, root, stack, brief: _languages_sharing_a_directory(files, root)),
    ("application modules the page never loads, only the tests",
     lambda files, root, stack, brief: _reached_only_by_its_tests(files, root)),
    ("debugging scripts left behind in the product",
     lambda files, root, stack, brief: _scratch_scripts_left_behind(files, root)),
    ("a page whose controls no script anywhere operates",
     lambda files, root, stack, brief: _a_page_no_script_ever_touches(files, root)),
    ("suite functions called without the import that defines them",
     lambda files, root, stack, brief: _suites_calling_a_global_node_does_not_define(files, root)),
    ("files that contradict the module type their manifest declares",
     lambda files, root, stack, brief: _files_that_contradict_the_declared_module_type(files, root)),
    ("module syntax against a test runner that cannot parse it",
     lambda files, root, stack, brief: _module_system_mismatch(files, root)),
    ("tests against the directory they are run from",
     lambda files, root, stack, brief: _tests_that_depend_on_the_working_directory(files, root)),
    ("the size of the product against the budget its own documents state",
     lambda files, root, stack, brief: _over_the_declared_budget(files, root, _orphans_quietly(files, root))),
    ("presence of Playwright for UI testing",
     lambda files, root, stack, brief: _missing_playwright_for_ui(files, root, stack)),
)

#: Extensions that carry behaviour a browser test could exercise. A page of
#: markup and styling has none.
_CLIENT_LOGIC_SUFFIXES = frozenset({".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"})


def _missing_playwright_for_ui(files: list[Path], root: Path, stack: Any) -> list[str]:
    """A UI with behaviour and no browser test, or [].

    Narrowed on 2026-09-19 after it fired on a fixture of one `<div>` and one
    stylesheet. Three conditions, and each removes a false positive the first
    version produced:

    - there must be **client-side logic**, not merely HTML. A static page has
      no behaviour to regression-test, and demanding a browser harness for it
      is asking for a test with nothing to assert.
    - there must be a **manifest**. With no `package.json` there is no
      JavaScript project yet, so "not installed in package.json" names a file
      that does not exist and the remedy cannot be carried out.
    - the page must actually **load a script**, which is what
      `_a_page_no_script_ever_touches` already reasons about: markup that
      loads nothing has no end-to-end path through a browser.

    Left as a finding rather than dropped, because the case it was written for
    is real - a product whose UI logic is only ever unit-tested has no
    evidence it works in a browser, and `TESTABILITY_RULE` requires one.

    A fourth condition, added after one run: the run's own stack must not
    have chosen a different testing framework. Without it this check and
    `_a_test_runner_the_stack_did_not_choose` contradict each other, and both
    grade BREAKS, so no state of the workspace satisfies both. Demonstrated on
    one project whose stack chose `node --test with JSDOM`:

        without @playwright/test -> "Playwright is not installed ... You MUST
                                     install `@playwright/test`"          BREAKS
        with @playwright/test    -> "installs '@playwright/test', but this run's
                                     stack chose 'node --test with JSDOM'" BREAKS

    One run hit the second horn and failed at the revision limit with

        [major] contracts: @playwright/test is declared as a devDependency in
        todo-app/package.json, but technology_stack.md explicitly chose
        'node --test with JSDOM' as the testing framework.

    while earlier runs hit the first. A reviewer cannot accept either, because
    the remedy for each is the thing the other forbids.

    Resolved towards the run's own decision rather than by muting a severity.
    `stack_selector` chooses the testing framework and writes it to
    `technology_stack.md`, and `_a_test_runner_the_stack_did_not_choose` already
    enforces the project against that choice. Two authorities on one question is
    what produced the loop; this check hard-codes one vendor's tool, which is
    also the narrower thing to be - the harness has to build products in every
    framework and language, and a check that names a product cannot do that.

    So: when the stack has named a testing framework that is not Playwright, the
    choice governs and this stays quiet. When the stack named Playwright, or
    named nothing at all, the finding stands.
    """
    has_html = any(f.suffix == ".html" for f in files)
    if not has_html:
        return []
    if not any(f.suffix.lower() in _CLIENT_LOGIC_SUFFIXES for f in files):
        return []
    if not any(f.name == "package.json" for f in files):
        return []
    chosen = str(getattr(stack, "testing_framework", "") or "").strip().lower()
    if chosen and not re.search(r"(?<![a-z0-9])playwright(?![a-z0-9])", chosen):
        return []

    packages = _manifest_packages(files, "package.json")
    if "playwright" not in packages and "@playwright/test" not in packages:
        return [
            "The product has an HTML UI but Playwright is not installed in package.json. "
            "This BREAKS regression detection. You MUST install `@playwright/test` and use it "
            "to test the UI logic end-to-end. Unit testing the data layer alone with `node --test` "
            "is insufficient for verifying that the application works in the browser."
            + _and_the_brief_bans_dependencies(root)
        ]
    return []


#: A project document ruling out dependencies. Deliberately narrow: it has to
#: be a statement about dependencies, not any sentence with "external" in it.
_NO_DEPENDENCIES = re.compile(
    r"no\s+(?:external\s+|third[-\s]party\s+|runtime\s+)?dependencies"
    r"|without\s+(?:any\s+)?external\s+dependencies"
    r"|zero\s+dependencies",
    re.I,
)


def _and_the_brief_bans_dependencies(root: Path) -> str:
    """The constraint the reviewer has to weigh this finding against, or "".

    The finding above tells a reviewer it MUST install a package. On a brief
    reading "No external dependencies beyond basic HTML/CSS/JS" that is an
    instruction to break a stated constraint, and it arrives with no mention
    that the constraint exists.

    Both of one run's reviewers worked it out for themselves and wrote
    the reasoning into their findings - "While the brief forbids external
    dependencies f..." - and both filed the result as `suggestion`, against a
    finding this file grades as blocking. A check that two consecutive
    reviewers have to overrule is not giving them what they need.

    The answer is not in doubt and the reviewer's own prompt already states
    it: a test-only dependency is not a dependency of the product. Saying so
    here puts it where the finding is read.

    Read from the workspace's own documents, like `_declared_line_budget`,
    because that is where the brief has already been restated as something
    this run committed to.
    """
    for folder in (root / "docs", root):
        if not folder.is_dir():
            continue
        for document in sorted(folder.glob("*.md")):
            try:
                text = _read(document)
            except Exception:  # noqa: BLE001 - an unreadable document bans nothing
                continue
            if _NO_DEPENDENCIES.search(text):
                return (
                    f" This project's documents ({document.name}) rule out external "
                    "dependencies, and that constraint is about the SHIPPED product: "
                    "`@playwright/test` belongs in `devDependencies`, where "
                    "`npm ci --omit=dev` installs none of it and the user receives "
                    "nothing of it. Installing it as a dev dependency breaks no "
                    "constraint here. Putting it in `dependencies` would."
                )
    return ""


def summarise_integration(
    repository_root: str | Path, stack: Any = None, brief: str = ""
) -> str:
    """What the files in this workspace say about each other. Never raises.

    `brief` is the operator's own document, not the run's restatement of it.
    Two checks read it, and they read it because a run that redefines a
    requirement removes it from every document downstream - after which a
    check that reads only those documents agrees with the run. See
    `_actions_the_brief_requires`.
    """
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
        # Each problem is kept with the floor its own check declares, so the
        # bucketing below cannot put a declared-breaking finding under "untidy
        # rather than broken" because of how its sentence happens to read.
        graded_problems: list[tuple[str, str]] = []
        for entry in _CHECKS:
            floor = _floor_of(entry)
            for problem in entry[1](files, root, stack, brief):
                graded_problems.append((problem, floor or _severity_of(problem)))
        problems = [problem for problem, _ in graded_problems]
    except Exception:  # noqa: BLE001
        return "The cross-file checks could not complete on this workspace."

    checked = (
        f"Cross-file checks ran over {len(files)} files: "
        + ", ".join(entry[0] for entry in _CHECKS)
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
    breaking = [p for p, g in graded_problems if g == "BREAKS"]
    criterion = [p for p, g in graded_problems if g == "CRITERION"]
    untidy = [p for p, g in graded_problems if g == "untidy"]
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
    if criterion:
        sections.append(
            f"{len(criterion)} {'is' if len(criterion) == 1 else 'are'} a stated "
            "acceptance criterion this product does not meet. Nothing is broken "
            "and nothing is untidy: the work simply does not match what the "
            "project was asked for, and only a person may decide that no longer "
            "holds:\n"
            + "\n".join(f"- {problem}" for problem in criterion)
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


def problems_that_break_the_product(
    repository_root: str | Path, stack: Any = None, brief: str = ""
) -> list[str]:
    """The `BREAKS` tier of `summarise_integration`, as separate problems.

    `summarise_integration` grades every problem and tells the reviewer, in its
    own words, that each one in this tier "means a feature DOES NOT WORK" and
    "is a blocking finding unless you can show it is not". Then it renders them
    into a paragraph and relies on the reviewer to turn them back into findings.
    Nothing checked that it did.

    Measured on one run. The checks proved three of these, this text
    reached the reviewer, and the reviewer restated one of them in prose while
    recording `findings: []`. An empty `findings` list is what the workflow
    routes on, so none of the three became a task, and the run spent its three
    revisions and failed with the missing stylesheet still missing.

    Returned as a list rather than prose because the caller needs them one at a
    time: a finding is per defect, and a paragraph cannot be turned back into
    one. Never raises - a caller reaching for this is already on an error path.
    """
    try:
        root = Path(repository_root).resolve()
        if not root.is_dir():
            return []
        files = _source_files(root)
        if not files:
            return []
        breaking: list[str] = []
        for entry in _CHECKS:
            found = entry[1](files, root, stack, brief)
            # The floor first. A check that declares itself breaking is breaking
            # however its message is worded, which is the point of declaring it.
            floor = _floor_of(entry)
            for problem in found:
                if floor == "BREAKS" or _severity_of(problem) == "BREAKS":
                    breaking.append(problem)
    except Exception:  # noqa: BLE001 - proof that cannot be gathered is not proof
        return []
    return breaking


__all__ = ["problems_that_break_the_product", "summarise_integration"]
