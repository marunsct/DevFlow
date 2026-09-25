"""The brief's own technical constraints, for the stage that chooses the stack.

Run 0c5aabdb chose `Express` with `JSON File Storage` for a brief whose
Technical Constraints section reads, in full:

    - Single-page application
    - No external dependencies beyond basic HTML/CSS/JS

Its rationale argued for `node --test` because it "does not add external
packages", in the same paragraph that added Express. The technical lead then
delegated "Create package.json ... add minimal dependencies: express", and the
backend specialist built a server, all of it correct work downstream of a
decision that had already contradicted the brief.

Nothing in the workflow was wrong except what the stage could see.
`stack_selector_node` is given `product_intake` and `tools_models` - both
derived - and `ProductManagerOutput.constraints` came back empty, as it may:
the field exists and the model simply did not fill it. The brief itself was
never in the room when the stack was chosen.

So the constraints travel separately, taken from the document rather than from
a model's summary of it, and they are short: a handful of lines that would
otherwise be paraphrased away.

Nothing here decides anything. It selects text and hands it over, because a
constraint the deciding stage never reads cannot be honoured by any prompt
written for it. `app.analysis.integration_checks` catches what is built
against a stack; this is about the stack itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: Headings whose body states what the product may and may not be built with.
#: Matched on the heading text, so any level of `#` and any trailing colon.
_CONSTRAINT_HEADINGS = (
    "technical constraints",
    "constraints",
    "non-functional requirements",
    "technical requirements",
    "out of scope",
    "restrictions",
    "limitations",
)

#: A markdown heading, with its level and its text.
_HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*:?\s*$", re.M)

#: Lines that state a restriction even outside a constraints heading. Kept
#: narrow deliberately: a sentence about what the product must NOT use is the
#: one a stack decision can contradict, and anything broader sweeps in the
#: feature list.
_A_RESTRICTION = re.compile(
    r"""^\s*[-*]?\s*([^\n]*\b(?:no|without|avoid|must not|do not|don't|"""
    r"""zero|none|only|single|plain|vanilla)\b[^\n]*"""
    r"""\b(?:dependenc|framework|librar|package|server|backend|build|"""
    r"""bundler|database|tooling|npm|install|runtime)[^\n]*)$""",
    re.M | re.I,
)

#: How much to carry. The point is the constraints, not the brief.
MAX_CONSTRAINT_LINES = 12


def _section_under(text: str, heading: re.Match[str]) -> str:
    """The body below `heading`, ending at the next heading of the same level."""
    level = len(heading.group(1))
    start = heading.end()
    for following in _HEADING.finditer(text, start):
        if len(following.group(1)) <= level:
            return text[start : following.start()]
    return text[start:]


def constraint_lines(document_text: str) -> list[str]:
    """The brief's technical constraints, as the lines that state them.

    Sections first, because a brief that has a constraints heading has said
    where they are. The loose pattern then adds restrictions stated elsewhere -
    run 0c5aabdb's brief also says "Single-page application" under a heading
    this would find, but other briefs bury the same thing in an overview.
    """
    if not document_text:
        return []

    found: list[str] = []
    seen: set[str] = set()

    def keep(line: str) -> None:
        cleaned = line.strip().lstrip("-*").strip()
        if not cleaned or len(cleaned) > 300:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(cleaned)

    for heading in _HEADING.finditer(document_text):
        if heading.group(2).strip().lower().rstrip(":") not in _CONSTRAINT_HEADINGS:
            continue
        for line in _section_under(document_text, heading).splitlines():
            keep(line)

    for match in _A_RESTRICTION.finditer(document_text):
        keep(match.group(1))

    return found[:MAX_CONSTRAINT_LINES]


#: What to do about a conflict, which differs by who is reading. The stage
#: choosing picks again; the stage reviewing blocks. A single sentence telling
#: a reviewer to "pick the one it leaves" would be telling it to do the job of
#: the stage it is reviewing.
_REMEDY = {
    "choosing": (
        "If a constraint rules out the technology you would otherwise pick, "
        "pick the one it leaves."
    ),
    "reviewing": (
        "A specification that contradicts one of these is a blocking finding, "
        "however well argued it is - say which constraint and require the "
        "change. You are the last gate before anything is built."
    ),
}


def constraints_note(document_text: str, reader: str = "choosing") -> str:
    """The constraints as a block for a prompt, or "" when the brief states none.

    `reader` is "choosing" for the stage picking the stack and "reviewing" for
    the one reviewing what it produced; it selects the closing sentence only.
    """
    lines = constraint_lines(document_text)
    if not lines:
        return ""
    body = "\n".join(f"- {line}" for line in lines)
    return (
        "--- Technical constraints, quoted from the brief ---\n"
        f"{body}\n\n"
        "These are the author's words, not a summary of them. A decision that "
        "contradicts one of these is the wrong decision however good it would "
        "otherwise be: every later stage builds what it allows, and none of "
        f"them reads the brief again. {_REMEDY.get(reader, _REMEDY['choosing'])}\n\n"
    )




#: Phrases that mean the product is meant to be opened in a browser. Narrow
#: deliberately: this drives a blocking finding, and a brief that never says
#: any of these must produce none.
_WANTS_A_PAGE = (
    "html",
    "web-based interface",
    "web interface",
    "single-page",
    "single page application",
    "in the browser",
    "modern browsers",
    "web page",
    "webpage",
    "front-end",
    "frontend",
)

#: And that it is meant to be styled.
_WANTS_STYLING = ("css", "responsive", "styling", "stylesheet")


#: A brief saying the product may not bring packages with it. Narrow: this
#: drives a blocking finding, so a brief that merely prefers something light
#: must produce none.
_FORBIDS_DEPENDENCIES = (
    "no external dependencies",
    "no dependencies",
    "without external dependencies",
    "without dependencies",
    "no third-party",
    "no libraries",
    "no frameworks",
    "zero dependencies",
)

#: Packages that are the runtime itself rather than something fetched.
_NOT_A_DEPENDENCY = frozenset({"node", "npm"})


_IMPORTS_A_PACKAGE = re.compile(
    r"""(?:import\s[^;]*?\sfrom\s*|import\s*\(\s*|require\(\s*)['"]([^'"]+)['"]"""
)
_A_PACKAGE_NAME = re.compile(r"""^@?[a-z0-9][\w.-]*(?:/[\w.-]+)*$""")
_NODE_BUILTIN = frozenset(
    """assert async_hooks buffer child_process cluster console constants crypto
    dgram diagnostics_channel dns domain events fs http http2 https inspector
    module net os path perf_hooks process punycode querystring readline repl
    stream string_decoder sys timers tls trace_events tty url util v8 vm wasi
    worker_threads zlib test""".split()
)
_A_SCRIPT = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")


def _packages_the_code_imports(project: Path) -> set[str]:
    """Every package name the scripts under `project` import.

    A bare specifier that is not a Node builtin is a dependency whether or not
    anything declared it - which is how run 9bd3a091 imported `jsdom` into
    three test files under an empty `devDependencies`, a full `node_modules`
    and a lockfile of thirty-nine packages.
    """
    imported: set[str] = set()
    for script in project.rglob("*"):
        if script.suffix not in _A_SCRIPT or "node_modules" in script.parts:
            continue
        try:
            source = script.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for specifier in _IMPORTS_A_PACKAGE.findall(source):
            if specifier.startswith((".", "/", "#")) or "//" in specifier:
                continue
            if specifier.startswith("node:") or not _A_PACKAGE_NAME.match(specifier):
                continue
            name = (
                "/".join(specifier.split("/")[:2])
                if specifier.startswith("@")
                else specifier.split("/")[0]
            )
            if name not in _NODE_BUILTIN:
                imported.add(name)
    return imported


def _imported_only_by_tests(project: Path, package: str) -> bool:
    """Whether `package` is imported only by files this project owns as tests.

    A test runner or browser binary imported by a test file is test tooling, so
    the constraint on the product's dependencies has nothing to say about it.
    The same package imported by the application itself is a product dependency
    and is reported. `file_kinds.is_test` is the one answer to "is this a test"
    across the codebase - see that module for why it must not be re-derived.

    A test framework's own configuration file counts as test tooling as well.
    `playwright.config.ts` is the one that imports `@playwright/test`, and
    `file_kinds` classifies it as `config` rather than `test` - correctly, it is
    not a test - so a check that asked only `is_test` saw the runner's config as
    product code and reported the package as a shipped dependency. Measured on
    json declares
    @playwright/test, violating the brief" as BLOCKING and ended the run, three
    remediation rounds later, over a devDependency that ships to nobody. The
    config belongs to the suite, not the product: nothing in `dependencies`
    pulls it in, and `npm ci --omit=dev` never installs it.
    """
    from app.analysis.file_kinds import classify_file, is_test

    try:
        for script in project.rglob("*"):
            if script.suffix not in _A_SCRIPT or "node_modules" in script.parts:
                continue
            relative = str(script.relative_to(project))
            if is_test(relative):
                continue
            if classify_file(relative) == "config":
                # A test framework's config is part of the suite it configures.
                continue
            try:
                source = script.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if package in _IMPORTS_A_PACKAGE.findall(source):
                return False
    except Exception:  # noqa: BLE001 - a check must never fail the review
        return False
    return True


def what_the_brief_forbids_that_is_there(
    document_text: str, repository_root: str | Path
) -> list[str]:
    """Dependencies the brief rules out and the product declares anyway.

    `what_the_brief_asked_for_that_is_missing` checks one direction - the
    brief asks for a page, the product has none. Nothing checked the other,
    and it is the direction run 0c5aabdb failed in: a brief reading "No
    external dependencies beyond basic HTML/CSS/JS" against a product built on
    Express with a 32KB lockfile.

    Run 551640d3 is the same thing in a quieter form. It installed `jsdom` to
    get a DOM for its tests - a reasonable engineering instinct, and exactly
    what the brief forbids - leaving a full `node_modules` and a 29KB
    lockfile. Nothing reported it: the cross-file checks look at how files
    relate, not at what the brief allows, and the missing-things check has
    nothing to say about a thing that is present.

    Across the stored workspaces 11 of 55 declare dependencies, among them
    jsdom, jest, express and node-fetch.

    Decidable, so it is stated rather than left to a reading: the constraint is
    a quoted line of the brief and the packages are `package.json`'s own.

    Only the product's dependencies are reported. `devDependencies` are not
    shipped - `npm ci --omit=dev` in a production image installs none of them -
    so a test runner sitting there breaks no constraint, and a package imported
    only by test files is treated the same way.  The
    constraint was never aimed at the test suite; this check no longer reads it
    as though it were. See `app.agents.testing_dependency_rule`.
    """
    if not document_text:
        return []
    quoted = " ".join(constraint_lines(document_text)).lower() + " " + document_text.lower()
    if not any(phrase in quoted for phrase in _FORBIDS_DEPENDENCIES):
        return []

    found: list[str] = []
    try:
        root = Path(repository_root)
        for manifest in sorted(root.rglob("package.json")):
            if "node_modules" in manifest.parts:
                continue
            try:
                declared = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            # The brief constrains what ships, and only that. `devDependencies`
            # are the developer's: they are not installed by `npm ci --omit=dev`
            # in a production image and never reach the user, so a test runner
            # spent all three remediation attempts on `@playwright/test` in
            # devDependencies against a brief reading "No external dependencies
            # beyond basic HTML/CSS/JS" and failed without a product defect.
            # See `app.agents.testing_dependency_rule`.
            shipped = sorted(
                set(declared.get("dependencies") or {})
                - set(declared.get("devDependencies") or {})
            )
            dev_only = sorted(
                set(declared.get("devDependencies") or {})
                - set(declared.get("dependencies") or {})
            )
            imported = _packages_the_code_imports(manifest.parent)
            # Test tooling: declared as a devDependency AND never touched by
            # product code. It ships to nobody, so the constraint on the
            # product has nothing to say about it.
            test_only = {
                name
                for name in dev_only
                if name not in _NOT_A_DEPENDENCY
                and _imported_only_by_tests(manifest.parent, name)
            }
            packages = [
                name
                for name in shipped
                if name not in _NOT_A_DEPENDENCY
            ]
            # A devDependency the product itself imports is a product dependency
            # filed in the wrong place: the product needs it at runtime, so the
            # brief rules it out - and `npm ci --omit=dev` would break it too.
            misfiled = [
                name
                for name in dev_only
                if name not in test_only and name not in _NOT_A_DEPENDENCY
            ]
            packages = packages + misfiled
            undeclared = sorted(
                imported
                - set(shipped)
                - set(dev_only)
                - _NOT_A_DEPENDENCY
            )
            if not packages and not undeclared and not test_only:
                continue
            how = []
            if packages:
                how.append("declares " + ", ".join(f"`{name}`" for name in packages[:6]))
            if undeclared:
                # Not declaring it does not make it not a dependency. It makes
                # it a dependency `npm ci` will not install, so the tests that
                # import it fail for a second reason on any other machine.
                how.append(
                    "imports " + ", ".join(f"`{name}`" for name in undeclared[:6])
                    + " without declaring it"
                )
            if not how:
                # Everything present is test-only and declared as such, which
                # is exactly what the constraint asks for. Say so rather than
                # falling silent, so a reviewer reading the note knows the
                # check ran and the product itself carries no dependencies.
                how.append(
                    "declares no product dependencies; "
                    + ", ".join(f"`{name}`" for name in sorted(test_only)[:6])
                    + " are devDependencies used for testing only and are not shipped"
                )
            found.append(
                f"{manifest.parent.name}/package.json "
                + " and ".join(how)
                + ". The brief rules that out in its own words, quoted above. "
                "Whatever it was needed for, the product the brief describes "
                "does not have it, and a reviewer cannot accept the milestone "
                "as meeting the brief while the product needs it."
            )
    except Exception:  # noqa: BLE001 - evidence that cannot be gathered says nothing
        return found
    return found


def what_the_brief_asked_for_that_is_missing(
    document_text: str, project_files: list[str]
) -> list[str]:
    """Requirements the brief states plainly that the product does not have.

    Run 0c5aabdb completed. Its architecture review returned "approved" with no
    findings, both security reviews "passed", and the milestone review raised
    one blocking finding - a missing npm test script - then "accepted". What it
    delivered was:

        simple-to-do-list-app/index.js            616 bytes, an Express server
        simple-to-do-list-app/app.test.js
        simple-to-do-list-app/index.test.js
        simple-to-do-list-app/package-lock.json   32,693 bytes

    No HTML. No CSS. No front-end JavaScript. The brief's first requirement is
    "Simple web-based interface with HTML/CSS/JavaScript" and its constraints
    are "Single-page application" and "No external dependencies beyond basic
    HTML/CSS/JS".

    Every gate passed because every gate reviews the artifacts against each
    other and against the milestone's own goal. The brief enters at the product
    manager and is never read again, so nothing in the run was in a position to
    notice that the product it accepted has no user interface.

    Only the two requirements that can be checked without judgement: a brief
    that asks for a page, and a product with no page in it; a brief that asks
    for styling, and nothing that styles. Everything else about "does this meet
    the brief" is a reading, and belongs to the reviewer that now gets the text.
    """
    low = (document_text or "").lower()
    names = [name.lower() for name in project_files]
    missing: list[str] = []

    if any(phrase in low for phrase in _WANTS_A_PAGE):
        if not any(name.endswith((".html", ".htm")) for name in names):
            missing.append(
                "The brief asks for a web interface, and the product contains no "
                "HTML file. There is nothing for a user to open. Whatever else "
                "works, the product described has not been built."
            )
        elif any(phrase in low for phrase in _WANTS_STYLING) and not any(
            name.endswith(".css") for name in names
        ):
            missing.append(
                "The brief asks for styling, and the product contains no "
                "stylesheet. Check that the page carries its own `<style>`; if "
                "it does not, the interface is unstyled."
            )
    return missing


__all__ = [
    "MAX_CONSTRAINT_LINES",
    "constraint_lines",
    "constraints_note",
    "what_the_brief_asked_for_that_is_missing",
    "what_the_brief_forbids_that_is_there",
]
