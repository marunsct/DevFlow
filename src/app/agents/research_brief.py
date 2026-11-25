"""The reading a specification needs, done before the frontier model is asked to write it.

Measured on one run: the specification stage spent 70 minutes of a frontier
model, most of it reasoning 5,000 to 15,000 tokens before each documentation
read or registry lookup - 2 to 5 minutes to decide which page to read next.
Handing those turns to the build model one at a time did not help: the build
model kept starting on the answer instead.

So the harness does the reading first. It looks every library of the chosen
stack up in its registry itself, asks the build model once which
documentation topics the specification will need, reads those pages itself,
and hands everything to the architect in its request. The architect is then
offered no documentation or registry lookups (`app.tools.research.researched`):
its reasoning goes on the specification.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

#: Documentation pages read before the architect writes.
MOST_TOPICS = 10
#: Characters kept of one page.
MOST_PAGE_CHARACTERS = 3_000
#: Libraries looked up in their registries.
MOST_LIBRARIES = 12

_NOT_A_LIBRARY = re.compile(
    r"^(?:none|n/?a|-|vanilla.*|plain.*|native.*|built-?in.*|html.*|css.*|localstorage|no .*)$", re.I
)
#: Runtimes, languages and package managers: named in a stack, never a package to look up.
_RUNTIMES = {
    "node", "node.js", "nodejs", "deno", "bun", "python", "python3", "cpython", "typescript", "javascript",
    "ecmascript", "npm", "pnpm", "yarn", "pip", "poetry", "uv", "go", "golang", "rust", "cargo", "java",
    "jvm", "kotlin", "ruby", "php", "dotnet", ".net", "c#", "swift", "sql",
}
#: What a package's name can look like in any registry: `hono`, `@hono/node-server`, `better-sqlite3`.
_A_PACKAGE_NAME = re.compile(r"^(?:@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*$", re.I)
#: A file (`package.json`), a built-in module (`node:test`), or an option (`--watch`).
_NOT_A_PACKAGE = re.compile(r"\.(?:json|md|ts|js|mjs|cjs|py|toml|ya?ml|txt|lock)$|:|^-|^v?\d", re.I)
#: A segment between commas of more words than this is a sentence about the stack, not a name.
MOST_WORDS_IN_A_NAME = 4
#: Words of a build or a sentence that are also package names in a registry.
_GENERIC_WORDS = {
    "build", "run", "test", "tests", "start", "dev", "serve", "watch", "lint", "format", "scripts", "script",
    "already", "only", "both", "layers", "app", "server", "client", "api", "cli", "compiler", "runner",
    "adapter", "module", "modules", "library", "framework", "tooling", "tools", "config", "entrypoint",
}
_SCOPED_NAME = re.compile(r"@[a-z0-9][\w.-]*/[\w.-]*[\w-]", re.I)


def libraries_of(stack: Any) -> list[str]:
    """The libraries the chosen stack names, each once, in the order the stack gives them."""
    if stack is None:
        return []
    named: list[str] = []
    for field in ("framework", "frontend_framework", "database", "testing_framework"):
        named.append(str(getattr(stack, field, "") or ""))
    named.extend(str(item) for item in getattr(stack, "additional_tools", None) or [])
    found: list[str] = []
    pieces: list[str] = []
    for entry in named:
        # "Hono (on @hono/node-server)": the name, and the one in brackets.
        pieces.append(re.sub(r"\(.*?\)", " ", entry))
        pieces.extend(re.findall(r"\((.*?)\)", entry))
        # Names written as code or scoped, wherever they stand in a sentence.
        pieces.extend(re.findall(r"`([^`]+)`", entry))
        pieces.extend(_SCOPED_NAME.findall(entry))
    for entry in pieces:
        # A sentence about the stack split on its connectives left its words
        # as names: one run looked up `already`, `build` and `pairs`.
        for segment in re.split(r"\s*(?:,|;|\+|\s[-\u2014]\s)\s*", entry):
            if len(segment.split()) > MOST_WORDS_IN_A_NAME:
                continue
            for part in re.split(r"\s*(?:\band\b|\bwith\b|\bon\b|\bvia\b|\bfor\b)\s*", segment):
                name = part.strip().strip(".`")
                name = re.sub(r"\s+v?\d[\w.]*$", "", name).strip()
                if " " in name or not _A_PACKAGE_NAME.match(name) or _NOT_A_PACKAGE.search(name):
                    continue
                if name.lower() in _RUNTIMES or name.lower() in _GENERIC_WORDS:
                    continue
                if name and not _NOT_A_LIBRARY.match(name) and name.lower() not in (f.lower() for f in found):
                    found.append(name)
    return found[:MOST_LIBRARIES]


def _topics(libraries: list[str], brief: str, model: Any) -> list[tuple[str, str]]:
    """(library, topic) pairs the specification will need, asked of `model` once."""
    from langchain_core.messages import HumanMessage

    fallback = [(name, "getting started and core API") for name in libraries][:MOST_TOPICS]
    if model is None or not libraries:
        return fallback
    request = (
        "A software product is about to be specified. Its brief and its chosen libraries are below. "
        f"Name the documentation topics (at most {MOST_TOPICS}) its specification needs to get right: "
        "the exact calls, options and behaviours the product depends on.\n\n"
        f"Libraries: {', '.join(libraries)}\n\n--- Brief ---\n{brief[:6000]}\n\n"
        'Reply with one JSON object and nothing else: {"topics": [{"library": "<one of the libraries>", '
        '"topic": "<a few words>"}]}'
    )
    try:
        from app.observability.direct_calls import config_for_this_run

        reply = model.invoke([HumanMessage(content=request)], **config_for_this_run("research_brief"))
        from app.models.reply_text import reply_text

        text = reply_text(reply)
        match = re.search(r"\{.*\}", text, re.S)
        parsed = json.loads(match.group(0)) if match else {}
        known = {name.lower(): name for name in libraries}
        pairs = [
            (known[str(item.get("library", "")).lower()], str(item.get("topic") or "").strip())
            for item in parsed.get("topics") or []
            if isinstance(item, dict) and str(item.get("library", "")).lower() in known and item.get("topic")
        ]
        return pairs[:MOST_TOPICS] or fallback
    except Exception:  # noqa: BLE001 - each library's own overview instead
        logger.info("The build model could not name the documentation topics; reading each library's overview")
        return fallback


#: A line that is page furniture, not documentation: markup alone, a badge, a link alone, a rule, a comment.
_FURNITURE = re.compile(
    r"^\s*(?:</?[a-z][^>]*>\s*)+$"                      # markup alone: `<p align="center">`, `<a ...><img ...></a>`
    r"|^\s*(?:\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)\s*)+$"   # badges alone
    r"|^\s*(?:\*\*[^*]+\*\*:?\s*)?\[[^\]]*\]\([^)]*\)\s*$"  # a link alone, or `**Documentation**: [url](url)`
    r"|^\s*(?:-{3,}|\*{3,}|_{3,})\s*$"                   # a rule
    r"|^\s*<!--.*-->\s*$",
    re.I)
#: A badge or markup inside a line of text, kept as the text.
_BADGE = re.compile(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
_TAG = re.compile(r"</?[a-z][^>]*>", re.I)
#: A heading over what is not the library's documentation: its sponsors, backers, contributors, licence, community.
_NOT_DOCUMENTATION = re.compile(r"^(#{1,6})\s+.*\b(?:sponsors?|backers?|contributors?|licen[cs]e|community|"
                                r"support us|donat\w*|star history)\b", re.I)
_A_HEADING = re.compile(r"^(#{1,6})\s")


def without_page_furniture(text: str) -> str:
    """A documentation page as its documentation: markup, badges, lone links, rules and sponsor sections left out
    (LF.1471). Measured on one medium run: the architect's evidence was 19,354 characters in all 17 of its calls -
    a README's "Gold Sponsors" list, logo and badge markup, "Join Discord" - beside the version table it was asked
    to cite. Code blocks are kept as they are."""
    out: list[str] = []
    skipping_below: int | None = None
    in_code = False
    for line in str(text or "").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            if skipping_below is None:
                out.append(line)
            continue
        if in_code:
            if skipping_below is None:
                out.append(line)
            continue
        heading = _A_HEADING.match(line)
        if heading and skipping_below is not None and len(heading.group(1)) <= skipping_below:
            skipping_below = None
        if skipping_below is not None:
            continue
        if _NOT_DOCUMENTATION.match(line):
            skipping_below = len(_A_HEADING.match(line).group(1))
            continue
        if _FURNITURE.match(line):
            continue
        cleaned = _TAG.sub("", _BADGE.sub("", line)).rstrip()
        if line.strip() and not cleaned.strip():
            continue
        if not cleaned.strip() and out and not out[-1].strip():
            continue
        out.append(cleaned)
    return "\n".join(out).strip()


#: The most of one library's page kept under `DOCUMENTATION_EXCERPTS_BOUNDED`, in characters.
MOST_BOUNDED_CHARACTERS = 1_200
#: How a bounded page says so: the firing signal of `DOCUMENTATION_EXCERPTS_BOUNDED`.
BOUNDED_SAID = "the passages of its page that bear on the brief"
_A_TERM = re.compile(r"[a-z][a-z0-9_]{4,}")


class _BoundedExcerpts:
    """`DOCUMENTATION_EXCERPTS_BOUNDED` as the switch registry reads one: off in code until measured (LF.1471).

    Doubtful: it changes what the architect knows of each library, so it is measured on the specification review's
    findings before it is trusted."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("The documentation excerpts the architect is handed beside the version table keep, for each "
                   "library, only the passages of its page that use a word of the brief or of the topic read, at most "
                   f"{MOST_BOUNDED_CHARACTERS:,} characters a library. Measured on one medium run: 19,354 characters "
                   "of landing pages in each of the architect's 17 calls.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("DOCUMENTATION_EXCERPTS_BOUNDED", _BoundedExcerpts.ON_BY_DEFAULT)


bounded_excerpts_switch = _BoundedExcerpts()


def bounded(page: str, terms: set[str], most: int = MOST_BOUNDED_CHARACTERS) -> str:
    """`page`'s passages (paragraphs and code blocks, in order) that use one of `terms`, within `most`; "" for none."""
    passages: list[str] = []
    current: list[str] = []
    in_code = False
    for line in str(page or "").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        if not in_code and not line.strip() and not line.lstrip().startswith("```"):
            if current:
                passages.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        passages.append("\n".join(current))
    kept: list[str] = []
    used = 0
    for passage in passages:
        if not set(_A_TERM.findall(passage.lower())) & terms:
            continue
        if used + len(passage) > most:
            continue
        kept.append(passage)
        used += len(passage) + 2
    return "\n\n".join(kept)


def research_notes(stack: Any, brief: str, model: Any, *, workers: int = 6, root: Any = None) -> str:
    """The registry versions and documentation the specification needs, as text for its request; "" if nothing was found.

    `root`: the workspace, where the stack facts are written (`app.stacks.stack_facts`, HK.1); their lines - each
    library's release this toolchain runs, its date and whether it was withdrawn - replace the registry's raw answers.
    """
    from app.stacks import stack_facts
    from app.tools import docs, package_registry

    libraries = libraries_of(stack)
    if not libraries:
        return ""
    ecosystem = package_registry.ecosystem_named(str(getattr(stack, "language", "") or "")) or ""
    looked_up: list[str] = []
    read: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        if package_registry.enabled() and ecosystem:
            for name, answer in zip(libraries, pool.map(lambda n: _safely(package_registry.look_up, ecosystem, n), libraries)):
                if isinstance(answer, dict) and answer and "error" not in answer:
                    looked_up.append(f"- {name}: " + ", ".join(
                        f"{key}: {value}" for key, value in answer.items() if key not in ("description",)
                    )[:400])
        if docs.enabled():
            # Only libraries the registry knows, when it was asked: one run
            # read six topics for `Node.js`, each trying three spellings of a
            # README that does not exist.
            known = [name for name in libraries if any(line.startswith(f"- {name}:") for line in looked_up)]
            topics = _topics(known if package_registry.enabled() and ecosystem and looked_up else libraries, brief, model)
            pages = pool.map(lambda pair: _safely(docs.read, pair[0], pair[1], ecosystem), topics)
            for (name, topic), answer in zip(topics, pages):
                excerpt = without_page_furniture(
                    str((answer or {}).get("excerpt") or "") if isinstance(answer, dict) else "")
                if excerpt.strip() and bounded_excerpts_switch.enabled():
                    # Only what bears on the brief and the topic read (`DOCUMENTATION_EXCERPTS_BOUNDED`, LF.1471).
                    excerpt = bounded(excerpt, set(_A_TERM.findall(f"{brief} {topic}".lower())))
                    if excerpt:
                        read.append(f"### {name}: {topic} ({BOUNDED_SAID})\n{excerpt}")
                elif excerpt.strip():
                    read.append(f"### {name}: {topic}\n{excerpt[:MOST_PAGE_CHARACTERS].strip()}")
    if not looked_up and not read:
        return ""
    logger.info("Research done before the architect: %d package(s) looked up, %d page(s) read", len(looked_up), len(read))
    facts = stack_facts.library_lines(root, stack, libraries) if looked_up else ""
    # Each library's release, support window, open advisories and fit as one table (HK.8, `app.stacks.stack_evidence`).
    from app.stacks.stack_evidence import for_the_architect

    evidence = for_the_architect(root, stack)
    return "\n\n".join(part for part in (
        "--- Research done for this stage: current registry releases and documentation excerpts ---\n"
        "Read for you before this stage, from the registries and the libraries' own documentation. "
        "Write from it; documentation and registry lookups are not offered in this stage.",
        facts or (("Registry releases:\n" + "\n".join(looked_up)) if looked_up else ""),
        evidence,
        "\n\n".join(read),
    ) if part) + "\n"


def _safely(function: Any, *args: Any) -> Any:
    try:
        return function(*args)
    except Exception as error:  # noqa: BLE001 - one page that cannot be read leaves the rest
        return {"error": str(error)}
