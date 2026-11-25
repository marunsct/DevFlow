"""The project held in memory and handed to a stage, instead of read call by call.

Measured on one run: 204 `read_file` calls, 55 listings and 37 searches,
most of them a stage finding again what an earlier one had read - the
specification, the sprint plan, the product's own files. Each is a model turn
carrying the whole conversation, and for a local model one in ten was
malformed. The harness already holds every one of those files.

So a stage is handed them at its start: the workflow's documents first - the
specification, the sprint plan, the acceptance criteria, the intake, the stack
- then the project's files, the ones its request names first, product before
tests, up to a share of its model's window (`MEMORY_SHARE`). What does not
fit is named, to be read when needed.

Always current. Each file is kept with its modification time and size, and
both are checked on every use: a file changed by a write tool, by a command a
stage ran, or by the harness is read again before it is handed on; one that
was deleted is dropped. Nothing has to remember to update it.

A read of a file the memory already handed over, unchanged, is answered with
a pointer to it rather than the same text a second time.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

logger = logging.getLogger(__name__)

#: How a read of a file the memory holds is answered; `settled_answer` counts it.
HELD_POINTER = "is in the project memory at the start of this conversation"

#: A window of a held file this many lines or fewer is read from the file: the
#: memory holds its text without line numbers, and a line an error names cannot
#: be found in it. Measured on one run: a testing stage was told "line 146" by a
#: SyntaxError, asked for lines 135-195, was pointed at the memory, and spent
#: three attempts of forty calls without making its fix.
MOST_WINDOW_LINES = 80
#: Said in a pointer, so the way to the numbered lines is known.
NUMBERED_LINES = (
    f"If you need its line numbers - for a line an error names - read just those lines with `offset` and "
    f"`limit`, up to {MOST_WINDOW_LINES} of them: those are read from the file. "
)

#: The last sentence of a pointer: a second one ends the stage's reading (Initiative BC).
POINTER_ENDS_READING = (
    "A second read the memory answers ends reading for this stage: make your change or give your answer."
)

#: The share of a model's window the memory may take.
MEMORY_SHARE = 0.3
#: The most it takes on any model, in characters.
MOST_CHARACTERS = 240_000
#: A file larger than this is named, not handed over.
LARGEST_FILE_CHARACTERS = 60_000
#: Characters per token, as the context budget counts them.
CHARS_PER_TOKEN = 3

#: The workflow's documents, most useful first; any other is after these.
DOCUMENT_ORDER = (
    "docs/technical_specification.md", "docs/sprint_plan.md", "docs/acceptance_criteria.md",
    "docs/acceptance_tests.md", "docs/milestone_plan.md", "docs/product_intake.md",
    "docs/technology_stack.md",
)
#: Documents that are records of the run rather than inputs to its work.
_RECORDS = re.compile(r"^docs/(?:decision_log|.*_summary|stage_summaries/|architecture_review|tools_and_models)")
_TEXT_SUFFIXES = (
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env.example", ".sh",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".py", ".go", ".rs", ".java", ".kt", ".cs",
    ".rb", ".php", ".swift", ".html", ".css", ".scss", ".vue", ".svelte", ".sql", ".graphql",
)
#: Build and configuration files known by their suffix or whole name. The
#: snapshot showed them; with it gone under the memory (LF.188), a Go, Java,
#: .NET, Ruby or PHP project's `go.mod`, `pom.xml`, `.csproj`, `Gemfile` or
#: `phpunit.xml` was neither held nor named as left out.
_BUILD_SUFFIXES = (".xml", ".properties", ".csproj", ".fsproj", ".sln", ".ru", ".gradle", ".kts", ".mod", ".lock.json")
_BUILD_NAMES = {"Gemfile", "Rakefile", "artisan", "Dockerfile", "Makefile", "Procfile", "Pipfile", "go.work"}
_SKIPPED_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "go.sum", "Gemfile.lock",
                  "composer.lock", "packages.lock.json"}

_LOCK = threading.Lock()
#: (root, relative path) -> (modification time, size, content).
_FILES: dict[tuple[str, str], tuple[int, int, str]] = {}


def _ignored(parts: tuple[str, ...]) -> bool:
    from app.tools.repository import IGNORED_DIRECTORIES

    return any(part in IGNORED_DIRECTORIES or part in (".harness", ".agent-home", "test-results")
               or part.endswith((".egg-info", ".dist-info")) for part in parts)


#: Code the harness saved from a command line (`agent_toolkit`): it stays in the transcript, in the call that ran it.
_A_COMMAND_LINE_S_CODE = re.compile(r"^tmp-inline-[0-9a-f]{8}\.\w+$")


def _candidates(root: Path) -> list[str]:
    from app.analysis.integration_checks import _HARNESS_BOOKKEEPING
    from app.stacks.languages import is_generated

    found: list[str] = []
    for folder, directories, files in os.walk(root):
        relative_folder = Path(folder).relative_to(root)
        directories[:] = [d for d in directories
                          if not _ignored((*relative_folder.parts, d)) and not is_generated(d, files)]
        for name in files:
            if (name in _SKIPPED_NAMES or name in _HARNESS_BOOKKEEPING or name.startswith(".project-")
                    or _A_COMMAND_LINE_S_CODE.match(name)) or not (
                name.endswith(_TEXT_SUFFIXES) or name.endswith(_BUILD_SUFFIXES) or name in _BUILD_NAMES
            ):
                continue
            found.append((relative_folder / name).as_posix())
    return found


def current(repo_root: str | Path) -> dict[str, str]:
    """Every text file of the workspace as it is now, by workspace-relative path."""
    root = Path(repo_root)
    if not root.is_dir():
        return {}
    key = str(root.resolve())
    files: dict[str, str] = {}
    present = set()
    for relative in _candidates(root):
        path = root / relative
        try:
            stat = path.stat()
        except OSError:
            continue
        present.add(relative)
        with _LOCK:
            held = _FILES.get((key, relative))
        if held and held[0] == stat.st_mtime_ns and held[1] == stat.st_size:
            files[relative] = held[2]
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        with _LOCK:
            _FILES[(key, relative)] = (stat.st_mtime_ns, stat.st_size, text)
        files[relative] = text
    with _LOCK:
        for gone in [k for k in _FILES if k[0] == key and k[1] not in present]:
            _FILES.pop(gone, None)
    return files


def _ranked(files: dict[str, str], focus: str, unserved: tuple[str, ...] = ()) -> list[str]:
    from app.agents.canonical_memory import enabled as canonical_order
    from app.analysis.file_kinds import classify_file

    # The order no request changes, under `CANONICAL_MEMORY` (plan PX.3).
    canonical = canonical_order()

    def rank(path: str) -> tuple[int, int, str]:
        name = path.rsplit("/", 1)[-1]
        named = not canonical and (path in focus or (len(name) > 4 and name in focus))
        if named and not path.startswith("docs/"):
            return (-1, 0, path)
        # A copy nothing serves comes after everything that is the product, so
        # a limited memory holds the served files first (Initiative AQ).
        if any(path.startswith(folder + "/") for folder in unserved):
            return (4, 1, path)
        if path in DOCUMENT_ORDER:
            return (0, DOCUMENT_ORDER.index(path), path)
        if path.startswith("docs/"):
            return (5 if _RECORDS.match(path) else 3, 0, path)
        kind = classify_file(path)
        return (2 if kind in ("application", "config") else 4, 0, path)

    return sorted(files, key=rank)


_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_MEASURE = re.compile(r"\b(?:AC|TC|ADR|DR|SM)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")
_WORD = re.compile(r"[a-z][a-z0-9_]{3,}")


def digest_of(text: str, focus: str, budget: int) -> str:
    """`text`'s heading outline with line numbers, then its sections that `focus` points at, within `budget`.

    Measured on one run: a 205 KB specification was over the size a file may
    be held whole, so it was never in memory, and the most-read document of
    the run was read in windows 18 times. A section scores by the criterion
    and record ids (`AC-3`, `TC-AC-3-01`) it shares with the request, then by
    the words of its heading the request uses.
    """
    if budget <= 0:
        return ""
    lines = text.splitlines()
    starts = [(index, match.group(2)) for index, line in enumerate(lines) if (match := _HEADING.match(line))]
    if not starts:
        return ""
    sections = [
        (heading, start, (starts[n + 1][0] if n + 1 < len(starts) else len(lines)))
        for n, (start, heading) in enumerate(starts)
    ]
    outline = "\n".join(f"- lines {start + 1}-{end}: {heading}" for heading, start, end in sections[:300])
    wanted_ids = set(_MEASURE.findall(focus))
    wanted_words = set(_WORD.findall(focus.lower()))

    def score(section: tuple[str, int, int]) -> int:
        heading, start, end = section
        body = "\n".join(lines[start:end])
        return 5 * len(wanted_ids & set(_MEASURE.findall(body))) + len(wanted_words & set(_WORD.findall(heading.lower())))

    room = budget - len(outline) - 200
    chosen: list[tuple[int, int, str]] = []
    for section in sorted(sections, key=score, reverse=True):
        if score(section) <= 0 or room <= 0:
            break
        heading, start, end = section
        body = "\n".join(lines[start:end]).rstrip()
        if len(body) > room:
            body = body[:room].rsplit("\n", 1)[0] + "\n[... the rest of this section: read it by line]"
        chosen.append((start, end, body))
        room -= len(body) + 40
    shown = "\n\n".join(f"[lines {start + 1}-{end}]\n{body}" for start, end, body in sorted(chosen))
    return f"Outline:\n{outline}" + (f"\n\nSections this request points at:\n{shown}" if shown else "")


#: A line that defines something, in the languages the packs cover.
_DEFINES = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:pub(?:\([a-z]+\))?\s+)?(?:async\s+)?"
    r"(?:function\*?|class|interface|type|enum|struct|trait|def|func|fn|module|impl|"
    r"(?:const|let|var)\s+\w+\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>)\b.*"
)
#: The most a map of the files left out may take, in characters.
MOST_MAP_CHARACTERS = 20_000
MOST_DEFINITIONS_PER_FILE = 12


#: Files named one by one as left out of the memory, at most; the rest are counted.
MOST_NAMED_LEFT_OUT = 60


def _definitions(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        if _DEFINES.match(line):
            found.append(" ".join(line.strip().rstrip("{:").split())[:120])
            if len(found) >= MOST_DEFINITIONS_PER_FILE:
                break
    return found


def _by_relevance(entries: dict[str, list[str]], focus: str, importance: dict[str, int],
                  root: str | Path | None = None) -> list[str]:
    """The files most worth a place first: those `focus` names, their neighbours, those defining its words, the most imported.

    Agentless localises by files, then their definitions; Aider's repository
    map ranks files by how much the rest of the code refers to them. Both
    without a parser per language here: the words and the import counts.
    """
    words = set(_WORD.findall(focus.lower()))
    named = {path for path in entries if path in focus or (len(path.rsplit("/", 1)[-1]) > 4 and path.rsplit("/", 1)[-1] in focus)}
    near: set[str] = set()
    if root is not None and named:
        try:
            from app.analysis.project_graph import build

            graph = build(root)
            near = {other for path in named for other in (*graph.get(path, {}).get("imports", []),
                                                          *graph.get(path, {}).get("imported_by", []))} - named
        except Exception:  # noqa: BLE001 - no graph, no neighbours
            pass

    def score(path: str) -> tuple[int, int, int, str]:
        said = sum(1 for d in entries[path] for w in _WORD.findall(d.lower()) if w in words)
        return (0 if path in named else 1 if path in near else 2, -said, -importance.get(path, 0), path)

    return sorted(entries, key=score)


def map_of(files: dict[str, str], focus: str = "", most_characters: int = MOST_MAP_CHARACTERS,
           importance: dict[str, int] | None = None, root: str | Path | None = None) -> str:
    """For each file, the lines that define something - its functions, classes and types - one file a line.

    A large project's files do not all fit; naming the ones left out told a
    stage nothing about what they hold, so it read them to find out. The
    lines that define something are most of what a reader needs to know
    which one to open (the idea of Aider's repository map, without a parser
    per language).

    While every file fits, the map is in path order, as it always was. Past
    `most_characters` it was cut there too - alphabetically, so on a large
    project the map held `api/` and `app/` and never `src/` - and said
    nothing of the rest. Now the files most worth a place come first
    (`_by_relevance`: by `focus`, else by `importance`, how many files import
    each; with `root`, the code graph's neighbours of the files `focus`
    names next), and a last line counts the files left out.
    """
    entries = {path: found for path in sorted(files) if (found := _definitions(files[path]))}
    lines = [f"- {path}: " + " | ".join(found) for path, found in entries.items()]
    if sum(len(line) for line in lines) <= most_characters:
        return "\n".join(lines)
    chosen: list[str] = []
    used = 0
    for path in _by_relevance(entries, focus, importance or {}, root):
        entry = f"- {path}: " + " | ".join(entries[path])
        if used + len(entry) > most_characters:
            continue
        chosen.append(entry)
        used += len(entry)
    left = len(entries) - len(chosen)
    note = (f"\n({left:,} more files define things not shown here; search for a name or list a folder to find them.)"
            if left else "")
    return "\n".join(chosen) + note


def importance_of(repo_root: str | Path) -> dict[str, int]:
    """How many of the project's files import each one, from the harness's code graph; {} when there is none."""
    try:
        from app.analysis.project_graph import build

        return {path: len(node.get("imported_by") or []) for path, node in build(repo_root).items()}
    except Exception:  # noqa: BLE001
        return {}


def where_things_stand(repo_root: str | Path, files: dict[str, str]) -> str:
    """The workspace's top level, and the project's directory said to be empty when it is.

    Measured on one run: the architect's gathering turns, before any of the
    product existed, listed `.`, `docs`, `notes-api` and `.harness` and
    globbed for `**/package.json` six to eight times a visit - each answer the
    empty project it could have been told about.
    """
    root = Path(repo_root)
    try:
        top = sorted(
            entry.name + ("/" if entry.is_dir() else "") for entry in root.iterdir()
            if not entry.name.startswith(".")
        )
    except OSError:
        return ""
    line = f"Workspace top level: {', '.join(top) or 'nothing'}.\n"
    try:
        from app.tools.repository import pinned_project_directory

        project = pinned_project_directory(root)
    except Exception:  # noqa: BLE001 - the listing alone
        project = None
    if project and not any(path.startswith(f"{project}/") for path in files):
        line += (
            f"The project directory `{project}/` holds no files yet: nothing of the product has been written, "
            "so listing or searching it finds nothing.\n"
        )
    return line + "\n"


#: A fixer's share of the specification: its outline and the sections its defect points at.
FIXER_SPECIFICATION_CHARACTERS = 8_000
#: The documents a fixer is given; the plans that led to the code are named, not held.
FIXER_DOCUMENTS = ("docs/technical_specification.md", "docs/acceptance_criteria.md")
#: The documents a builder on written code is given (`builds_on_code`): a fixer's, and the sprint plan for the part of
#: it the request points at. The other plans - the milestones, the acceptance tests, the stack, the intake, reviews -
#: are records of work done before it, named.
BUILDER_ON_CODE_DOCUMENTS = (*FIXER_DOCUMENTS, "docs/sprint_plan.md")
#: The stages that open on the product's code (`builds_on_code`): a builder, and a review of what the builders wrote.
#: Measured on one run: the sprint's code review, after the testing stage's loop, opened on the plans whole and of the
#: code only an `__init__` and the manifest; it read the four files under review seven times each over four summaries.
_ON_CODE_STAGES = ("specialist_", "code_review_")
#: The stages that build the product from work orders: past their room, their memory outlines what it does not hold
#: (LF.1287) and holds what they wrote and read at each summary (LF.1288). Measured on one medium run: a sprint's
#: backend builder spent 24 minutes reading about six files a call, summarised every two or three calls, one write.
_BUILDER_STAGES = ("specialist_",)
#: The stages that set the project up: what they write is the scaffold, not the product's code.
_SETUP_STAGES = ("stack_setup",)


#: How a request quotes sections of the specification (`technical_lead._the_contracts`), and each quoted section.
_QUOTED_SPECIFICATION = re.compile(r"^--- From the approved technical specification\b[^\n]*---\n(.*?)(?=^--- |\Z)", re.M | re.S)
_QUOTED_HEADING = re.compile(r"^([A-Z][\w ()/-]*):$", re.M)


def _without_the_quoted_sections(document: str, request: str) -> tuple[str, list[str]]:
    """`document` less the `## ` sections `request` quotes under the same heading, and their names.

    Measured on three runs: the technical lead's request quoted the specification's contract sections (~31k
    characters) while its memory held the whole specification again.
    """
    found = _QUOTED_SPECIFICATION.search(request or "")
    if not found:
        return document, []
    quoted = {" ".join(h.lower().split()) for h in _QUOTED_HEADING.findall(found.group(1))}
    kept: list[str] = []
    dropped: list[str] = []
    skipping = False
    for line in document.splitlines(keepends=True):
        if line.startswith("## "):
            name = line[3:].strip()
            skipping = " ".join(name.lower().split()) in quoted
            if skipping:
                dropped.append(name)
        if not skipping:
            kept.append(line)
    return "".join(kept), dropped


#: The stages that plan the work and write no file: the harness's kept files are named to them, not held.
_PLANNING_STAGES = ("technical_lead", "scrum_master")


def _kept_out_for(stage: str, repo_root: str | Path) -> tuple[str, ...]:
    """Files a stage's memory leaves out: the harness's own for a planning stage; the specification for a layered setup.

    A setup on a runner layer writes a few framework files; the specification is the product's (HR2.SS.2: its memory
    held the whole document, and one layered stage wrote the product from it).
    """
    if planning_stage(stage):
        return kept_by_the_harness(repo_root)
    if str(stage or "").startswith("stack_setup"):
        from app.tools.repository import SETUP_SCOPE_FILE

        if (Path(repo_root) / SETUP_SCOPE_FILE).is_file():
            return ("docs/technical_specification.md",)
    return ()


def builds_on_code(repo_root: str | Path, stage: str) -> bool:
    """Whether a builder opens on the product's code an earlier stage wrote: not the setup's scaffold, not its own.

    Measured on one run: a later sprint's testing stage, writing unit tests for the code two sprints had written,
    opened on the workflow's documents whole - every sprint's long sections of the sprint plan among them - and of
    the product only an empty `__init__`; the files its tests were for were named as left out. It read them, the
    conversation was summarised, it read them again: eleven summaries in fifty minutes. Never raises.
    """
    if not str(stage or "").startswith(_ON_CODE_STAGES):
        return False
    try:
        from app.analysis.file_kinds import classify_file
        from app.analysis.project_memory import creators

        written = creators(repo_root)
        for path in current(repo_root):
            author = written.get(path, "")
            if (author and author != stage and not author.startswith(_SETUP_STAGES)
                    and not path.startswith(("docs/", ".")) and classify_file(path) == "application"):
                return True
    except Exception:  # noqa: BLE001 - the memory as before
        logger.debug("Could not tell whether the product has code", exc_info=True)
    return False


#: The stage that writes the acceptance suite.
_SUITE_WRITER = "acceptance_author"


def written_from_the_interface(repo_root: str | Path, stage: str) -> tuple[str, ...]:
    """The product's source a later sprint's suite writer's memory leaves out (PA.12, LF.1362); () for every other
    stage and for a suite written whole or a first sprint's part.

    The request hands it the product's routes, the shapes they take and give, and the earlier tests' helpers
    (`app.acceptance.product_interface`). Measured on one medium run: a later sprint's writer read the product's
    schemas 21 times and a service 19 in one visit of 123 calls, 118 of them reads. Never raises: ()."""
    if not str(stage or "").startswith(_SUITE_WRITER):
        return ()
    try:
        from app.acceptance import by_sprint, product_interface

        if not by_sprint.earlier_files(repo_root):
            return ()
        return tuple(product_interface.the_product_s_source(repo_root, current(repo_root)))
    except Exception:  # noqa: BLE001 - the memory as before
        return ()


def planning_stage(stage: str) -> bool:
    return str(stage or "").startswith(_PLANNING_STAGES)


def kept_by_the_harness(repo_root: str | Path) -> tuple[str, ...]:
    """The workspace paths of the files the harness writes and keeps for this run's pack; () when none. Never raises."""
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        if found is None:
            return ()
        project = str((found[1] or {}).get("project") or "")
        return tuple(f"{project}/{name}" if project else name for name in found[0].kept_files)
    except Exception:  # noqa: BLE001 - held as before
        return ()


def render(repo_root: str | Path, budget_characters: int, focus: str = "",
           for_a_fixer: bool = False, kept_out: tuple[str, ...] = (), sliced: bool = False,
           sprint_files: tuple[str, ...] = (), on_code: bool = False,
           documents_at_most: int = 0, review_files: tuple[str, ...] = (),
           numbered_as: str = "", outlined: bool = False,
           interface_only: tuple[str, ...] = ()) -> tuple[str, dict[str, str]]:
    """The memory as text within `budget_characters`, and the files it holds by path.

    `for_a_fixer`: the product's code first, the acceptance criteria, and the specification as its outline and the
    sections the defect points at; the other plans named only. Measured over 64 fix attempts: every fixer opened on
    about 164k characters of plans with its failure about 2k of it, and those left open read twice as many files and
    reasoned nearly three times as long as those that fixed their defect. A fixer's file longer than
    `memory_slices.MOST_CHARACTERS_WHOLE` is held as the lines around those its failure names (deep review C3).

    `sliced`: only the product files the request names, and what they import, held whole (`SLICED_MEMORY`).

    `sprint_files`: a re-plan's sprint's own files (`LEAD_REPLAN_REQUEST_SMALLER`): only the product files among them,
    and what they import, held whole, and every document longer than `memory_slices.MOST_CHARACTERS_WHOLE` held as
    its digest. The whole memory as before when none of them is in the project.

    `on_code`: a builder on code earlier stages wrote (`builds_on_code`) is given what a fixer is, as far as a builder
    needs it: the documents of `BUILDER_ON_CODE_DOCUMENTS`, each longer than `memory_slices.MOST_CHARACTERS_WHOLE` as
    its digest, and the other plans named, so the rest of the budget holds the product's code. A slice orders that
    code, the files the request names and what they import first; it leaves none out, since a file the builder is to
    write does not exist yet to import what it builds on.

    `documents_at_most`: each workflow document longer than this is held as its digest - its outline by line and the
    sections the request points at, within this size (a request past its input budget, `render_for_a_stage`).

    `review_files`: the files a review judges (`review_files.under_review`), held first, numbered, within the budget
    less the room the documents' digests need (`REVIEW_DOCUMENTS_ROOM`); the rest of the memory as before after them.
    Given only when today's request and memory would not show them all (`review_files.fits_as_today`).
    `numbered_as` heads each of them after its path (`review_files.numbered_heading`; a review's by default).
    With them, every code file not held whole is in an outline of its definitions and tests with their lines
    (`app.analysis.outline`, LF.1287) in place of the map of the files left out: its room comes first out of the
    room for the whole files, each file held whole gives its share back, and the memory runs the documents, the
    outline, then the files held whole. Measured on one medium run: 13 of 45 files fit whole and the map of the rest
    had no line numbers, so a stage read whole each file it needed one function of.

    `interface_only`: the product's source a later sprint's suite writer is not given (`written_from_the_interface`):
    neither held, outlined nor mapped, and counted in one line of its own.
    """
    files = current(repo_root)
    if not files or budget_characters <= 0:
        return "", {}
    from app.agents import memory_slices

    ask = memory_slices.the_ask(focus)
    product = [path for path in files if not path.startswith(("docs/", "."))]
    the_slice = memory_slices.the_slice(repo_root, ask, files) if sliced else None
    replan = _the_sprint_s_slice(repo_root, sprint_files, files) if sprint_files else None
    if replan is not None:
        the_slice = replan
    first: set[str] = set()
    if on_code and the_slice is not None:
        first, the_slice = the_slice, None
    held: dict[str, str] = {}
    parts: list[str] = []
    from app.agents.canonical_memory import enabled as canonical_order

    canonical = canonical_order()
    after_the_rest: list[str] = []
    # A fixer's documents ahead of its code, the same blocks in a stable order (`STABLE_MEMORY_ORDER`, off until
    # measured): those held whole first, then the digests its defect chose.
    from app.agents import stable_memory_order

    stable = for_a_fixer and stable_memory_order.enabled()
    whole_documents: list[str] = []
    chosen_documents: list[str] = []
    left_out: list[str] = []
    kept_named: list[str] = []
    used = 0
    try:
        from app.stacks.scaffold import folders_nothing_serves

        unserved = tuple(folders_nothing_serves(repo_root))
    except Exception:  # noqa: BLE001 - the order stands as it was
        unserved = ()
    try:
        from app.acceptance.sprint_scope import later_sprints_files

        later = later_sprints_files(repo_root)
    except Exception:  # noqa: BLE001 - every file is due
        later = {}
    held_back: list[str] = []
    from app.agents.stable_prefix import document_limit

    shorter_documents = document_limit(files)
    ranked = _ranked(files, focus, unserved)
    not_given = set(interface_only)
    under_review = [path for path in dict.fromkeys(review_files) if path in files and not path.startswith("docs/")
                    and path not in not_given]
    review_room = budget_characters - min(REVIEW_DOCUMENTS_ROOM, budget_characters // 4)
    # Past the size gate (a review or reading stage's files under review), every code file not held whole is in an
    # outline with its line ranges (LF.1287), its room taken before the whole files are chosen: each file held whole
    # gives its outline's room back.
    outline_blocks: dict[str, str] = {}
    if under_review or outlined:
        from app.analysis import outline

        outline_blocks = {path: outline.block(path, files[path]) for path in ranked
                          if not path.startswith("docs/") and path not in kept_out and path not in later
                          and path not in not_given and not _RECORDS.match(path)}
    outline_most = int(review_room * OUTLINE_SHARE)
    outline_left = sum(map(len, outline_blocks.values()))

    def outline_room(holding: str = "") -> int:
        """The outline's room once `holding` is held whole; 0 when there is no outline."""
        return min(outline_most, outline_left - len(outline_blocks.get(holding, "")))

    if under_review:
        ranked = under_review + [p for p in ranked if p not in set(under_review)]
    elif for_a_fixer:
        ranked = [p for p in ranked if not p.startswith("docs/")] + [p for p in ranked if p.startswith("docs/")]
    elif on_code:
        # The documents first, each held to a digest's size, then the code with the rest of the budget.
        ranked = ([p for p in ranked if p.startswith("docs/")] + [p for p in ranked if p in first]
                  + [p for p in ranked if not p.startswith("docs/") and p not in first])
    for path in ranked:
        text = files[path]
        if for_a_fixer and path.startswith("docs/"):
            if path not in FIXER_DOCUMENTS:
                left_out.append(path)
                continue
            if path.endswith("technical_specification.md"):
                digest = digest_of(text, focus, min(FIXER_SPECIFICATION_CHARACTERS, max(0, budget_characters - used)))
                if digest:
                    block = f"=== {path} (outline and the sections this defect points at; read others by line) ===\n{digest}\n"
                    (chosen_documents if stable else parts).append(block)
                    used += len(block)
                continue
        if _RECORDS.match(path) or (on_code and path.startswith("docs/") and path not in BUILDER_ON_CODE_DOCUMENTS):
            left_out.append(path)
            continue
        if path in kept_out:
            # Measured on one run: the technical lead's memory held the harness's 44k `test-setup.mjs`.
            kept_named.append(path)
            continue
        if path in not_given:
            continue
        if path in later:
            # A later sprint's tests, handed over whole, read as this sprint's
            # work (see `app.acceptance.sprint_scope`); the snapshot held them
            # back and the memory now stands in for it.
            held_back.append(f"{path} ({', '.join(later[path])})")
            continue
        if path in under_review:
            from app.agents.review_files import NUMBERED_MARK, numbered

            block = f"=== {path} {numbered_as or NUMBERED_MARK}\n{numbered(text)}\n"
            if len(text) > LARGEST_FILE_CHARACTERS or used + len(block) + outline_room(path) > review_room:
                left_out.append(path)
                continue
            parts.append(block)
            held[path] = text
            used += len(block)
            outline_left -= len(outline_blocks.get(path, ""))
            continue
        if the_slice is not None and path in product and path not in the_slice:
            # Not named by this request, nor imported by a file it names (`SLICED_MEMORY`).
            left_out.append(path)
            continue
        if for_a_fixer and path in product and len(text) > memory_slices.MOST_CHARACTERS_WHOLE:
            # Measured: one fixer was handed a 28.7k test file its defect never named. Its failing lines, not the file.
            lines = memory_slices.lines_named(ask, path, product)
            block = memory_slices.windowed_block(path, text, lines) if lines else ""
            if block and used + len(block) <= budget_characters:
                parts.append(block)
                used += len(block)
                continue
            if not memory_slices.named(ask, path, product):
                left_out.append(path)
                continue
        if path.endswith("technical_specification.md"):
            text, quoted = _without_the_quoted_sections(text, focus)
            if quoted:
                text += ("\n(Not repeated here because this request quotes them in full: " + ", ".join(quoted) + ".)\n")
        block = f"=== {path} ===\n{text.rstrip()}\n"
        # A small product's documents are held as a digest sooner (`STABLE_STAGE_PREFIX`, off until measured).
        largest = (shorter_documents or LARGEST_FILE_CHARACTERS) if path.startswith("docs/") else LARGEST_FILE_CHARACTERS
        if (replan is not None or on_code) and path.startswith("docs/"):
            largest = min(largest, memory_slices.MOST_CHARACTERS_WHOLE)
        if documents_at_most and path.startswith("docs/"):
            largest = min(largest, documents_at_most)
        if len(text) > largest and path.endswith(".md"):
            # Too large to hold whole: its outline and the sections this
            # stage's request points at, so it is not read window by window.
            digest = digest_of(text, focus, min(largest, budget_characters - used - outline_room()))
            if digest:
                block = f"=== {path} (outline and the sections this request points at; read others by line) ===\n{digest}\n"
                # Chosen by the request's words, so after what every request shares (plan PX.3).
                (chosen_documents if stable and path.startswith("docs/")
                 else after_the_rest if canonical else parts).append(block)
                used += len(block)
                continue
        if len(text) > LARGEST_FILE_CHARACTERS or used + len(block) + outline_room(path) > budget_characters:
            left_out.append(path)
            continue
        (whole_documents if stable and path.startswith("docs/") else parts).append(block)
        held[path] = text
        used += len(block)
        outline_left -= len(outline_blocks.get(path, ""))
    stable = stable and bool(whole_documents or chosen_documents)
    parts = whole_documents + chosen_documents + parts + after_the_rest
    outlined_text, in_the_outline = _the_outline(repo_root, files, outline_blocks, held, outline_most, focus,
                                                 canonical)
    if under_review or outlined:
        # What changes least first: the documents, the outline, then the files held whole (LF.1288 chooses those
        # again at a summary, so the server's cache holds up to them).
        parts = ([b for b in parts if b.startswith("=== docs/")] + ([outlined_text] if outlined_text else [])
                 + [b for b in parts if not b.startswith("=== docs/")])
        left_out = [path for path in left_out if path not in in_the_outline]
    if not parts:
        return "", {}
    head = (
        "[Project memory: the workflow's documents and the project's files as they are now, kept current "
        "by the harness. Use them as they are here; read a file only if it is named at the end as not "
        "included." + (" " + stable_memory_order.SAID if stable else "")
        + (" " + _replan_said() if replan is not None
           else " " + memory_slices.SAID if the_slice is not None else "") + "]\n\n"
    ) + where_things_stand(repo_root, files)
    # Named one by one only up to `MOST_NAMED_LEFT_OUT`, in the memory's own
    # order: a large project's left-out list was every path it has, larger
    # than the memory itself and outside its budget.
    named = left_out[:MOST_NAMED_LEFT_OUT]
    more = len(left_out) - len(named)
    tail = ("\nNot included here (read when needed): " + ", ".join(named)
            + (f", and {more:,} more (list a folder or search to find them)" if more else "") + "\n") if left_out else ""
    if kept_named:
        tail += ("\nNot included because the harness writes and keeps them, and no work order changes them: "
                 + ", ".join(kept_named) + "\n")
    if held_back:
        tail += ("\nNot included because every test in them is for a criterion a later sprint builds: "
                 + ", ".join(held_back) + "\n")
    source = [path for path in ranked if path in not_given]
    if source:
        tail += (f"\nNot included: the product's source, {len(source)} files ("
                 + ", ".join(source[:MOST_SOURCE_NAMED]) + (", ..." if len(source) > MOST_SOURCE_NAMED else "")
                 + "). This sprint's tests are written from its interface, which the request gives - its routes, "
                 "the shapes they take and give, and the earlier tests' helpers - not from its source.\n")
    sources = {path: files[path] for path in left_out if not path.startswith("docs/") and not outline_blocks}
    # Ranked by the request only when the memory's order may follow it
    # (`CANONICAL_MEMORY` off); otherwise by what does not change between
    # requests, so the memory stays the same, and cached, from call to call.
    shapes = map_of(sources, focus="" if canonical else focus,
                    importance=importance_of(repo_root) if sum(map(len, sources.values())) > MOST_MAP_CHARACTERS else None)
    if shapes:
        tail += "\nWhat those files define (read one when you need its body):\n" + shapes + "\n"
    return head + "\n".join(parts) + tail, held


#: The product's source files named one by one in the memory of a suite writer not given them, at most.
MOST_SOURCE_NAMED = 12


#: The most of a review's room (the budget less the documents' room) its outline of the other files may take.
#: Measured on one medium run: an outline of all 45 files was 18,475 characters in a room of 70,598.
OUTLINE_SHARE = 0.3
#: How the memory heads its outline of the files it does not hold whole (LF.1287).
OUTLINE_HEADING = (
    "=== Outline of the project's other files, not held whole here: each file's definitions and tests, each with "
    "its first and last line. Read only the lines you need, by range (`offset` and `limit`). ==="
)


def _the_outline(repo_root: str | Path, files: dict[str, str], blocks: dict[str, str], held: dict[str, str],
                 most_characters: int, focus: str, canonical: bool) -> tuple[str, set[str]]:
    """The memory's outline of the files in `blocks` it does not hold whole, and the files it names; ("", set())
    for none. Past `most_characters` the files most worth a place first (`_by_relevance`), the rest counted."""
    from app.analysis import outline

    left = {path: text for path, text in blocks.items() if path not in held}
    if not left:
        return "", set()
    order: list[str] = []
    if sum(map(len, left.values())) > most_characters:
        order = _by_relevance(outline.texts_of(left, files), "" if canonical else focus, importance_of(repo_root))
    shown = set(outline.shown_of(left, most_characters, order))
    return OUTLINE_HEADING + "\n" + outline.rendered_blocks(left, most_characters, order), shown


def _the_sprint_s_slice(repo_root: str | Path, sprint_files: tuple[str, ...], files: dict[str, str]) -> set[str] | None:
    """The product files a re-plan's memory holds whole: the sprint's own and what they import; None to hold all."""
    from app.agents import memory_slices

    product = [path for path in files if not path.startswith(("docs/", "."))]
    named = "\n".join(sprint_files)
    chosen = {path for path in product if memory_slices.named(named, path, product)}
    if not chosen:
        return None
    return chosen | (memory_slices.imports_of(repo_root, chosen) & set(product))


def render_for_a_replan(repo_root: str | Path, budget_characters: int, opening: str, sprint_files: tuple[str, ...],
                        kept_out: tuple[str, ...] = ()) -> tuple[str, dict[str, str], str]:
    """A re-plan's memory, the files it holds and the request it goes with (`LEAD_REPLAN_REQUEST_SMALLER`).

    Never longer than the request it replaces: the memory, the request and the line naming the held files together
    are held to the length they have without the switch, the request less its list of the sprint's files. Measured
    on a small window: the budget the sliced files freed filled with the documents the whole memory had to leave out,
    and the request grew. So the smaller memory gets no more budget than the whole one used, and where it is still
    not shorter, the whole memory and the request without the list are sent, as with the switch off.
    """
    from app.agents import prompt_size

    plain = opening.replace(prompt_size.sprint_files_section(list(sprint_files)), "", 1)
    whole, whole_held = render(repo_root, budget_characters, plain, kept_out=kept_out)

    def length(memory: str, held: dict[str, str], request: str) -> int:
        return (len(memory) + 2 if memory else 0) + len(request) + len(files_held_line(list(held)))

    smaller, smaller_held = render(repo_root, min(budget_characters, len(whole)), opening, kept_out=kept_out,
                                   sprint_files=sprint_files)
    if smaller and length(smaller, smaller_held, opening) < length(whole, whole_held, plain):
        return smaller, smaller_held, opening
    return whole, whole_held, plain


def _without_the_list(messages: list[Any], opening: str, request: str) -> list[Any]:
    """`messages` with the opening request as `request` (the re-plan's list of files taken out), or as they are."""
    if request == opening:
        return messages
    from langchain_core.messages import HumanMessage

    for index, message in enumerate(messages):
        if getattr(message, "type", None) == "human" and getattr(message, "content", None) == opening:
            return [*messages[:index], HumanMessage(content=request, additional_kwargs=dict(
                getattr(message, "additional_kwargs", None) or {})), *messages[index + 1:]]
        if isinstance(message, dict) and message.get("role") == "user" and message.get("content") == opening:
            return [*messages[:index], {**message, "content": request}, *messages[index + 1:]]
    return messages


def _replan_said() -> str:
    from app.agents.prompt_size import REPLAN_SAID

    return REPLAN_SAID


def _the_sprint_s_files(stage: str, opening: str) -> tuple[str, ...]:
    """A lead's re-plan's sprint files, while `LEAD_REPLAN_REQUEST_SMALLER` is on; () otherwise."""
    if not str(stage or "").startswith("technical_lead"):
        return ()
    from app.agents import review_files

    if review_files.held_named_in(opening):
        return ()  # the files it reads are held numbered instead (LF.1286)
    from app.agents import prompt_size

    if not prompt_size.lead_replan_smaller_switch.enabled():
        return ()
    return tuple(prompt_size.sprint_files_in(opening))


def _arguments_for(repo_root: str | Path, stage: str) -> dict[str, Any]:
    """How `render` is called for a stage that is not a fixer cut to its target."""
    from app.agents import memory_slices

    return dict(for_a_fixer=str(stage or "").startswith("defect_fix"), kept_out=_kept_out_for(stage, repo_root),
                sliced=memory_slices.enabled() and str(stage or "").startswith(("defect_fix", "specialist_")),
                on_code=builds_on_code(repo_root, stage),
                interface_only=written_from_the_interface(repo_root, stage))


#: The room a review's memory leaves after the files under review for the documents' digests, at most a quarter.
REVIEW_DOCUMENTS_ROOM = 12_000


def render_for_a_review(repo_root: str | Path, model: Any, opening: str, stage: str,
                        review_files: Sequence[str]) -> tuple[str, dict[str, str]]:
    """A review's memory with `review_files` held first, numbered, and each long document as its digest (LF.1284);
    another reading stage's the same way (`review_files.READING_STAGES`, LF.1286).

    The budget is the model's share whatever the request's size: the files the request names as held are exactly
    those this holds (`review_files.held_for_review` renders it to find them), so it is not cut again to the input
    budget as other requests are (`_within_its_budget`)."""
    from app.agents.review_files import numbered_heading

    return render(repo_root, budget_for(model), opening, **_arguments_for(repo_root, stage),
                  documents_at_most=DOCUMENTS_PAST_THE_BUDGET, review_files=tuple(review_files),
                  numbered_as=numbered_heading(stage))


def render_for_a_stage(repo_root: str | Path, model: Any, opening: str, stage: str,
                       noted: bool = True) -> tuple[str, dict[str, str]]:
    """The memory a stage's opening request is given, and the files it holds (not a lead's re-plan's).

    A fixer whose request was cut to its size target (`fixer_request_shape.reshaped`) is given the memory cut the same
    way (LF.1270): the files its evidence names and what they import held whole, the rest named, within what the
    target leaves beside the request. The fix request reads this too, to tell whether it is past its target.

    Any other stage whose request and memory together are past its input budget (`request_budget.opening_target`,
    LF.1274) is given the memory within what the budget leaves beside its request (at least
    `request_budget.MEMORY_LEAST_SHARE` of it), each long workflow document as its outline by line and the sections
    the request points at (`documents_at_most`) - with `REQUEST_BUDGET_FOR_EVERY_STAGE` on (off until measured: small
    runs open past the budget too). Measured on a medium run: every builder of the first sprint, the lead, the
    planner, the reviews and the suite's author opened on 157,000-198,000 characters, 53,000-69,000 of them the
    specification's sections beside the parts of it their requests already quoted. Within the budget it is as before.
    One `request_budget` record a visit says which, and with the switch off what would have been cut (none with
    `noted` False: the size gate of a review asking what today's memory holds, `review_files.fits_as_today`).

    A review, or another reading stage (`review_files.READING_STAGES`, LF.1286), whose request names the files its
    memory holds (`review_files.held_section`) is given `render_for_a_review` (LF.1284).
    """
    fixer = str(stage or "").startswith("defect_fix")
    if fixer:
        from app.graph import fixer_request_shape

        if fixer_request_shape.reshaped(opening):
            target = fixer_request_shape.opening_target(model)
            least = int(target * fixer_request_shape.MEMORY_LEAST_SHARE)
            return render(repo_root, min(budget_for(model), max(least, target - len(opening))),
                          fixer_request_shape.the_evidence(opening), for_a_fixer=True, sliced=True)
    from app.agents import review_files

    named = review_files.held_named_in(opening) if not fixer and review_files.holds_what_it_reads(stage) else ()
    if named:
        memory, held = render_for_a_review(repo_root, model, opening, stage, named)
        if noted:
            _noted_as_built(stage, model, opening, memory)
        return memory, held
    arguments = _arguments_for(repo_root, stage)
    memory, held = render(repo_root, budget_for(model), opening, **arguments)
    if fixer:
        return memory, held  # sized with its request (`nodes.fixes._sized_to_its_target`)
    if str(stage or "").startswith(_BUILDER_STAGES) and memory and not _holds_every_code_file(
            repo_root, stage, held, current(repo_root)):
        # A builder past its room: the code files it does not hold are outlined with their lines (LF.1287).
        arguments = {**arguments, "outlined": True}
        memory, held = render(repo_root, budget_for(model), opening, **arguments)
    return _within_its_budget(repo_root, model, opening, stage, memory, held, arguments, noted=noted)


def as_the_stage_opens(repo_root: str | Path, model: Any, opening: str, stage: str) -> tuple[str, dict[str, str]]:
    """The memory a stage's first call is given and the files it holds, as the middleware renders it - a lead's
    re-plan's (`render_for_a_replan`) or `render_for_a_stage` - without recording it: what a stage is shown today,
    for the size gate of `review_files.fits_as_today`."""
    sprint_files = _the_sprint_s_files(stage, opening)
    if sprint_files:
        memory, held, _ = render_for_a_replan(repo_root, budget_for(model), opening, sprint_files,
                                              kept_out=_kept_out_for(stage, repo_root))
        return memory, held
    return render_for_a_stage(repo_root, model, opening, stage, noted=False)


def _noted_as_built(stage: str, model: Any, opening: str, memory: str) -> None:
    try:
        from app.agents import request_budget

        request_budget.noted(stage, built=len(opening) + (len(memory) + 2 if memory else 0),
                             target=request_budget.opening_target(model))
    except Exception:  # noqa: BLE001 - a record never fails the request
        logger.debug("Could not record a review's request", exc_info=True)


#: The size a long workflow document is held to, as its digest, in the memory of a request past its input budget.
DOCUMENTS_PAST_THE_BUDGET = 12_000


def _within_its_budget(repo_root: str | Path, model: Any, opening: str, stage: str, memory: str,
                       held: dict[str, str], arguments: dict[str, Any], noted: bool = True) -> tuple[str, dict[str, str]]:
    """`memory` when it and `opening` are within the stage's input budget; past it, with
    `REQUEST_BUDGET_FOR_EVERY_STAGE` on, the memory rendered again within what the budget leaves, long documents as
    digests - off, `memory` as it is and the record says what would have been cut. Never raises: `memory` as it is."""
    try:
        from app.agents import request_budget

        def note(*args: Any, **kwargs: Any) -> None:
            if noted:
                request_budget.noted(*args, **kwargs)

        target = request_budget.opening_target(model)
        built = len(opening) + (len(memory) + 2 if memory else 0)
        if built <= target or not memory:
            note(stage, built=built, target=target)
            return memory, held
        room = min(budget_for(model), max(int(target * request_budget.MEMORY_LEAST_SHARE), target - len(opening) - 2))
        smaller, smaller_held = render(repo_root, room, opening, **arguments,
                                       documents_at_most=DOCUMENTS_PAST_THE_BUDGET)
        if not smaller or len(smaller) >= len(memory):
            note(stage, built=built, target=target)
            return memory, held
        documents = [path for path in held if path.startswith("docs/") and path not in smaller_held]
        documents += [path for path in DOCUMENT_ORDER if path not in held and f"=== {path} (outline" in memory
                      and f"=== {path} (outline" in smaller and path not in documents]
        fitted = request_budget.Fitted(
            text=smaller, built=len(memory), target=target,
            cut=[f"{path} as its outline and the sections this request points at (read others by line)"
                 for path in documents],
            left_out=[path for path in held if not path.startswith("docs/") and path not in smaller_held])
        applied = request_budget.for_every_stage_switch.enabled()
        note(stage, built=built, sent=len(opening) + len(smaller) + 2, target=target, fitted=fitted,
                             applied=applied, message=request_budget.SAID_FOR_EVERY_STAGE if applied else "")
        if not applied:
            return memory, held  # what would have been cut is in the record (`REQUEST_BUDGET_FOR_EVERY_STAGE` off)
        logger.info("The memory of %s is past its input budget (%d characters with its request, target %d); held "
                    "within %d characters, long documents as digests", stage, built, target, room)
        return smaller, smaller_held
    except Exception:  # noqa: BLE001 - the memory as rendered
        logger.debug("Could not hold a stage's memory to its budget", exc_info=True)
        return memory, held


def budget_for(model: Any) -> int:
    """The memory's share of `model`'s window, in characters."""
    try:
        from app.agents.context_budget import ContextBudget
        from app.models import environment_of

        window = ContextBudget.resolve(environment_of(model)).window_tokens
    except Exception:  # noqa: BLE001 - the deployment's own window
        window = 32_000
    return int(min(MOST_CHARACTERS, window * MEMORY_SHARE * CHARS_PER_TOKEN))


def enabled() -> bool:
    """On in every delivery mode unless `PROJECT_MEMORY` is off: it saves calls and takes nothing out."""
    return str(os.environ.get("PROJECT_MEMORY") or "").strip().lower() not in ("0", "off", "false", "no")


#: Files named in the line that closes the opening request, at most.
MOST_HELD_NAMED = 30


def files_held_line(held: Any) -> str:
    """The line closing the opening request: the files the memory holds whole, or "" for none.

    The memory opens the request and the request can run to 70,000 tokens
    after it; by its end the model read files it held. Measured on one gate
    run: 24 of 142 tool-calling replies did nothing but read files the memory
    held - every review's and the lead's first move - each a model call and
    its reasoning, answered with a pointer. Named again at the end, where the
    model is about to act. Fixed for the visit, so the prompt stays cached.
    """
    names = [str(n) for n in held or () if not str(n).startswith(".")]
    if not names:
        return ""
    shown = ", ".join(f"`{n}`" for n in names[:MOST_HELD_NAMED]) + (
        f" and {len(names) - MOST_HELD_NAMED} more" if len(names) > MOST_HELD_NAMED else "")
    return (f"\n\n[Already in front of you, whole and current, in the project memory at the start of this "
            f"message: {shown}. Reading any of them returns nothing new; work from the memory.]")


def _with_memory(messages: list[Any], memory: str, held: Any = ()) -> list[Any] | None:
    """`messages` with `memory` at the start of the opening request and the files it holds named at its end, or None if there is none to put it in."""
    from langchain_core.messages import HumanMessage

    from app.observability.transcript import MEMORY_CHARS

    closing = files_held_line(held)
    for index, message in enumerate(messages):
        if getattr(message, "type", None) == "human" and isinstance(getattr(message, "content", None), str):
            # How much of the message is memory, for the transcript's record of
            # what a request carried; the provider never sends it.
            marked = {**(getattr(message, "additional_kwargs", None) or {}), MEMORY_CHARS: len(memory) + 2}
            return [
                *messages[:index],
                HumanMessage(content=memory + "\n\n" + message.content + closing, additional_kwargs=marked),
                *messages[index + 1:],
            ]
        if isinstance(message, dict) and message.get("role") == "user" and isinstance(message.get("content"), str):
            return [*messages[:index], {**message, "content": memory + "\n\n" + message["content"] + closing}, *messages[index + 1:]]
    return None


#: Files whose changes are shown in full when reading is withheld, and the lines of each.
MOST_CHANGED_FILES_SHOWN = 3
MOST_DIFF_LINES_PER_FILE = 24


def _the_read_tool_is_withheld() -> bool:
    try:
        from app.agents.settled_answer import the_read_tool_is_withheld

        return the_read_tool_is_withheld()
    except Exception:  # noqa: BLE001 - then the note names the files, as before
        return False


#: A unified diff's hunk header: `@@ -57,2 +57,4 @@`.
_A_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
#: The hunks past the cut named by where they are, and the longest first line quoted for each.
MOST_HIDDEN_HUNKS_NAMED = 8
HIDDEN_LINE_CHARS = 90


def _where_the_rest_changed(rest: list[str]) -> str:
    """`: at lines ...` for the hunks of a diff past its cut, each with its first changed line; the rest are in the file.

    Measured on one run: a repair made three edits, and the note showed only the first two before "... 33 more changed
    lines". The model read that as the whole of what it had done ("the update confirms only AC-8 and AC-9 were
    applied"), disbelieved the edit tool's "already applied" and sent the third edit five times more until its tools
    were withheld. A cut note names where the rest is and says those changes are in the file.
    """
    hunks: list[tuple[int, int, str]] = []
    for line in rest:
        header = _A_HUNK.match(line)
        if header:
            start = int(header.group(1))
            hunks.append((start, start + max(int(header.group(2) or 1), 1) - 1, ""))
        elif hunks and not hunks[-1][2] and line[:1] in "+-" and line[1:].strip():
            hunks[-1] = (*hunks[-1][:2], line[:1] + " " + line[1:].strip()[:HIDDEN_LINE_CHARS])
    if not hunks:
        return "; they are in the file now, and `grep` finds any text in it"
    named = [
        (f"line {a}" if a == b else f"lines {a}-{b}") + (f" ({first})" if first else "")
        for a, b, first in hunks[:MOST_HIDDEN_HUNKS_NAMED]
    ]
    if len(hunks) > MOST_HIDDEN_HUNKS_NAMED:
        named.append(f"{len(hunks) - MOST_HIDDEN_HUNKS_NAMED} more place(s)")
    return (
        ", at " + "; ".join(named) + " of the file now. Those changes are in the file too: this shows only the "
        "first of them, not all that was done. `grep` finds any text in it"
    )


def changes_since(snapshot: dict[str, str], now: dict[str, str]) -> str:
    """A note naming what changed since the memory was taken, for the end of a call; "" if nothing did.

    The memory is taken once per stage visit and kept byte for byte (see the
    middleware), so a server's prefix cache holds across the visit; what a
    write changed after that is named here, at the end, where it changes
    nothing before it. A read of a changed file returns the file.
    """
    changed = sorted(path for path, text in snapshot.items() if path in now and now[path] != text)
    gone = sorted(path for path in snapshot if path not in now)
    added = sorted(path for path in now if path not in snapshot and not _RECORDS.match(path))
    lines = []
    if changed and _the_read_tool_is_withheld():
        # The note used to say "read for the current text" to a stage whose
        # read tool had been taken away. What changed is shown instead
        # (Initiative AM).
        lines.append("Changed since the project memory was taken (reading is withheld; this is what changed):")
        for path in changed[:MOST_CHANGED_FILES_SHOWN]:
            shown = list(difflib.unified_diff(
                snapshot[path].splitlines(), now[path].splitlines(), "before", "now", n=1, lineterm="",
            ))
            body = shown[:MOST_DIFF_LINES_PER_FILE]
            more = len(shown) - len(body)
            lines.append(f"{path} ({len(now[path].splitlines())} lines now):")
            lines.extend(f"  {line}" for line in body)
            if more > 0:
                lines.append(f"  ... {more} more changed lines, not shown" + _where_the_rest_changed(shown[len(body):]))
        if len(changed) > MOST_CHANGED_FILES_SHOWN:
            lines.append("Also changed: " + ", ".join(changed[MOST_CHANGED_FILES_SHOWN:40]))
    elif changed:
        lines.append("Changed since the project memory was taken (read for the current text): "
                     + ", ".join(f"{p} ({len(now[p].splitlines())} lines now)" for p in changed[:40]))
    if added:
        lines.append("New since then: " + ", ".join(added[:40]))
    if gone:
        lines.append("Deleted since then: " + ", ".join(gone[:40]))
    return ("[Project memory update]\n" + "\n".join(lines)) if lines else ""


def _a_narrow_window(args: dict, text: str) -> bool:
    """Whether a read asks for a few lines of a file by position (see `MOST_WINDOW_LINES`)."""
    offset, limit = args.get("offset"), args.get("limit")
    if offset in (None, "", 0) and limit in (None, ""):
        return False
    try:
        start = max(int(offset or 1), 1)
        wanted = int(limit) if limit not in (None, "") else text.count("\n") + 1 - start + 1
    except (TypeError, ValueError):
        return False
    return 0 < wanted <= MOST_WINDOW_LINES


#: The longest file a first re-read is answered with whole; a longer one gets the pointer at once.
MOST_LINES_A_FIRST_REREAD_GETS = 400


class _FirstRereadAnswered:
    """`FIRST_REREAD_ANSWERED` as the switch registry reads one: off in code, the compose file turns it on."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A stage's first read of a file it already holds in its opening project memory gets the file's "
                   "numbered lines back; only a second read gets the pointer to the memory. Measured on one run, 28 "
                   "of 197 model calls were such reads answered with a pointer that brought nothing back.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("FIRST_REREAD_ANSWERED", _FirstRereadAnswered.ON_BY_DEFAULT)


first_reread_switch = _FirstRereadAnswered()


def _numbered(content: str) -> str:
    """`content` with each line's number, as a read of the file shows it."""
    return "\n".join(f"{number:>6}\t{line}" for number, line in enumerate(content.splitlines(), start=1))


#: What the running stage's memory keeps across calls, in `stage_memory`.
_VISIT = "project_memory"
#: The mark a summary leaves in the visit: the files written and the reads it replaced (LF.1288).
_SUMMARISED = "summarised"


def a_summary_was_made(written: Sequence[str], reads: Sequence[Sequence[Any]]) -> None:
    """Mark the running stage's memory to choose again, at its next call, the files it holds whole (LF.1288).

    `written`: the files the stage wrote, oldest first; `reads`: [path, reads] for each file it read, the latest read
    last (`compaction.READS`). Nothing outside a graph run: no stage, no visit to mark."""
    from app.agents.stage_memory import current_stage_key, store

    if current_stage_key() is None:
        return
    store(_VISIT, {})[_SUMMARISED] = {"written": list(written or ()), "reads": [list(r) for r in reads or ()]}


def _chosen_again_at_a_summary(repo_root: str | Path, visit: dict[str, Any], mark: dict[str, Any], model: Any) -> None:
    """After a summary, the visit's memory holds whole the files the stage was reading and writing (LF.1288).

    A summary is the moment a stage loses what it read, and the moment the server's cache after the memory is lost
    anyway. When some code file the stage read or wrote is not held as it is now, the memory is rendered again on
    the files `review_files.chosen_again` puts first (`render_for_a_review`), and the visit's snapshot, held files
    and files as they are now are replaced. Between summaries nothing changes: the memory stays byte for byte.

    Size gate: a visit whose request named no held files (it fit as today at its start) is changed only when today's
    memory, rendered now, would not hold every code file of the product (`_every_code_file_fits`): a product whose
    files fit is as today, whatever the stage wrote. Never raises: the memory as it was."""
    try:
        from app.agents import review_files

        stage = str(visit.get("stage") or "")
        if not review_files.holds_what_it_reads(stage) or not visit.get("snapshot"):
            return
        written = [str(p) for p in mark.get("written") or ()]
        reads = [r for r in mark.get("reads") or () if isinstance(r, (list, tuple)) and len(r) >= 2]
        touched = review_files.chosen_again((), written, reads, repo_root)
        held = visit.get("held") or {}
        now = current(repo_root)
        stale = [path for path in touched if path in now and held.get(path) != now[path]]
        if not stale:
            return
        opening = str(visit.get("opened_on") or "")
        named = review_files.held_named_in(opening)
        if not named and _every_code_file_fits(repo_root, model, opening, stage, now):
            return
        chosen = review_files.chosen_again(named, written, reads, repo_root)
        memory, now_held = render_for_a_review(repo_root, model, opening, stage, chosen)
        if not memory or not now_held:
            return
        visit["snapshot"], visit["held"] = memory, now_held
        visit["files"] = dict(current(repo_root))
        visit["first_held"] = dict(now_held)
        visit["held_line"] = [path for path in chosen if path in now_held]
        logger.info("%s: after a summary its memory holds %d files whole, numbered: %s", stage,
                    len(visit["held_line"]), ", ".join(visit["held_line"][:10]))
    except Exception:  # noqa: BLE001 - the memory as it was
        logger.debug("Could not choose a stage's held files again", exc_info=True)


def _every_code_file_fits(repo_root: str | Path, model: Any, opening: str, stage: str, now: dict[str, str]) -> bool:
    """Whether the memory a stage would open on now holds every code file of the product (`review_files.under_review`
    of every file): the size gate of a visit that opened as today. The files kept out of its memory on purpose - the
    harness's own, a later sprint's tests - do not count."""
    _, today = as_the_stage_opens(repo_root, model, opening, stage)
    return _holds_every_code_file(repo_root, stage, today, now)


def _holds_every_code_file(repo_root: str | Path, stage: str, held: dict[str, str], now: dict[str, str]) -> bool:
    """Whether `held` holds every code file of the product but those kept out of `stage`'s memory on purpose."""
    from app.agents.review_files import under_review

    try:
        from app.acceptance.sprint_scope import later_sprints_files

        later = set(later_sprints_files(repo_root))
    except Exception:  # noqa: BLE001 - every file is due
        later = set()
    kept = set(_kept_out_for(stage, repo_root)) | later | set(written_from_the_interface(repo_root, stage))
    code = [path for path, _ in under_review(repo_root, [p for p in now
                                                       if not p.startswith("docs/") and p not in kept])]
    return all(path in held for path in code)


def _naming_the_held(messages: list[Any], held: Sequence[str]) -> list[Any]:
    """`messages` with each request's line naming the files held (`review_files.held_section`) naming `held`."""
    from langchain_core.messages import HumanMessage

    from app.agents.review_files import with_the_held_line

    changed: list[Any] = []
    for message in messages:
        if getattr(message, "type", None) == "human" and isinstance(getattr(message, "content", None), str):
            text = with_the_held_line(message.content, held)
            if text != message.content:
                message = HumanMessage(content=text, additional_kwargs=dict(
                    getattr(message, "additional_kwargs", None) or {}), id=getattr(message, "id", None))
        elif isinstance(message, dict) and message.get("role") == "user" and isinstance(message.get("content"), str):
            text = with_the_held_line(message["content"], held)
            if text != message["content"]:
                message = {**message, "content": text}
        changed.append(message)
    return changed


def build_project_memory_middleware(repo_root: str) -> Any:
    """Middleware that hands each call the project memory, and answers a read of what it already holds."""
    from langchain.agents.middleware import AgentMiddleware

    class ProjectMemoryMiddleware(AgentMiddleware):
        name = "ProjectMemoryMiddleware"

        def __init__(self) -> None:
            super().__init__()
            # This instance's own visit, used outside a graph run.
            self._own: dict[str, Any] = {}

        def _visit(self) -> dict[str, Any]:
            """The visit's memory: the snapshot, the files it holds, the files as the visit began.

            The memory as this visit's first call rendered it, kept byte for
            byte: rendered again on every call it changed with every write, at
            the very start of the conversation, and the server's prefix cache
            missed for everything after it on the next call. Kept in the stage's
            memory, not on this instance: every gated tool call interrupts the
            graph and the node builds the agent afresh on resume (see
            `app.agents.stage_memory`), so on the instance it lasted one write.
            Measured on one gate run, 48 calls re-read 2.4M tokens of prompt the
            server had cached, about 18 minutes, behind a memory rendered again
            with the stage's new file in the middle of it.
            """
            from app.agents.stage_memory import store

            return store(_VISIT, self._own)

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            messages = getattr(request, "messages", None)
            if not isinstance(messages, list) or not messages or not enabled():
                return handler(request)
            try:
                opening = next((str(getattr(m, "content", "") or (m.get("content") if isinstance(m, dict) else ""))
                                for m in messages), "")
                visit = self._visit()
                if visit.get("snapshot") is None:
                    from app.observability.log_context import _from_the_graph

                    stage = str(_from_the_graph()[1] or "")
                    sprint_files = _the_sprint_s_files(stage, opening)
                    if sprint_files:
                        visit["snapshot"], visit["held"], visit["request"] = render_for_a_replan(
                            repo_root, budget_for(getattr(request, "model", None)), opening, sprint_files,
                            kept_out=_kept_out_for(stage, repo_root))
                        visit["opening"] = opening
                    else:
                        visit["snapshot"], visit["held"] = render_for_a_stage(
                            repo_root, getattr(request, "model", None), opening, stage)
                    visit["files"] = dict(current(repo_root))
                    visit["stage"], visit["opened_on"] = stage, opening
                mark = visit.pop(_SUMMARISED, None)
                if mark is not None:
                    _chosen_again_at_a_summary(repo_root, visit, mark, getattr(request, "model", None))
                if visit.get("held_line") is not None:
                    messages = _naming_the_held(messages, visit["held_line"])
                if visit.get("request") is not None:
                    messages = _without_the_list(messages, visit["opening"], visit["request"])
                memory = visit["snapshot"]
                held = visit.get("held") or {}
                # Each file as this visit first held it, so a read of one that
                # changed since - by this stage's own edit - is answered with
                # the file, not "it has not changed since the start".
                first_held = visit.setdefault("first_held", {})
                for held_path, held_content in held.items():
                    first_held.setdefault(held_path, held_content)
                if held:
                    from app.tools.seen_content import remember_if_unseen

                    for held_path, held_content in held.items():
                        remember_if_unseen(held_path, held_content)
                changed = _with_memory(messages, memory, list(held)) if memory else None
                if changed is None and messages is not getattr(request, "messages", None):
                    changed = messages  # a request rewritten here, and no memory to put before it
                if changed is not None:
                    note = changes_since(visit.get("files") or {}, current(repo_root))
                    if note:
                        changed = [*changed, {"role": "user", "content": note}]
                    request = request.override(messages=changed)
            except Exception:  # noqa: BLE001 - the stage reads for itself
                logger.debug("Could not hand the project memory to a call", exc_info=True)
            return handler(request)

        def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            call = getattr(request, "tool_call", None) or {}
            args = call.get("args") or {}
            # Any read of a file the memory holds, a window of it included: a
            # third of all reads were windows (`offset`), and every one went
            # to disk for lines already in the conversation.
            visit = self._visit()
            if call.get("name") == "read_file" and visit.get("held"):
                path = str(args.get("file_path") or args.get("path") or "").strip().lstrip("/")
                held = visit["held"].get(path)
                if held is not None and _a_narrow_window(args, held):
                    return handler(request)
                # A file changed since this visit began is read for real once:
                # measured on one run, a fix stage edited a file, read it to see
                # its change, was told six times "it has not changed since",
                # and fell back to `cat`.
                changed_this_visit = (visit.get("first_held") or {}).get(path, held) != held
                if held is not None and not changed_this_visit and current(repo_root).get(path) == held:
                    from app.tools.seen_content import remember

                    remember(path, held)
                    from langchain_core.messages import ToolMessage

                    answered = visit.setdefault("first_rereads_answered", [])
                    # A file the memory holds numbered (a review's, LF.1284) has its lines there already: its
                    # numbered copy in the conversation is the copy a summary deletes and the review reads again.
                    from app.agents.review_files import NUMBERED_START

                    numbered_there = f"=== {path} {NUMBERED_START}" in str(visit.get("snapshot") or "")
                    if (first_reread_switch.enabled() and path not in answered and not numbered_there
                            and held.count("\n") + 1 <= MOST_LINES_A_FIRST_REREAD_GETS):
                        # The first time, the lines themselves: a pointer is a turn that brings nothing back.
                        answered.append(path)
                        return ToolMessage(
                            content=f"{_numbered(held)}\n\n[`{path}` is also held in the project memory at the "
                                    "start of this conversation; a second read of it is answered from there.]",
                            tool_call_id=call.get("id") or "",
                            name="read_file",
                        )
                    return ToolMessage(
                        content=f"`{path}` {HELD_POINTER}, whole and as "
                                "it is now; it has not changed since. Use it, and any lines of it, from there. "
                                + NUMBERED_LINES + POINTER_ENDS_READING,
                        tool_call_id=call.get("id") or "",
                        name="read_file",
                    )
            return handler(request)

    return ProjectMemoryMiddleware()
