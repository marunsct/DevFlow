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
from typing import Any, Callable

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
_SKIPPED_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "go.sum"}

_LOCK = threading.Lock()
#: (root, relative path) -> (modification time, size, content).
_FILES: dict[tuple[str, str], tuple[int, int, str]] = {}


def _ignored(parts: tuple[str, ...]) -> bool:
    from app.tools.repository import IGNORED_DIRECTORIES

    return any(part in IGNORED_DIRECTORIES or part in (".harness", ".agent-home", "test-results") for part in parts)


def _candidates(root: Path) -> list[str]:
    found: list[str] = []
    for folder, directories, files in os.walk(root):
        relative_folder = Path(folder).relative_to(root)
        directories[:] = [d for d in directories if not _ignored((*relative_folder.parts, d))]
        for name in files:
            if name in _SKIPPED_NAMES or not name.endswith(_TEXT_SUFFIXES) or name.startswith(".project-"):
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


def map_of(files: dict[str, str]) -> str:
    """For each file, the lines that define something - its functions, classes and types - one file a line.

    A large project's files do not all fit; naming the ones left out told a
    stage nothing about what they hold, so it read them to find out. The
    lines that define something are most of what a reader needs to know
    which one to open (the idea of Aider's repository map, without a parser
    per language).
    """
    lines: list[str] = []
    used = 0
    for path in sorted(files):
        found = []
        for line in files[path].splitlines():
            if _DEFINES.match(line):
                found.append(" ".join(line.strip().rstrip("{:").split())[:120])
                if len(found) >= MOST_DEFINITIONS_PER_FILE:
                    break
        if not found:
            continue
        entry = f"- {path}: " + " | ".join(found)
        if used + len(entry) > MOST_MAP_CHARACTERS:
            break
        lines.append(entry)
        used += len(entry)
    return "\n".join(lines)


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


def render(repo_root: str | Path, budget_characters: int, focus: str = "") -> tuple[str, dict[str, str]]:
    """The memory as text within `budget_characters`, and the files it holds by path."""
    files = current(repo_root)
    if not files or budget_characters <= 0:
        return "", {}
    held: dict[str, str] = {}
    parts: list[str] = []
    from app.agents.canonical_memory import enabled as canonical_order

    canonical = canonical_order()
    after_the_rest: list[str] = []
    left_out: list[str] = []
    used = 0
    try:
        from app.stacks.scaffold import folders_nothing_serves

        unserved = tuple(folders_nothing_serves(repo_root))
    except Exception:  # noqa: BLE001 - the order stands as it was
        unserved = ()
    for path in _ranked(files, focus, unserved):
        text = files[path]
        if _RECORDS.match(path):
            left_out.append(path)
            continue
        block = f"=== {path} ===\n{text.rstrip()}\n"
        if len(text) > LARGEST_FILE_CHARACTERS and path.endswith(".md"):
            # Too large to hold whole: its outline and the sections this
            # stage's request points at, so it is not read window by window.
            digest = digest_of(text, focus, min(LARGEST_FILE_CHARACTERS, budget_characters - used))
            if digest:
                block = f"=== {path} (outline and the sections this request points at; read others by line) ===\n{digest}\n"
                # Chosen by the request's words, so after what every request shares (plan PX.3).
                (after_the_rest if canonical else parts).append(block)
                used += len(block)
                continue
        if len(text) > LARGEST_FILE_CHARACTERS or used + len(block) > budget_characters:
            left_out.append(path)
            continue
        parts.append(block)
        held[path] = text
        used += len(block)
    parts += after_the_rest
    if not parts:
        return "", {}
    head = (
        "[Project memory: the workflow's documents and the project's files as they are now, kept current "
        "by the harness. Use them as they are here; read a file only if it is named at the end as not "
        "included.]\n\n"
    ) + where_things_stand(repo_root, files)
    tail = ("\nNot included here (read when needed): " + ", ".join(left_out) + "\n") if left_out else ""
    shapes = map_of({path: files[path] for path in left_out if not path.startswith("docs/")})
    if shapes:
        tail += "\nWhat those files define (read one when you need its body):\n" + shapes + "\n"
    return head + "\n".join(parts) + tail, held


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
                lines.append(f"  ... {more} more changed lines; `grep` finds any text in the file")
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

            return store("project_memory", self._own)

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            messages = getattr(request, "messages", None)
            if not isinstance(messages, list) or not messages or not enabled():
                return handler(request)
            try:
                opening = next((str(getattr(m, "content", "") or (m.get("content") if isinstance(m, dict) else ""))
                                for m in messages), "")
                visit = self._visit()
                if visit.get("snapshot") is None:
                    visit["snapshot"], visit["held"] = render(repo_root, budget_for(getattr(request, "model", None)), opening)
                    visit["files"] = dict(current(repo_root))
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

                    return ToolMessage(
                        content=f"`{path}` {HELD_POINTER}, whole and as "
                                "it is now; it has not changed since. Use it, and any lines of it, from there. "
                                + NUMBERED_LINES + POINTER_ENDS_READING,
                        tool_call_id=call.get("id") or "",
                        name="read_file",
                    )
            return handler(request)

    return ProjectMemoryMiddleware()
