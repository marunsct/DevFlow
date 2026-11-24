"""A fixer's opening request sized to what its defect touches, with the defect's own evidence first (LF.1270, 2.6).

Measured on a medium run (27 fix stages): the fixer's opening request averaged about 104,000 characters of role
prompt and project memory, 14,800 of facts, 11,000 of the product's whole API, 6,000 of the specification for its
files and 8,700 of setup, stack, where things stand and later sprints - and about 5,000 of the defect's own evidence:
what its failing tests printed, its actual behaviour, the last failing command. The round's own cause defect, raised
the same round, was in no related fixer's request. Those requests were summarised within five calls. On a small run
the request was about 52,000 characters and fitted.

The size target (`opening_target`): the opening request - project memory and request together - leaves room for
`WORKING_CALLS` working calls, each as large as one command's output may be, before the conversation is first
summarised (`ContextBudget.trigger_tokens`). A request under it is sent as it was built. Past it the request is
reshaped (`shaped`):

1. it opens with this defect's evidence: the defect, its reproduction, what was expected and what happened, its
   files, what its failing tests printed, the failures bundled with it - and, when the round raised a defect for
   one step many of this defect's tests stop at, that defect, named as the shared cause (`the_round_s_cause`);
2. then what is kept whole: how a fix is settled, earlier attempts at this defect as measured, the fixes earlier
   rounds made that must be kept, what was tried before on its cause, the specification's rulings and the fixes undone
   for a start that broke;
3. then, under `STANDING_HEADING`, the standing context cut to what the defect touches: the API only for the routes
   its failing tests call (whole when none can be read, `the_api_cut`), the facts only those about its files
   (`the_facts_cut`); and the project memory holds whole only the files its evidence names and what they import,
   the rest named to read on demand (`app.agents.project_memory`, which reads `the_evidence`).

Still past the target, whole standing sections go, largest first, each named as left out; the evidence and what is
kept whole never do. A quality fix with a size threshold, so always on and no switch: a small request is as before.
The target, the parts and the fitting are every stage's (`app.agents.request_budget`, LF.1274).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, Iterable

# The budget, the parts and their order are every stage's (LF.1274); the agent-loop fixer's request was the first
# sized by them.
from app.agents.request_budget import (
    EVIDENCE, KEPT, LEAST_OPENING_CHARACTERS, MEMORY_LEAST_SHARE, STANDING, STANDING_HEADING, WORKING_CALLS, Part,
    fit, opening_target, sections,
)

logger = logging.getLogger(__name__)

#: The section that names the round's shared cause.
CAUSE_HEADING = "--- The shared cause the same measurement raised beside this defect ---"


def the_evidence(opening: str) -> str:
    """What a reshaped request says before its standing context - the defect's evidence and what is kept; "" for a
    request that was not reshaped."""
    text = str(opening or "")
    at = text.find(STANDING_HEADING)
    return text[:at] if at >= 0 else ""


def reshaped(opening: str) -> bool:
    return STANDING_HEADING in str(opening or "")


#: Sections of a mixed part that are kept whole: the fixes earlier rounds made.
_KEPT_HEADINGS = ("--- Fixed earlier - keep these fixes",)


def split_mixed(text: str) -> list[Part]:
    """A part holding standing and kept sections (what a fix stage must leave alone) as one part per section."""
    return [Part(KEPT if section.lstrip("\n").startswith(_KEPT_HEADINGS) else STANDING, section)
            for section in sections(text)]


# --- the round's shared cause -------------------------------------------------------------------------------------

def the_round_s_cause(cycle: Any, defect_index: int, round_: int | None) -> str:
    """The section naming an open defect the same round raised for one step many tests stop at, when this defect's
    tests are among them (by test or by criterion); "" otherwise. Never raises."""
    try:
        from app.acceptance.junit import tags_in
        from app.graph.acceptance_nodes import ONE_CAUSE_MARK

        defects = list(getattr(cycle, "defects", None) or [])
        defect = defects[defect_index]
        if ONE_CAUSE_MARK in str(defect.description or ""):
            return ""
        own_tests = {str(e.get("test")) for e in defect.evidence or [] if isinstance(e, dict) and e.get("test")}
        own_criteria = {t for t in tags_in(str(defect.description or "")) if t.startswith(("AC-", "CR-"))}
        own_criteria |= set(defect.failing_criteria or [])
        for position, other in enumerate(defects):
            if position == defect_index or other.status != "open" or ONE_CAUSE_MARK not in str(other.description or ""):
                continue
            if round_ is not None and other.found_in_round is not None and other.found_in_round != round_:
                continue
            records = [e for e in other.evidence or [] if isinstance(e, dict)]
            shared_tests = own_tests & {str(e.get("test")) for e in records if e.get("test")}
            shared_criteria = own_criteria & {str(e.get("criterion")) for e in records if e.get("criterion")}
            if not (shared_tests or shared_criteria):
                continue
            which = (f"{len(shared_tests)} of this defect's failing tests" if shared_tests
                     else "tests of " + ", ".join(sorted(shared_criteria)))
            return (
                f"\n{CAUSE_HEADING}\n"
                f"The same measurement raised failure {position + 1} for one step that {which} stop at:\n"
                f"{' '.join(str(other.description).split())}\n"
                f"{str(other.actual_behavior or '').strip()[:1500]}\n"
                "That failure has a fixer of its own. While it stands, these tests stop at that step before they reach "
                "what is this defect's own: read where your failing tests stop first. If they stop there, the change "
                "this defect needs is in that one place; make it there, not in each test's own code.\n"
            )
    except Exception:  # noqa: BLE001 - the request without it
        logger.debug("Could not name the round's shared cause", exc_info=True)
    return ""


# --- the routes a defect's failing tests call ---------------------------------------------------------------------

#: A request in a runner's log, a message or a test's code: `POST /api/items`, `client.get("/api/items/3")`.
_A_LOGGED_REQUEST = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+(?:https?://[^/\s\"'`]+)?(/[^\s\"'`)]*)")
_A_REQUEST_CALL = re.compile(r"\.(?:get|post|put|patch|delete|fetch)\(\s*f?([`'\"])(.*?)\1", re.I)
_AN_ADDRESS = re.compile(r"https?://[^/\s\"'`]+(/[^\s\"'`)]*)")
_A_PLACEHOLDER = re.compile(r"\$\{[^}]*\}|\{[^}]*\}")
_AN_ID = re.compile(r"^(?::\w+|\d+|[0-9a-f]{8,}(?:-[0-9a-f]{4,})*|\*|<[^>]*>)$", re.I)
_A_SHARED_LEAD = re.compile(r"^(?:api|v\d+)$", re.I)
#: A path written in a specification's entry.
_A_PATH = re.compile(r"(?<![\w.])(/[A-Za-z0-9_{}:<>$.\-/]+)")


def resource_of(path: str) -> str:
    """The leading resource of a path, the segments every route shares kept: `/api/items/3/notes` -> `/api/items`."""
    path = re.sub(r"^https?://[^/]+", "", str(path or "").strip())
    path = re.sub(r"^(?:\$\{[^}]*\}|\{[^}]*\})+", "", path)
    path = _A_PLACEHOLDER.sub(":id", path.split("?", 1)[0].split("#", 1)[0])
    kept: list[str] = []
    for segment in (s for s in path.split("/") if s):
        if _AN_ID.match(segment):
            break
        kept.append(segment.lower())
        if not _A_SHARED_LEAD.match(segment):
            break
    if not kept or _A_SHARED_LEAD.match(kept[-1]):
        return ""
    return "/" + "/".join(kept)


def routes_called(texts: Iterable[str]) -> set[str]:
    """The resources the requests in `texts` call (a failing test's output, its defect's account of it)."""
    found: set[str] = set()
    for text in texts:
        text = str(text or "")
        paths = [m.group(1) for m in _A_LOGGED_REQUEST.finditer(text)]
        paths += [m.group(2) for m in _A_REQUEST_CALL.finditer(text)]
        paths += [m.group(1) for m in _AN_ADDRESS.finditer(text)]
        found.update(r for r in (resource_of(p) for p in paths) if r)
    return found


def _words_of(resources: Iterable[str]) -> set[str]:
    """Each resource's own name and its singular: `/api/items` -> {"items", "item"}."""
    words: set[str] = set()
    for resource in resources:
        name = resource.rsplit("/", 1)[-1]
        if len(name) < 3:
            continue
        words.add(name)
        if name.endswith("ies"):
            words.add(name[:-3] + "y")
        elif name.endswith("s"):
            words.add(name[:-1])
    return words


def the_api_cut(specification: Any, routes: set[str]) -> str:
    """The product's API block for only the routes in `routes` and the shapes and errors that name them; "" when no
    endpoint matches (the whole API is then the one to show)."""
    if specification is None or not routes:
        return ""
    from app.acceptance.api_reference import api_reference

    def entries(field: str) -> list[str]:
        return [str(e).strip() for e in getattr(specification, field, None) or [] if str(e).strip()]

    endpoints = [e for e in entries("api_and_event_contracts")
                 if {resource_of(p) for p in _A_PATH.findall(e)} & routes]
    if not endpoints:
        return ""
    words = _words_of(routes)

    def names_one(entry: str) -> bool:
        lowered = entry.lower()
        return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", lowered) for w in words) or any(
            r in lowered for r in routes)

    cut = SimpleNamespace(
        api_and_event_contracts=endpoints,
        data_contracts=[e for e in entries("data_contracts") if names_one(e)],
        error_catalogue=[e for e in entries("error_catalogue") if names_one(e)],
        interface_design=[],
    )
    left = len(entries("api_and_event_contracts")) - len(endpoints)
    block = api_reference(cut)
    if not block:
        return ""
    return block + (f"Only the routes this defect's failing tests call ({', '.join(sorted(routes))}) are listed; "
                    f"the other {left} endpoint(s), the rest of the data shapes and errors, and the page's interface "
                    "are in /docs/technical_specification.md.\n\n")


# --- the facts about a defect's files -----------------------------------------------------------------------------

_A_QUOTED_PATH = re.compile(r"`([^`\s]+)`")


def _names_one_of(line: str, files: set[str]) -> bool:
    """Whether `line` names one of `files` by path or file name, or a folder holding one."""
    names = {PurePosixPath(f).name for f in files} | files
    for quoted in _A_QUOTED_PATH.findall(line):
        quoted = quoted.strip().lstrip("./")
        if quoted in names or PurePosixPath(quoted).name in names:
            return True
        if quoted.endswith("/") and any(f.startswith(quoted) for f in files):
            return True
    return any(f in line for f in files)


#: The fact lines about one file or folder of the product, which a cut keeps only for the defect's files.
_A_FILE_S_FACT = re.compile(r"^- (?:Code the product does not run: )?`")


def the_facts_cut(text: str, files: set[str]) -> str:
    """`text` (facts, or code the product does not run) with each line about another file left out, and how many
    were; `text` as it is when `files` is empty."""
    if not files or not text:
        return text
    kept: list[str] = []
    left = 0
    for line in text.split("\n"):
        about_a_file = bool(_A_FILE_S_FACT.match(line)) or line.startswith("- Code the product does not run:")
        if about_a_file and not _names_one_of(line, files):
            left += 1
            continue
        kept.append(line)
    if not left:
        return text
    cut = "\n".join(kept)
    tail = f"({left} more fact(s) about other files left out.)\n"
    return cut + ("" if cut.endswith("\n") else "\n") + tail


def split_facts(text: str, files: set[str]) -> list[Part]:
    """The facts block as parts: the specification's rulings and the fixes undone for a start that broke, kept whole
    (they bind every stage); the rest standing, cut to `files`."""
    from app.agents import specification_rulings, start_breaks

    binding = (specification_rulings.HEADING, start_breaks.HEADING)
    return [Part(KEPT, section) if section.lstrip("\n").startswith(binding)
            else Part(STANDING, section, cut=the_facts_cut(section, files))
            for section in sections(text) if section]


def the_files_it_touches(root: str | Path | None, evidence: str, named: Iterable[str] = ()) -> set[str]:
    """The product files the defect's evidence names, and the files those import; with `named` (its files)."""
    files = {str(f).strip().lstrip("./") for f in named if str(f).strip()}
    if not root:
        return files
    try:
        from app.agents import memory_slices, project_memory

        found = memory_slices.the_slice(root, evidence, project_memory.current(root))
        return files | set(found or ())
    except Exception:  # noqa: BLE001 - its named files alone
        return files


# --- the shape ----------------------------------------------------------------------------------------------------

def shaped(parts: list[Part], *, target: int, memory: int, cause: str = "") -> str:
    """The request past its target (`request_budget.fit`): the evidence and `cause` first, what is kept whole next,
    the standing context cut and, while the request and its memory are still past `target`, whole standing sections
    left out, largest first. `memory`: the characters the project memory will hold at least."""
    return fit(parts, target=target, memory=memory, cause=cause).text


def specification_cut(specification: Any, text: str, observed: Iterable[str]) -> str | None:
    """`text` (a request's part holding the product's whole API) with that API cut to the routes `observed` (what
    the failing tests printed, the defect's account of them) call; None when no route can be read, no endpoint
    matches, or `text` does not hold the whole API (the whole API is then the one shown)."""
    try:
        from app.acceptance.api_reference import api_reference

        whole = api_reference(specification)
        if not whole or whole not in str(text or ""):
            return None
        cut = the_api_cut(specification, routes_called(observed))
        return text.replace(whole, cut, 1) if cut else None
    except Exception:  # noqa: BLE001 - the whole API
        logger.debug("Could not cut the API to the defect's routes", exc_info=True)
        return None


__all__ = [
    "CAUSE_HEADING", "EVIDENCE", "KEPT", "LEAST_OPENING_CHARACTERS", "MEMORY_LEAST_SHARE", "Part", "STANDING",
    "STANDING_HEADING", "WORKING_CALLS", "opening_target", "reshaped", "resource_of", "routes_called", "sections",
    "shaped", "specification_cut", "split_facts", "split_mixed", "the_api_cut", "the_evidence", "the_facts_cut",
    "the_files_it_touches", "the_round_s_cause",
]
