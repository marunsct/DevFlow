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
from typing import Any, Mapping

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
    #: Where screenshots and other evidence the acceptance run leaves are found.
    evidence_dir: str = ""
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


def _language(stack: Any) -> str:
    text = str(getattr(stack, "language", "") or "").lower()
    if "typescript" in text or re.search(r"(?<![a-z])ts(?![a-z])", text):
        return "typescript"
    if "python" in text:
        return "python"
    if "javascript" in text or re.search(r"(?<![a-z])(?:js|node(?:\.js)?|html|css)(?![a-z])", text):
        return "javascript"
    return text.strip()


def _framework_text(stack: Any) -> str:
    parts = [
        str(getattr(stack, "framework", "") or ""),
        str(getattr(stack, "frontend_framework", "") or ""),
    ]
    return " ".join(parts).lower()


_BACKEND_FRAMEWORKS = re.compile(
    r"\b(?:express|fastify|koa|hapi|nest(?:js)?|fastapi|flask|django|starlette|"
    r"sinatra|rails|gin|echo|fiber|actix|axum|rocket|spring|laravel|aspnet|asp\.net)\b"
)
_FRONTEND_FRAMEWORKS = re.compile(
    r"\b(?:react|vue|svelte|angular|solid|preact|lit|vite|html|css|dom|browser|"
    r"vanilla js|vanilla javascript)\b"
)
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
    words = set(re.findall(r"[a-z0-9.#+-]+", text))
    if any(word in words or word in text for word in pack.frameworks):
        return True
    # Only words that are not a framework at all ("javascript", "html5",
    # "node.js") remain: the stack chose the language and nothing on top.
    return not (_BACKEND_FRAMEWORKS.search(text) or re.search(
        r"\b(?:react|vue|svelte|angular|solid|preact|lit|click|typer|commander|yargs|nest)\b", text
    ))


def choose_pack(stack: Any, text: str = "") -> StackPack | None:
    """The pack for this stack and brief, or None when no pack fits.

    A pack fits when it is for this kind of product, in the stack's language,
    and implements the framework the stack chose (or the stack chose none).
    """
    from app.stacks.packs import ALL_PACKS

    kind = product_kind(stack, text)
    if not kind:
        return None
    language = _language(stack)
    for pack in ALL_PACKS:
        if pack.kind != kind:
            continue
        if pack.language != language:
            continue
        if _framework_fits(pack, stack):
            return pack
    return None


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
