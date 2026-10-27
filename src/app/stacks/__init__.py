"""Stack packs: everything specific to one kind of product in one language.

The harness has to build products of every kind in every language, and the
part of building one that differs between them is narrow: how a project is laid
out, how it installs, how its unit tests and its acceptance tests run, where the
runners write their reports, and how a test drives the product - a browser for a
page, HTTP for a service, a process for a command-line tool, an import for a
library. A pack holds exactly that, so the workflow around it knows no language.

Why a pack scaffolds instead of the model
-----------------------------------------
On 46 measured runs 63% of reported defects concerned tests and their setup:
mixed runners, module flags, pages opened from disk, ports, a runner installed
and never used. None of that is the product, and none of it needs judgement. A
pack writes a layout known to work, installs it and runs its own smoke tests
before any agent writes a line, so a run starts from a project whose tests
already run.

A product no pack fits is still built: the run continues without a scaffold, as
every run did before packs existed, and its acceptance suite declares its own
command (see `app.acceptance.suite`). Adding a kind of product is adding a pack.

Language- and framework-specific content belongs in a pack or in
`app.plugins.seed`, never in the workflow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

#: The kinds of product a pack can be for.
KINDS = ("browser_app", "http_api", "fullstack", "cli", "library")

#: What each kind means, for the stack selector's prompt and the pack chooser.
KIND_MEANINGS = {
    "browser_app": "a user interface that runs in a web browser, with no server of its own beyond serving its files",
    "http_api": "a service other programs call over HTTP",
    "fullstack": "a browser user interface backed by the product's own HTTP service",
    "cli": "a program a user runs from a terminal",
    "library": "code other programs import and call",
}


@dataclass(frozen=True)
class StackPack:
    """One kind of product in one language, ready to build on.

    `files` are written relative to the project directory, with `{{project}}`,
    `{{title}}` and `{{package}}` filled in. `install`, `unit_test` and
    `acceptance_test` are argv lists run in the project directory; the two test
    commands write JUnit XML to `unit_report` and `acceptance_report`.

    `kept_files` are runner configuration the harness puts back if a stage
    changes them, and `kept_scripts` the manifest scripts it puts back: the
    commands the harness itself runs must keep meaning what they meant.

    `smoke_files` prove the scaffold works - one unit test and one acceptance
    test - and are removed once they pass, so no product ships a test that
    asserts nothing about it.
    """

    name: str
    title: str
    kind: str
    language: str
    #: Words in the chosen framework that this pack implements. A stack whose
    #: framework names none of these (and is not one of `NO_FRAMEWORK`) is not
    #: this pack's.
    frameworks: tuple[str, ...]
    files: Mapping[str, str]
    install: tuple[tuple[str, ...], ...]
    unit_test: tuple[str, ...]
    acceptance_test: tuple[str, ...]
    unit_report: str
    acceptance_report: str
    unit_dir: str
    acceptance_dir: str
    #: Glob for acceptance test files inside `acceptance_dir`.
    acceptance_pattern: str
    #: Glob for unit test files inside `unit_dir`.
    unit_pattern: str
    kept_files: tuple[str, ...]
    kept_scripts: Mapping[str, str]
    smoke_files: Mapping[str, str]
    #: How tests are written for this pack. Shown to every stage that writes one.
    guide: str
    #: How an acceptance test drives this kind of product. Shown to the QA stage.
    acceptance_guide: str
    #: The technology stack this pack is, field by field.
    stack: Mapping[str, str]
    #: Families of cross-file checks that apply (see `integration_checks`).
    check_families: frozenset[str] = field(default_factory=frozenset)
    #: Every name a unit test file of this pack's runners takes, beyond
    #: `unit_pattern`: pytest collects `*_test.py` too, and a fullstack pack's
    #: one unit command runs the page's runner and the service's. Read by the
    #: check that unit tests name the served code (`scaffold`, Initiative AO.10).
    unit_test_names: tuple[str, ...] = ()
    #: Files a unit test reaches the code through without naming it in the
    #: test itself: pytest's `conftest.py` fixtures.
    test_helpers: tuple[str, ...] = ()
    #: Where screenshots and other evidence the acceptance run leaves are found.
    evidence_dir: str = ""
    #: The command that type-checks the project without writing anything, run in the project directory; () when
    #: there is none. Read when the product does not start (`compiler_errors`).
    typecheck: tuple[str, ...] = ()
    #: The file the drafted service's routes or handlers live in, which the
    #: scaffold writes as a stub. While it is still byte-identical to that
    #: stub, nothing the run drafted is wired into the service the acceptance
    #: suite runs against - the dominant live failure, measured as 31 of 35
    #: locked tests failing against the stub (Initiative K.3; see
    #: `scaffold.entrypoint_is_still_the_stub`). "" when the pack's server is
    #: harness-owned or it serves nothing: there is no stub to outgrow.
    entrypoint: str = ""
    #: More files the scaffold writes as stubs that the drafted product must
    #: replace - a fullstack pack's page component and its service's app
    #: module. Measured on one run: the drafted app went into `frontend/` and
    #: `backend/app/`, the served page stayed the scaffold's `src/App.tsx`, and
    #: every page test failed its first control while 13 fixers chased criteria.
    entrypoints: tuple[str, ...] = ()
    #: Names an entry file of the scaffold must keep exporting, by file relative to the project: the pack's own
    #: smoke test and start file import them (`app.stacks.entry_exports`).
    required_exports: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: ".ts" for a pack whose TypeScript Node runs as it is: the harness adds the extension to a relative import that
    #: lacks it (`app.stacks.import_extensions`). "" for every other pack.
    relative_import_extension: str = ""
    #: Whether the product's code reaches its modules only through imports, so
    #: a source file under an entrypoint's folder that no import reaches is
    #: code the product never runs (`app.analysis.reachability`). Off for a
    #: framework that loads modules by where they sit or by name - file-system
    #: routes, autoloading, settings strings - where that would accuse code
    #: the framework runs.
    wired_by_imports: bool = False
    #: Where the product's data lives as the tests run it, said to the architect
    #: before the scaffold exists. Measured live: told the files and not the
    #: data, it planned a server's column types and search for a product every
    #: test runs on the file database. "" when the pack keeps no data.
    data_store: str = ""
    #: What a failure looks like when the test's own code broke, rather than
    #: the product being unbuilt or wrong - for this pack's runner. Before
    #: anything is built every test fails; only these failures are the test's.
    test_bugs: tuple[str, ...] = ()
    #: Where an acceptance run leaves a JSON list of what the product itself
    #: reported going wrong (a page's uncaught errors), relative to the
    #: project; "" when the pack records none.
    runtime_report: str = ""
    #: Patterns of locators that find a control by something no person sees (a
    #: placeholder, a test id). An acceptance suite using one is sent back.
    locators_nobody_sees: tuple[str, ...] = ()
    #: Patterns of locators that call methods the runner does not define (e.g. Testing Library
    #: methods like getByLabelText on Playwright). Sent back before locking and reopened once built.
    locators_that_do_not_exist: tuple[str, ...] = ()
    #: Patterns of actions on whichever of several matching controls comes
    #: first, which let a page showing one control twice pass. Sent back too.
    locators_that_pick_one: tuple[str, ...] = ()
    #: Patterns of a role found by a name it never takes from what it shows,
    #: which matches nothing on a right page. Sent back, and reopened once built.
    locators_by_a_missing_name: tuple[str, ...] = ()
    #: Patterns, with `{name}` for a regex-escaped name, of a test finding a
    #: control by that name. Every control the brief names must be found so.
    finds_by_name: tuple[str, ...] = ()
    #: A suite file's text -> (line, locator, text) where a test finds something
    #: by a text and asserts that it does not show that text.
    contradicting_locators: Callable[[str], Sequence[tuple[int, str, str]]] | None = None
    #: A failed test's message -> (old text, new text) when it failed on a
    #: locator found by a text the page it failed on no longer shows.
    locator_left_behind: Callable[[str], tuple[str, str] | None] | None = None
    #: A suite file's text -> (line, title) of each test that acts on the page
    #: with nothing that opens it; it can never pass.
    opens_no_page: Callable[[str], Sequence[tuple[int, str]]] | None = None
    #: A suite file's text -> (line, storage_name, context) where storage is accessed
    #: before the page is opened; it throws a browser SecurityError on about:blank.
    storage_before_page_open: Callable[[str], Sequence[tuple[int, str, str]]] | None = None
    #: (project root, suite file, its text) -> (line, why) where the file uses a
    #: module system its runtime will not load it as; it fails before any test runs.
    module_system_mismatch: Callable[[Path, Path, str], Sequence[tuple[int, str]]] | None = None
    #: A suite file's text -> (line, helper) where one of its async helpers is
    #: used without being awaited.
    unawaited_helpers: Callable[[str], Sequence[tuple[int, str]]] | None = None
    #: A suite file's text -> lines that pass a locator an option it ignores, so
    #: it matches more than the test means.
    locators_with_an_ignored_option: Callable[[str], Sequence[int]] | None = None
    #: A suite file's text -> (line, title, value) of each test that looks on
    #: the page for a value it made at run time and never gave the product.
    expects_what_it_never_gave: Callable[[str], Sequence[tuple[int, str, str]]] | None = None
    #: A suite file's text -> (line, title, positions) of each test that asserts
    #: what two or more places of a list show: an order.
    positions_it_asserts: Callable[[str], Sequence[tuple[int, str, Sequence[str]]]] | None = None
    #: A failed test's message -> the text it filtered by, when the page it
    #: failed on shows that text only as a field's value.
    filtered_by_a_field_value: Callable[[str], str | None] | None = None
    #: (project root, evidence dir) -> test name -> what the product showed
    #: when that test failed, read from the runner's own failure context.
    failure_pages: Callable[[Path, str], Mapping[str, str]] | None = None
    #: (failure message, the page it failed on) -> what on the page the failed
    #: locator nearly matched, or "".
    near_misses: Callable[[str, str], str] | None = None
    #: ([(test name, failure message, page it failed on)], the page as it first
    #: loads) -> test name -> why that locked test waits for something only data
    #: brings, having created none.
    needs_what_it_never_made: (
        Callable[[Sequence[tuple[str, str, str]], str], Mapping[str, str]] | None
    ) = None
    #: project root -> every assertion name the installed test runner defines;
    #: an acceptance test calling any other can never pass.
    assertion_names: Callable[[Path], frozenset[str]] | None = None
    #: Where the product's own code runs - "browser", "node" or "both" - which
    #: decides the globals the language service lets it use. See
    #: `app.analysis.language_service`.
    code_runs_in: str = "both"
    #: Where the unit tests' browser globals come from - a file or setting the
    #: harness keeps - or "" when unit tests run without a page. Where there is
    #: one, a test that builds its own DOM replaces it halfway and is told so.
    unit_dom: str = ""
    #: CI steps before the pack's install command (YAML list items): the
    #: language runtime. See `app.stacks.release`.
    ci_setup: tuple[str, ...] = ()
    #: Commands a CI runner needs after the install and before the tests, which
    #: the harness's own image already has (a browser build).
    ci_prepare: tuple[str, ...] = ()
    #: Files a release adds beside the product, relative to the project
    #: directory - for a service, how to run it in a container. Never written
    #: over a file the product already has.
    release_files: Mapping[str, str] = field(default_factory=dict)
    #: Words naming the component framework the pack's interface is built with
    #: (React, Vue ...), for a pack with a browser interface; empty for one in
    #: plain HTML, CSS and JavaScript. A stack naming a component framework
    #: fits only a pack built with that one: "Vue on Vite" fitted the React
    #: pack, which names Vite too.
    frontend_frameworks: tuple[str, ...] = ()
    #: The data limit each process of this toolchain needs, as the sandbox's
    #: SANDBOX_MEMORY_LIMIT is written ("2g"), or "" for what every pack gets.
    #: The limit counts what a runtime reserves, not only what it uses: the
    #: Angular CLI used 550 MB at most in one process and could not start a
    #: thread under 1.5 GB. The command's whole tree stays bounded by its real
    #: use (`sandbox._run_and_watch_the_tree`).
    process_memory: str = ""
    #: How long the pack's acceptance suite waits for the product's server to answer, in milliseconds; 0 when
    #: unknown. One acceptance file's run is given longer (`sandbox.timeout_for`), so the runner, not the
    #: sandbox's limit, is what says the server never came up.
    server_wait_ms: int = 0
    #: A command, run in the project, that prints the routes the application serves, one `METHOD /path` a line; empty
    #: when the pack has none. The start probe adds them when the readiness route is not served (a router mounted
    #: under its own path once served `/health/health`).
    list_routes: tuple[str, ...] = ()


    @property
    def probe_runner(self) -> str:
        """The runner the release's interface-contract checks go through ("playwright"), or "" for none.

        Declared by what the pack ships rather than named in the checks' own
        module, so a new kind of pack declares its runner here and the checks
        stay free of any one tool (Initiative AO.10, AU).
        """
        return "playwright" if "playwright.config.js" in self.files else ""

    @property
    def coverage(self) -> tuple[str, ...]:
        """What the harness checks for a product on this pack, from the pack's own data (Initiative AW).

        Derived, not written by hand: a pack that gains a runner, an entrypoint
        or a page report says so here without anyone remembering to.
        """
        found = [
            f"unit tests: `{self.unit_pattern}` in `{self.unit_dir}/`, run by the pack's command",
            f"acceptance tests: `{self.acceptance_pattern}` in `{self.acceptance_dir}/`, locked before building",
        ]
        if self.runtime_report:
            found.append("errors the page reports while it loads")
        if self.kind in {"browser_app", "fullstack"} and self.evidence_dir:
            found.append("the page in a browser, with screenshots kept as evidence")
        stubs = [e for e in (self.entrypoint, *self.entrypoints) if e]
        if stubs:
            found.append("that the served code is the run's own, not the scaffold's stub (" + ", ".join(f"`{e}`" for e in stubs) + ")")
        if self.language in {"javascript", "typescript", "python"}:
            found.append("imports against the packages the manifests declare")
        if self.probe_runner:
            found.append(f"the architect's interface contract, probed through {self.probe_runner}")
        return tuple(found)

    def render(self, project: str, title: str, package: str | None = None) -> dict[str, str]:
        """The scaffold's files with this project's names filled in."""
        return _filled(self.files, project, title, package)

    def render_release_files(self, project: str, title: str, package: str | None = None) -> dict[str, str]:
        """The release's files with this project's names filled in."""
        return _filled(self.release_files, project, title, package)

    def rendered_smoke_files(self, project: str, title: str, package: str | None = None) -> dict[str, str]:
        """The smoke tests with this project's names filled in."""
        return _filled(self.smoke_files, project, title, package)

    def filled(self, text: str, project: str, title: str = "", package: str | None = None) -> str:
        """`text` (a guide, say) with this project's names filled in."""
        return _filled({"": text}, project, title, package)[""]

    def commands(self, project: str, package: str | None = None) -> dict[str, Any]:
        """The commands as stored in the workspace, with the package name filled in."""
        package = package or python_package_name(project)

        def fill(argv: tuple[str, ...]) -> list[str]:
            return [part.replace("{{package}}", package) for part in argv]

        return {
            "install": [fill(argv) for argv in self.install],
            "unit_test": fill(self.unit_test),
            "acceptance_test": fill(self.acceptance_test),
        }


def _filled(
    files: Mapping[str, str], project: str, title: str, package: str | None = None
) -> dict[str, str]:
    values = {"project": project, "title": title or project, "package": package or python_package_name(project)}

    def fill(text: str) -> str:
        return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), text)

    return {fill(path): fill(content) for path, content in files.items()}


#: A framework field that says "nothing in particular".
NO_FRAMEWORK = frozenset({
    "", "none", "n/a", "na", "no framework", "vanilla", "plain", "native",
    "standard library", "stdlib", "built-in", "builtin",
})


def python_package_name(project: str) -> str:
    """A valid Python package name for a project directory name."""
    name = re.sub(r"[^0-9a-zA-Z]+", "_", project).strip("_").lower() or "app"
    if name[0].isdigit():
        name = f"app_{name}"
    return name


#: How a brief names the module a user runs or imports: `python -m wordstats`,
#: `import textkit`, "a package named `textkit`".
_A_STATED_MODULE = (
    re.compile(r"python3?\s+-m\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"`import\s+([A-Za-z_][A-Za-z0-9_]*)`"),
    re.compile(r"(?:package|module)\s+(?:named|called)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", re.I),
)


def stated_module(text: str) -> str | None:
    """The importable name the brief gives the product, when it gives one.

    A brief that says users run `python -m wordstats` has fixed the package's
    name, whatever the project directory is called; a scaffold named after the
    directory would ship a product its own brief cannot run.
    """
    for pattern in _A_STATED_MODULE:
        match = pattern.search(text or "")
        if match and match.group(1).isidentifier():
            return match.group(1)
    return None


#: How a stack's language field names each language a pack can be in.
_LANGUAGE_NAMES = {
    "typescript": re.compile(r"typescript|(?<![a-z])ts(?![a-z])"),
    "javascript": re.compile(r"javascript|(?<![a-z])(?:js|node(?:\.js)?|html|css)(?![a-z])"),
    "python": re.compile(r"python"),
    "go": re.compile(r"(?<![a-z])(?:go|golang)(?![a-z])"),
    "java": re.compile(r"(?<![a-z])java(?![a-z])"),
    "kotlin": re.compile(r"kotlin"),
    "csharp": re.compile(r"c#|c sharp|csharp|\.net|dotnet"),
    "rust": re.compile(r"(?<![a-z])rust(?![a-z])"),
    "ruby": re.compile(r"(?<![a-z])ruby(?![a-z])"),
    "php": re.compile(r"(?<![a-z])php(?![a-z])"),
}

#: The languages a framework is written in, for a stack whose language field
#: names only one side of it: "Python", with React chosen for the interface.
_WRITTEN_IN = {
    ("react", "preact", "vue", "svelte", "solid", "lit", "express", "fastify", "koa", "hapi",
     "next", "nextjs", "nuxt", "sveltekit", "remix"): ("javascript", "typescript"),
    ("angular", "nest", "nestjs"): ("typescript",),
    ("fastapi", "flask", "django", "starlette"): ("python",),
    ("gin", "fiber", "chi"): ("go",),
    ("spring",): ("java", "kotlin"),
    ("ktor",): ("kotlin",),
    ("aspnet", "asp.net"): ("csharp",),
    ("actix", "axum", "rocket"): ("rust",),
    ("rails", "sinatra"): ("ruby",),
    ("laravel", "symfony", "slim"): ("php",),
}


def _languages(stack: Any) -> set[str]:
    """Every language the stack is written in: named in its language field, or by its frameworks.

    A full-stack product is written in two. Read as one - the first named,
    TypeScript before Python - a Python service with a React page matched no
    pack whose language was the service's.
    """
    text = str(getattr(stack, "language", "") or "").lower()
    found = {name for name, pattern in _LANGUAGE_NAMES.items() if pattern.search(text)}
    frameworks = _framework_text(stack)
    for words, languages in _WRITTEN_IN.items():
        if any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", frameworks) for word in words):
            found.update(languages)
    return found


def _framework_text(stack: Any) -> str:
    parts = [
        str(getattr(stack, "framework", "") or ""),
        str(getattr(stack, "frontend_framework", "") or ""),
    ]
    return " ".join(parts).lower()


_BACKEND_FRAMEWORKS = re.compile(
    r"\b(?:express|fastify|koa|hapi|nest(?:js)?|adonis|fastapi|flask|django|starlette|tornado|"
    r"sinatra|rails|hanami|roda|grape|gin|echo|fiber|chi|beego|actix|axum|rocket|warp|"
    r"spring|quarkus|micronaut|javalin|dropwizard|vert\.?x|ktor|play|"
    r"laravel|symfony|slim|lumen|codeigniter|cakephp|yii|phoenix|aspnet|asp\.net)\b"
)
_FRONTEND_FRAMEWORKS = re.compile(
    r"\b(?:react|vue|svelte|angular|solid|preact|lit|vite|html|css|dom|browser|"
    r"vanilla js|vanilla javascript)\b"
)
#: Frameworks that are a page and its own service in one application.
_FULLSTACK_FRAMEWORKS = re.compile(r"\b(?:next(?:\.?js)?|nuxt(?:\.?js)?|svelte ?kit|remix)\b")
#: The component framework each of those builds its page with.
_BUILT_ON = {"next": "react", "nextjs": "react", "remix": "react", "nuxt": "vue", "sveltekit": "svelte", "svelte kit": "svelte"}

_CLI_FRAMEWORKS = re.compile(r"\b(?:click|typer|argparse|commander|yargs|oclif|cobra|clap)\b")

_SAYS_BROWSER = re.compile(
    r"\b(?:web ?page|web ?app(?:lication)?|website|single[- ]page|browser|front[- ]?end|"
    r"responsive|mobile and desktop|html)\b",
    re.I,
)
_SAYS_API = re.compile(
    r"\b(?:rest(?:ful)?\b|api\b|endpoints?\b|http service|web service|json over http|"
    r"micro-?service|backend service)",
    re.I,
)
_SAYS_CLI = re.compile(
    r"\b(?:command[- ]line|cli\b|terminal command|run from (?:a|the) terminal|shell command)",
    re.I,
)
_SAYS_LIBRARY = re.compile(
    r"\b(?:library|sdk\b|importable|package (?:that|which) (?:exposes|provides)|"
    r"public (?:api|functions?) (?:that|for))",
    re.I,
)


def product_kind(stack: Any, text: str = "") -> str:
    """Which kind of product this is: one of `KINDS`, or "" when nothing says.

    The stack's own field wins when it names a kind. Otherwise the frameworks
    the stack chose decide - a backend framework is a service, a frontend one a
    page, both a full-stack product - and the brief's words decide only when the
    stack named neither.
    """
    stated = str(getattr(stack, "product_kind", "") or "").strip().lower().replace("-", "_")
    if stated in KINDS:
        return stated
    frameworks = _framework_text(stack)
    if _FULLSTACK_FRAMEWORKS.search(frameworks):
        return "fullstack"
    frontend = str(getattr(stack, "frontend_framework", "") or "").strip().lower()
    has_frontend = bool(_FRONTEND_FRAMEWORKS.search(frameworks)) or (
        frontend not in NO_FRAMEWORK and bool(frontend)
    )
    has_backend = bool(_BACKEND_FRAMEWORKS.search(frameworks))
    if has_backend and (has_frontend or _SAYS_BROWSER.search(text)):
        return "fullstack"
    if has_backend:
        return "http_api"
    if _CLI_FRAMEWORKS.search(frameworks):
        return "cli"
    if has_frontend:
        return "browser_app"
    says = {
        "browser_app": bool(_SAYS_BROWSER.search(text)),
        "http_api": bool(_SAYS_API.search(text)),
        "cli": bool(_SAYS_CLI.search(text)),
        "library": bool(_SAYS_LIBRARY.search(text)),
    }
    if says["browser_app"] and says["http_api"]:
        return "fullstack"
    for kind in ("browser_app", "http_api", "cli", "library"):
        if says[kind]:
            return kind
    return ""


#: Words in a framework field that name no framework: languages, runtimes,
#: versions and filler.
_NOT_A_FRAMEWORK = re.compile(
    r"(?:javascript|typescript|js|ts|node|node\.?js|nodejs|ecmascript|es\d*\+?|esm|commonjs|"
    r"html5?|css3?|python3?|cpython|go|golang|java|jdk|jvm|kotlin|c#|csharp|\.net|dotnet|rust|"
    r"ruby|php|v?\d+(?:\.\d+)*(?:\+|\.x)?|lts|latest|"
    r"none|n/a|na|no|vanilla|plain|native|pure|standard|library|stdlib|std|built-in|builtin|core|"
    r"runtime|only|framework|frameworks|with|and|on|the|its|own|of|for|a|an|"
    r"http|https|net/http|server|web|api|rest|module|modules|package|packages|"
    r"[-+/.#]+)"
)


def _framework_fits(pack: StackPack, stack: Any) -> bool:
    """Whether the frameworks the stack chose are ones this pack implements."""
    text = _framework_text(stack)
    named = [
        part.strip()
        for part in re.split(r"[,;/+]| and | with ", text)
        if part.strip() and part.strip() not in NO_FRAMEWORK
    ]
    if not named:
        return True
    # A scoped package names its framework by its scope: "@hono/node-server"
    # is Hono's, and the "node" in it is not the pack's "node".
    text = re.sub(r"@([a-z0-9._-]+)/[a-z0-9._-]+", r"\1", text)
    words = set(re.findall(r"[a-z0-9.#+-]+", text))
    # Only a name of the pack's own counts as the stack choosing it. A
    # runtime or language the pack lists ("node", "http", "go") is shared by
    # every framework on it: measured on one run, "Hono 4 served by
    # @hono/node-server" fitted the Express pack because "node" was found
    # inside it, and the run was set up on Express against a brief that
    # required Hono.
    if any(
        re.search(rf"(?<![a-z0-9-]){re.escape(name)}(?![a-z0-9-])", text)
        for name in pack.frameworks
        if not _NOT_A_FRAMEWORK.fullmatch(name)
    ):
        return True
    # The stack chose the language and nothing on top only when every word
    # left is a language, a runtime or filler ("javascript", "html5",
    # "node.js built-in http module"). A word that is none of those names a
    # framework - one this harness may never have heard of: Hono read as "no
    # framework" and was given the Nest pack, because only frameworks on a
    # list were recognised as frameworks.
    return all(_NOT_A_FRAMEWORK.fullmatch(word) for word in words)


def choose_pack(stack: Any, text: str = "", rationale: str = "") -> StackPack | None:
    """The pack for this stack and brief (see `_pack_that_fits`), or its measured arm when that arm is switched on."""
    pack = _pack_that_fits(stack, text, rationale)
    if pack is not None and pack.name == "node-hono-api":
        from app.stacks.packs.node_hono_native_api import enabled

        # A measured arm (owner 2026-10-25): Hono run by Node itself, with node:test, for weaker models.
        if enabled():
            return pack_named("node-hono-native-api") or pack
    return pack


def _pack_that_fits(stack: Any, text: str = "", rationale: str = "") -> StackPack | None:
    """The pack for this stack and brief, or None when no pack fits.

    A pack fits when it is for this kind of product, in the stack's language,
    and implements the framework the stack chose (or the stack chose none).

    `rationale` is the stack selector's own reasoning. Where the stack's
    fields fit no pack and the rationale names exactly one offered pack by its
    title - of this kind and language, implementing what the stack did name -
    that pack is the one chosen: the field left out was an omission, not a
    choice. Measured on one run: the rationale chose "Browser app in React
    with its own HTTP service in FastAPI" and the frontend field read "not
    stated", so no pack fitted and the agents set the project up themselves.
    """
    from app.stacks.packs import ALL_PACKS

    kind = product_kind(stack, text)
    if not kind:
        return None
    languages = _languages(stack)
    for pack in ALL_PACKS:
        if pack.kind != kind:
            continue
        if pack.language not in languages:
            continue
        if _framework_fits(pack, stack) and _frontend_fits(pack, stack):
            return pack
    named = [
        pack for pack in ALL_PACKS
        if rationale and pack.title.lower() in rationale.lower()
        and pack.kind == kind
        and pack.language in languages
        and _framework_fits(pack, stack)
        and (not pack.frontend_frameworks or _frontend_fits(pack, stack) or not _names_a_frontend(stack))
    ]
    return named[0] if len(named) == 1 else None


def _names_a_frontend(stack: Any) -> bool:
    """Whether the stack names any component framework at all."""
    frontend = re.sub(r"\.?js\b", "", _framework_text(stack))
    return any(re.search(rf"(?<![a-z]){word}(?![a-z])", frontend) for word in _COMPONENT_FRAMEWORKS) or any(
        re.search(rf"(?<![a-z]){re.escape(framework)}(?![a-z])", frontend) for framework in _BUILT_ON
    )


#: Component frameworks an interface is built with. A stack names at most one.
_COMPONENT_FRAMEWORKS = ("react", "preact", "vue", "svelte", "angular", "solid", "lit")


def _frontend_fits(pack: StackPack, stack: Any) -> bool:
    """Whether the pack's interface is built with the component framework the stack chose.

    Only for a pack with a browser interface. A stack that names a component
    framework fits only a pack built with that one; a stack that names none
    fits only a pack in plain HTML, CSS and JavaScript.
    """
    if pack.kind not in {"browser_app", "fullstack"}:
        return True
    frontend = " ".join([
        str(getattr(stack, "frontend_framework", "") or ""),
        str(getattr(stack, "framework", "") or ""),
    ]).lower()
    # "React.js", "Vue.js", "AngularJS" name the framework too.
    frontend = re.sub(rf"(?<![a-z])({'|'.join(_COMPONENT_FRAMEWORKS)})\.?js(?![a-z])", r"\1", frontend)
    named = {word for word in _COMPONENT_FRAMEWORKS if re.search(rf"(?<![a-z]){word}(?![a-z])", frontend)}
    named.update(
        built_on for framework, built_on in _BUILT_ON.items()
        if re.search(rf"(?<![a-z]){re.escape(framework)}(?![a-z])", frontend.replace(".js", ""))
    )
    if not pack.frontend_frameworks:
        return not named
    return bool(named) and any(word in pack.frontend_frameworks for word in named)


#: What a run on a stack can promise, by whether a pack fits it. Stated in the
#: run's stack decision so the handoff is read for what it is: a pack's
#: scaffold, commands and release files are known and tested; a stack no pack
#: fits is set up and tested by the agents' own commands, with nothing packaged.
PACK_SUPPORTED = "pack-supported"
CUSTOM_STACK = "custom stack"


def support_tier(pack: StackPack | None) -> str:
    """The support tier, with what it means, for a run on `pack` (None: no pack fits)."""
    if pack is not None:
        return (
            f"Support tier: {PACK_SUPPORTED} - the {pack.name} pack's scaffold, install and "
            "test commands, and release files (CI pipeline, and a container definition for "
            "a service). What the harness checks on it: " + "; ".join(pack.coverage) + "."
        )
    return (
        f"Support tier: {CUSTOM_STACK} - no pack fits, so a setup stage creates the project "
        "with the framework's own generator and declares its test commands; the harness "
        "proves them with a smoke test of each before building starts (or, if they cannot "
        "be proven, leaves the setup to the agents), and the release carries no packaged CI "
        "or container files."
    )


def pack_named(name: str | None) -> StackPack | None:
    from app.stacks.packs import ALL_PACKS

    for pack in ALL_PACKS:
        if pack.name == name:
            return pack
    return None


def supported_stacks_note() -> str:
    """The stacks a pack exists for, for the stack selector to prefer."""
    from app.stacks.packs import ALL_PACKS

    lines = [
        f"- {pack.title}: language {pack.stack.get('language')}, framework "
        f"{pack.stack.get('framework')}"
        + (f", frontend {pack.stack['frontend_framework']}" if pack.stack.get("frontend_framework") else "")
        + f", testing {pack.stack.get('testing_framework')}"
        for pack in ALL_PACKS
    ]
    return (
        "--- Stacks this environment scaffolds, with tests that already run ---\n"
        "Choose one of these unless the brief requires something else; a stack not on "
        "this list is still built, but its project setup and test runners are left to "
        "the agents, which is slower and less reliable:\n"
        + "\n".join(lines)
        + "\nSet `product_kind` to one of: "
        + ", ".join(f"{kind} ({KIND_MEANINGS[kind]})" for kind in KINDS)
        + ".\n\n"
    )


def aligned_stack(stack: Any, pack: StackPack) -> Any:
    """The stack with the fields the pack decides set to the pack's values.

    The pack is what will be built and tested, so the stack document must say
    the same thing - otherwise reviews read one stack and the workspace holds
    another. Language and database stay the stack's: a pack does not choose
    the database.
    """
    updates = {
        key: value
        for key, value in pack.stack.items()
        if key in {"framework", "frontend_framework", "testing_framework"} and hasattr(stack, key)
    }
    if hasattr(stack, "product_kind"):
        updates["product_kind"] = pack.kind
    try:
        return stack.model_copy(update=updates)
    except AttributeError:
        return stack
