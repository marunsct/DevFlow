"""Safe repository-access helpers for workflow agents.

A beginner-friendly explanation: these tools intentionally do not expose a full
shell. Instead, the workflow gives agents a few narrow, auditable operations:
list files, read a selected file, search text, inspect dependency metadata, write
only within the approved artifact directory, and run a small allowlist of safe
validation commands. That reduces accidental secrets exposure and prevents a role
agent from wandering outside the project boundary.
"""

from __future__ import annotations

import re
import json
import os
import subprocess
import logging
import threading
import tomllib
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from app.analysis.walk import files_under

logger = logging.getLogger(__name__)


class RepositoryToolError(ValueError):
    """Raised when a repository tool violates the workflow's safe boundaries.

    Why this exists: the workflow needs one clear failure type for path escapes,
    invalid file requests, or blocked commands. That gives agents and tests a
    precise way to handle unsafe activity instead of a generic Python exception.
    """


def _normalize_repo_root(repo_root: str | Path) -> Path:
    """Resolve the repository root and reject unsafe paths before any read or write.

    This helper is the first safety gate. If the caller passes a path that does not
    exist or is not a directory, the workflow should fail before trying to read any
    file. This keeps the tools deterministic and avoids ambiguous behavior.
    """
    root = Path(repo_root).expanduser().resolve()
    if not root.exists():
        raise RepositoryToolError(f"Repository root does not exist: {root}")
    if not root.is_dir():
        raise RepositoryToolError(f"Repository root is not a directory: {root}")
    return root


def _assert_within_repo(repo_root: Path, target: Path) -> Path:
    """Ensure a file path stays inside the project root before reading or writing it.

    In plain terms: if the target is outside the repository, the tool refuses to
    continue. This prevents path traversal bugs such as ../secret.txt or writes to
    a sibling folder that was never meant to be touched.
    """
    resolved = target.resolve()
    repo_root_resolved = repo_root.resolve()
    if repo_root_resolved not in resolved.parents and resolved != repo_root_resolved:
        raise RepositoryToolError(
            f"Path escapes the repository boundary: {target}. Allowed root: {repo_root_resolved}"
        )
    return resolved


_MUTATION_LOCK = threading.RLock()
"""Serialises every write and edit, because tool calls in one turn run in parallel.

A model can ask for several gated calls in a single turn, and LangGraph executes
them concurrently. `edit_approved_artifact` is a read-modify-write: it reads the
whole file, replaces one passage, and writes the whole file back. Two of those
running at once against the same file both read the original, and the second to
finish writes over the first one's change - which is then *reported as applied*,
because each call did succeed on the copy it was holding.

That is the worst failure shape available: silent, and invisible to the agent,
which believes all of its corrections landed. A real turn asked for seven edits
to one specification; without this, at most one of them would have survived.

One lock for all mutations rather than one per path: edits are rare next to
reads, so the contention costs nothing, and a per-path registry would have to
grow without bound to avoid the same race in its own bookkeeping.
"""


def _repo_relative_path(repo_root: Path, relative_path: str | Path) -> Path:
    """Interpret a model-supplied path the way the model means it.

    Models write `/docs/spec.md` for a file at the top of the workspace. They are
    not asking for the filesystem root; the leading slash is how you say "from the
    root of the project" in every document they have ever read.

    `write_approved_artifact` already stripped that anchor, so writes worked.
    Reads and edits did not, and `root / Path("/docs/spec.md")` is `/docs/spec.md`
    in pathlib - the root is discarded entirely. A real run had an agent write
    `docs/technical_specification_v2.md` successfully and then fail every edit to
    the same file it had just created, because it addressed it the same way both
    times and only one of the two tools understood it.

    An absolute path that genuinely lands inside the workspace is kept as-is
    (made relative to the root); anything else has its anchor stripped and is
    read as workspace-relative. Traversal is unaffected: the joined result is
    still checked by `_assert_within_repo`, and a path that used to escape the
    root now resolves under it instead, which is the safer of the two outcomes.
    """
    candidate = Path(str(relative_path)).expanduser()
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(repo_root.resolve())
        except ValueError:
            candidate = candidate.relative_to(candidate.anchor)

    # The workspace's own absolute path, with its leading slash gone.
    #
    # An agent handed the host path writes it verbatim; refused, it drops the
    # slash and tries again, and `/app/data/workspaces/<run>/index.html` becomes
    # the relative `app/data/workspaces/<run>/index.html`. That is a real path
    # inside the workspace, so it was created - a mirror of the host layout,
    # nested inside the workspace it describes. Measured on one run, where
    # it also pinned `app` as the project directory.
    # Any trailing portion of it, not only the whole thing: refused once, the
    # agent drops another leading component and retries, so
    # `data/workspaces/<run>/index.html` arrives next. The match is anchored on
    # the workspace directory's own name - which carries the run id and cannot
    # occur by accident - so a project with a real `data/` folder is untouched.
    root_parts = repo_root.resolve().parts[1:]  # drop the anchor
    parts = candidate.parts
    if root_parts:
        workspace_name = root_parts[-1]
        for index, part in enumerate(parts):
            if part != workspace_name:
                continue
            prefix = parts[: index + 1]
            if prefix == root_parts[-len(prefix):]:
                remainder = parts[index + 1:]
                return Path(*remainder) if remainder else Path(".")
            break
    return candidate


IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".next", ".nuxt",
    "dist", "build", ".terraform", ".gradle", "target", ".langchain", "site-packages",
    # The sandbox points HOME here so npm, pip and cargo caches land inside the
    # workspace instead of a directory shared by every run (see
    # `sandbox._child_environment`). That makes them ours, and they are not the
    # product: on one run one `npm install` left 26 `_cacache` blobs with
    # sha512 filenames, and a listing of the workspace was mostly those rather
    # than the application.
    ".agent-home",
})
"""Directories never descended into."""

#: Directories a tool fills - a package manager, an interpreter, version
#: control, the sandbox's own caches. Nothing in them is written by hand.
#: `dist`, `build`, `target` and a bare `env` are left out: a project may keep
#: sources under those names.
INSTALLED_DIRECTORIES = frozenset({
    "node_modules", ".venv", "venv", "site-packages", "__pycache__",
    ".git", ".hg", ".svn", ".agent-home", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".gradle", ".terraform",
})


def _installed_by_a_tool(root: Path, target: Path, *, done: str = "written") -> str | None:
    """The refusal for changing a file inside a directory a tool fills, or None.

    Measured on one run: `npm install jsdom` was refused - the brief ruled out
    product dependencies, and the refusal said `npm i -D` for a package only the
    tests use - and the backend specialist wrote its own `jsdom` instead:
    `node_modules/jsdom/package.json` and `node_modules/jsdom/index.js`, both
    accepted. The tests would then have run against a counterfeit nobody
    installed, which the next real install overwrites.
    """
    try:
        parts = target.relative_to(root).parts
    except ValueError:
        return None
    inside = next((part for part in parts[:-1] if part in INSTALLED_DIRECTORIES), None)
    if inside is None:
        return None
    shown = target.relative_to(root).as_posix()
    return (
        f"'{shown}' is inside `{inside}`, which a tool fills - a package manager, an "
        "interpreter or version control - and nothing in it is written by hand. A "
        "file put there is overwritten at the next install and makes the code run "
        "against something nobody installed. Install the package properly (`npm i -D "
        "<pkg>` or its equivalent for something only the tests use), or change the "
        f"code so it does not need it. Nothing was {done}."
    )

SECRET_FILE_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
    "*.keystore", "credentials", "credentials.*", ".npmrc", ".pypirc", ".netrc",
    "*.sqlite", "*.sqlite3", "*.db", ".htpasswd", "service-account*.json",
)
"""Filenames withheld from agents regardless of where they sit.

An agent that can list and read repository files can hand the contents to the
model, which means into the provider's logs and any tracing backend. Credential
material must never enter that path, so it is excluded at the traversal layer
rather than left to prompt instructions."""

MAX_READABLE_FILE_BYTES = 512 * 1024
"""Files larger than this are listed but not read, so one oversized file cannot
exhaust memory or the model's context."""


def is_secret_path(path: Path) -> bool:
    """Whether a path looks like credential material."""
    name = path.name
    return any(fnmatch(name, pattern) for pattern in SECRET_FILE_PATTERNS)


#: The harness's own bookkeeping, written into the workspace beside the work.
#: None of it is the product and none of it is evidence, so no listing, no
#: digest, no cross-file check and no line count should ever see it.
#:
#: `.project-directory` and `.project-stack` were already invisible by
#: accident - nothing reads a dotfile with no suffix - and `.project-memory
#: .json` was not, because it has one. It appeared at the top of the first
#: digest that carried it, which is exactly where a stage looks first.
HARNESS_FILES = frozenset({
    ".project-directory", ".project-stack", ".project-memory.json", ".work-order-files.json",
})

#: Which delegated task each file of the current milestone belongs to, written
#: when the plan is dispatched. See `record_work_order_files`.
WORK_ORDER_FILES = ".work-order-files.json"

#: Directories, relative to the workspace root, holding the harness's own
#: records rather than the product's files.
#:
#: `docs/stage_summaries/` gets one file per gated stage, so a run accumulates
#: dozens: every specialist task, every test round, every defect fix. They exist
#: for the dashboard, and they were landing in the digest that is prepended to
#: every model call - sorted first, because `docs/` sorts before the project
#: directory, against a cap of `workspace_digest.MAX_FILES` files. A run far
#: enough along filled the digest with its own bookkeeping and pushed out the
#: product files the digest exists to show.
#:
#: Same reasoning as `HARNESS_FILES`, one level up. Written, served to the UI,
#: and invisible to the agents.
#: `.harness/` holds the project contract and the acceptance lock
#: (`app.stacks.contract`, `app.acceptance.lock`): the harness's record of what
#: it set up and froze, which no stage may read as the product or change.
HARNESS_DIRECTORIES = frozenset({"docs/stage_summaries", ".harness"})


#: What a search for a file by name, made for a stage, skips: every directory
#: never descended into, and the harness's own records. The listings already
#: hid `.harness/`; the searches that suggest or resolve a path by its name did
#: not. Measured on one run: the technical lead asked for the locked acceptance
#: spec under an invented `/home/user/` prefix, which resolves when one file
#: carries the name - and two did, the spec and the harness's private copy of
#: it under `.harness/`. Four reads were refused, each offering the copy.
NOT_SEARCHED_FOR_A_STAGE = IGNORED_DIRECTORIES | {".harness"}


def _is_harness_directory(repo_root: Path, directory: Path) -> bool:
    """Whether this directory holds the harness's records rather than the product's."""
    try:
        relative = directory.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    return relative in HARNESS_DIRECTORIES


#: The harness's momentary files in a workspace: the parse probe written beside
#: a file so its imports resolve (`app.3f9c2a1b.tmp.js`, see
#: `app.analysis.javascript_parse`), and the staging copy of an atomic write of
#: one of `HARNESS_FILES` (`..project-memory.json.k3j2x9.tmp`). Each lives for
#: a moment; in parallel mode another stage's listing can catch it. One run's
#: workspace digest listed `src/main.d7cebffc.tmp.js (2 lines)`, and a stage
#: spent a call trying to read it.
_A_PARSE_PROBE = re.compile(r"^.+\.[0-9a-f]{8}\.tmp\.[A-Za-z0-9]+$")


def is_harness_momentary(name: str) -> bool:
    """Whether a file name is one of the harness's momentary files."""
    return bool(_A_PARSE_PROBE.match(name)) or (
        name.endswith(".tmp") and any(f"{kept}." in name for kept in HARNESS_FILES)
    )


def is_harness_bookkeeping(path: Path) -> bool:
    """Whether this file is the harness's own, not the product's."""
    return path.name in HARNESS_FILES or is_harness_momentary(path.name)


def _iter_repo_files(repo_root: Path, allow_subdirectories: bool = True) -> list[Path]:
    """List project files, pruning noise directories and credential files.

    The previous implementation filtered on `path.name in ignored_names` while
    iterating `rglob("*")`. That only skipped the directory *entry*: rglob still
    descended into it, so every file under `.git/`, `.venv/` and `node_modules/`
    was still returned. This walks with `os.walk` and prunes `dirnames` in place,
    which actually stops the descent.
    """
    files: list[Path] = []

    if not allow_subdirectories:
        for path in sorted(repo_root.iterdir()):
            if path.is_file() and not is_secret_path(path) and not is_harness_bookkeeping(path):
                files.append(path)
        return files

    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Pruning in place is what stops os.walk descending further.
        # A test runner's own output goes with the dependency directories:
        # `test-results/.last-run.json` and `playwright-report/index.html`
        # are not the product, and on one run the first appeared in the
        # digest every stage reads. `_RUNNER_OUTPUT_DIRECTORIES` is the same
        # set `sandbox._written_since` already excludes.
        from app.tools.sandbox import _RUNNER_OUTPUT_DIRECTORIES

        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in IGNORED_DIRECTORIES
            and d not in _RUNNER_OUTPUT_DIRECTORIES
            and not d.startswith(".cache")
            and not _is_harness_directory(repo_root, current / d)
        )
        for filename in sorted(filenames):
            candidate = current / filename
            if is_secret_path(candidate) or is_harness_bookkeeping(candidate):
                continue
            if candidate.is_file():
                files.append(candidate)
    return files


def list_repository_files(repo_root: str | Path, allow_subdirectories: bool = True) -> list[str]:
    """List repository files within the project boundary.

    Purpose:
        Help a workflow agent understand the project structure before planning or
        editing work.

    Inputs:
        repo_root: the repository root to inspect.

    Returns:
        A list of relative file paths such as "src/app/main.py".

    Errors:
        RepositoryToolError if the repository root is invalid or the traversal fails.

    Safety model:
        The tool ignores repository metadata and dependency-heavy folders so the
        agent sees project code rather than hidden machine state.
    """
    root = _normalize_repo_root(repo_root)
    relative_files = []
    for path in _iter_repo_files(root, allow_subdirectories=allow_subdirectories):
        relative_path = path.relative_to(root).as_posix()
        relative_files.append(relative_path)
    return relative_files


def read_text_file(repo_root: str | Path, relative_path: str) -> str:
    """Read a selected text file from the repository.

    Purpose:
        Inspect one specific file without exposing the full filesystem.

    Inputs:
        repo_root: the repository root.
        relative_path: file path relative to the repo root, such as "src/app/config.py".

    Returns:
        The file contents as UTF-8 text.

    Errors:
        RepositoryToolError if the path is outside the repo, missing, or not a file.

    Safety model:
        The file must remain inside the repository root; the tool refuses traversal
        such as "../outside.txt".
    """
    root = _normalize_repo_root(repo_root)
    target = (root / _repo_relative_path(root, relative_path)).resolve()
    _assert_within_repo(root, target)
    if is_secret_path(target) or any(part in IGNORED_DIRECTORIES for part in target.parts):
        raise RepositoryToolError(
            f"Refusing to read '{relative_path}': it matches a credential or excluded-directory "
            "pattern. Secrets must never be placed in a model prompt."
        )
    if not target.exists():
        raise RepositoryToolError(
            f"File does not exist within the repository: {relative_path}"
            + (
                _document_manifest.not_rendered_yet(relative_path)
                or _where_that_name_actually_is(root, relative_path)
            )
        )
    if not target.is_file():
        raise RepositoryToolError(
            f"Requested path is not a file: {relative_path}"
            + _what_that_directory_holds(target)
        )
    from app.tools.seen_content import record_state, remember

    content = target.read_text(encoding="utf-8")
    # So a later edit whose `find` no longer matches can say the file changed
    # underneath it, rather than leaving the model to infer that from a diff.
    # See `app.tools.seen_content`.
    remember(relative_path, content)
    # And so an edit that returns the file to how it was found is recognised.
    # Without this the starting state is absent from the history and the first
    # thing a stage undoes is the one thing it is not told about.
    record_state(relative_path, content)
    return content


#: Paths to name when a read misses. Enough to place the file, short of a list.
_MAX_SUGGESTIONS = 4


def _where_that_name_actually_is(root: Path, wanted: str) -> str:
    """" There is a file of that name at ...", or "". Never raises.

    `read_file` has had this since one run, where 56 of 72 failed reads
    named a file that was in the workspace under a different path. This is the
    other read tool, and it had none of it - the third piece of machinery
    `read_repository_file` turned out to be missing, after the repeat notice
    and the span tracking.

    Measured across three runs: each one
    failed a `read_repository_file` of `README.md` at the workspace root while
    the project's README sat one directory down.
    """
    name = wanted.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if not name:
        return ""
    try:
        found = [
            candidate.relative_to(root).as_posix()
            for candidate in files_under(root, NOT_SEARCHED_FOR_A_STAGE, name)
            if candidate.is_file()
            and not any(part in NOT_SEARCHED_FOR_A_STAGE for part in candidate.parts)
        ]
    except Exception:  # noqa: BLE001 - a hint must never replace the error
        return ""
    if not found:
        return ""
    shown = ", ".join(sorted(found)[:_MAX_SUGGESTIONS])
    more = "" if len(found) <= _MAX_SUGGESTIONS else f" and {len(found) - _MAX_SUGGESTIONS} more"
    return f" There is a file of that name at {shown}{more}."


def _what_that_directory_holds(target: Path) -> str:
    """" It is a directory containing ...", or "". Never raises.

    A read that lands on a directory is asking what is in it; see
    `app.agents.workspace_backend._what_is_in_it`, which answers the same
    question for the other read tool.
    """
    try:
        if not target.is_dir():
            return ""
        entries = sorted(
            f"{child.name}/" if child.is_dir() else child.name
            for child in target.iterdir()
            if child.name not in IGNORED_DIRECTORIES
        )
    except Exception:  # noqa: BLE001
        return ""
    if not entries:
        return " It is a directory, and it is empty."
    shown = ", ".join(entries[:30])
    more = "" if len(entries) <= 30 else f" and {len(entries) - 30} more"
    return f" It is a directory containing: {shown}{more}. Read one of those."


def read_text_lines(
    repo_root: str | Path,
    relative_path: str,
    *,
    start_line: int = 1,
    line_count: int | None = None,
) -> dict[str, object]:
    """Read a slice of a file rather than the whole thing.

    Purpose:
        Let an agent look at one section of a large document without pulling the
        entire file into its context. The technical specification on a real run
        reached 71KB - roughly 18,000 tokens - and reading it whole to change one
        paragraph crowded out everything else the agent needed to hold.

    Inputs:
        start_line: 1-based, inclusive.
        line_count: how many lines to return; the rest of the file when omitted.

    Returns:
        The requested lines, plus where they sit in the file, so the agent can
        ask for the next slice without guessing.

    Errors:
        RepositoryToolError for the same reasons `read_text_file` raises, and for
        a `start_line` past the end of the file.
    """
    text = read_text_file(repo_root, relative_path)
    # Reported back in workspace-relative form, never as the model typed it: the
    # dashboard reads the path out of the result to label the row, and a raw
    # `/docs/spec.md` there would be a path that exists nowhere.
    reported_path = _repo_relative_path(_normalize_repo_root(repo_root), relative_path).as_posix()
    lines = text.splitlines()
    total = len(lines)

    if start_line < 1:
        raise RepositoryToolError(f"start_line must be 1 or greater, got {start_line}.")
    if total and start_line > total:
        raise RepositoryToolError(
            f"'{relative_path}' has {total} lines, so line {start_line} is past the end."
        )
    if line_count is not None and line_count < 1:
        raise RepositoryToolError(f"line_count must be 1 or greater, got {line_count}.")

    begin = start_line - 1
    end = total if line_count is None else min(total, begin + line_count)
    selected = lines[begin:end]

    return {
        "path": reported_path,
        "start_line": start_line,
        "end_line": begin + len(selected),
        "total_lines": total,
        "has_more": end < total,
        "content": "\n".join(selected),
    }


_READ_LINE_NUMBER = re.compile(r"^[ \t]*>?[ \t]*\d+[ \t]*(?:[|:][ \t]?|[ \t])")
"""A line-number gutter, in every format this harness puts in front of a line.

Three producers, three spellings, and the pattern used to know one:

    `1  def add(a, b):`      deepagents' `read_file`      matched
    `   21 | const url =`    this module's own            digits matched, `| ` left behind
    `>   21 | const url =`   ditto, nearest-line marker   same
    `21: content`            the filesystem tool's docs   not matched at all

The second is the one that mattered. `_closest_passage` quotes the file back
with a `NN | ` gutter and a `>` marker and says "Copy the passage from there
exactly"; the model does exactly that; the stripper removed the digits and
left the pipe, so the repaired candidate still did not match and the edit
failed again. The harness was teaching the model to send text it would then
reject - the self-inflicted half of the 247 "Could not find that text"
failures swept across 45 transcripts on 2026-09-19.

Safe to widen because this only runs on a `find` that has already failed to
match, and every repaired candidate must still match exactly once before it
is used. A line of real code reading `2 | x` is not at risk unless stripping
it happens to produce a unique match, and then the original would have
matched too."""


def _without_read_line_numbers(wanted: str) -> str | None:
    """`wanted` with `read_file`'s line-number prefixes removed, or None.

    The read tool decorates its output with line numbers and the edit tool
    demands byte exactness, so an agent that copies a passage out of a read is
    copying something the file does not contain. It shows up as a `find` whose
    first line is clean - the agent stripped the prefix it could see - and whose
    later lines each begin `27  `, `124      `, and so on.

    Observed on one run in three of four consecutive failed edits, against
    `index.html`, `styles.css` and `app.js` alike. Nothing about the agent's
    intent was wrong; it was quoting our own output back at us.

    Returns None when no line carries a prefix, so the caller can tell "nothing
    to try" from "try this".
    """
    lines = wanted.splitlines()
    stripped: list[str] = []
    removed = 0
    for line in lines:
        found = _READ_LINE_NUMBER.match(line)
        if found:
            stripped.append(line[found.end():])
            removed += 1
        else:
            stripped.append(line)
    return "\n".join(stripped) if removed else None


#: A gutter exactly as a read prints it - the number, then two spaces, a tab
#: or a bar - so the line's own indentation after it is kept. The digits are
#: captured to check they count up the way a read's do.
_COPIED_GUTTER = re.compile(r"^[ \t]*>?[ \t]*(\d+)(?:\t| {2}| ?\| ?)")


def _gutter_stripped(text: str) -> str:
    """`text` with a read's gutter taken off each line that has one, indentation kept."""
    stripped = []
    for line in text.splitlines():
        found = _COPIED_GUTTER.match(line)
        stripped.append(line[found.end():] if found else line)
    return "\n".join(stripped) + ("\n" if text.endswith("\n") else "")


def _content_without_a_copied_gutter(content: str, first_line: int | None = None) -> str:
    """`content` with `read_file`'s line numbers removed, when it plainly carries them.

    Plainly: every line with text in it starts with a gutter, and the numbers
    count up one at a time - or, for one line, it is the number of the line
    being replaced. Code whose lines begin with numbers does not count up from
    the line it lands on. Measured on one run: five edits to a page each wrote
    a gutter into it, and the page showed "11", "20", "21", "22" and "24" in
    front of its heading, its filters and its list.
    """
    numbers = []
    for line in content.splitlines():
        if not line.strip():
            continue
        found = _COPIED_GUTTER.match(line)
        if not found:
            return content
        numbers.append(int(found.group(1)))
    if not numbers:
        return content
    if len(numbers) == 1:
        if first_line is None or numbers[0] != first_line:
            return content
    elif any(later - earlier != 1 for earlier, later in zip(numbers, numbers[1:])):
        return content
    return _gutter_stripped(content)


def _the_replacement_without_its_find_s_gutter(find: str, replace: str) -> str:
    """`replace` without the line numbers its `find` was matched without. See below.

    The edit tool forgave a `find` copied with `read_file`'s line numbers and
    then wrote `replace` - copied the same way - as it came: one run's edit was
    told "Matched after removing the line numbers from your text" while its
    `11  <h1 ...>` went into the page. Only when every line of `replace` with
    text in it carries a gutter, as every line of the copied `find` did.
    """
    if _without_read_line_numbers(find) is None:
        return replace
    lines = [line for line in replace.splitlines() if line.strip()]
    if not lines or not all(_COPIED_GUTTER.match(line) for line in lines):
        return replace
    return _gutter_stripped(replace)


def _without_double_escaping(wanted: str) -> str | None:
    """`wanted` with doubled backslashes collapsed, or None if there are none.

    A model writing a tool call in JSON has to escape a backslash, and one that
    is already thinking about escaping tends to escape it twice. The result is a
    `find` of `\\\\n` against a file holding `\\n` - three characters searched
    for where two exist.

    Observed on one run fixing the very corruption this describes: a test
    file contained a literal backslash-n where a newline belonged, and the agent
    was stopped as a loop after five identical attempts to delete it, each one
    over-escaped the same way.

    Like the other fallbacks, this only proposes a candidate; the caller still
    requires it to match exactly once.
    """
    collapsed = wanted.replace("\\\\", "\\")
    return collapsed if collapsed != wanted else None


def _transcription_repairs(wanted: str) -> list[tuple[str, str]]:
    """Every repaired spelling of `wanted`, including composed ones.

    The repairs are independent faults and a model commits them together. A
    `find` can be double-escaped *and* JSON-escaped at once, and applying
    either one alone leaves the other in place - so both candidates miss and
    the agent is told only that its text is not in the file.

    Returns candidates in order of confidence, cheapest first. Each is still
    required by the caller to match exactly once, so composing forgives more
    transcription without forgiving any ambiguity: the exactness guarantee is
    unchanged.

    Bounded at one pass of each repair in each order. A fixed point is not
    worth chasing - a `find` needing three rounds of unescaping is not a
    transcription slip.
    """
    seen = {wanted}
    out: list[tuple[str, str]] = []

    def add(candidate: str | None, explanation: str) -> str | None:
        if candidate is None or candidate in seen:
            return None
        seen.add(candidate)
        out.append((candidate, explanation))
        return candidate

    doubled = add(
        _without_double_escaping(wanted),
        "Matched after collapsing doubled backslashes in your text. A backslash "
        "needs escaping once in JSON, not twice.",
    )
    jsoned = add(
        _without_json_escaping(wanted),
        "Matched after reading your text as JSON escapes - your `find` carried "
        "\\n and \\\" where the file has a real newline and a plain quote. The "
        "tool call is already JSON; put the literal text in `find`, not an "
        "escaped copy of it.",
    )
    # Both faults at once, in either order. `\\\\n` needs the collapse first and
    # then the decode; a payload escaped the other way round needs the reverse.
    if doubled is not None:
        add(
            _without_json_escaping(doubled),
            "Matched after collapsing doubled backslashes and then reading the "
            "result as JSON escapes - your `find` was escaped twice over. Put the "
            "literal text in `find`, exactly as the file has it.",
        )
    if jsoned is not None:
        add(
            _without_double_escaping(jsoned),
            "Matched after reading your text as JSON escapes and collapsing the "
            "doubled backslashes left behind. Put the literal text in `find`, "
            "exactly as the file has it.",
        )
    add(
        _without_read_line_numbers(wanted),
        "Matched after removing the line numbers from your text. Those come from "
        "`read_file`'s output and are not in the file - strip them before editing.",
    )
    # One stray quote at the end, from closing the JSON string a character
    # late. Measured on one run: `specialist_ui_ux_0` sent an 85-line
    # passage that matched the file exactly except for a trailing `"`, twice,
    # and the diff correctly reported `you sent: });"` against
    # `file has: });`. Every line but the last was right.
    #
    # Safe for the same reason as every repair here: it is offered only after
    # the original has failed, and the caller still requires the candidate to
    # match exactly once. A passage that really ends in a quote already
    # matched.
    if wanted[-1:] in {'"', "'"}:
        add(
            wanted[:-1],
            "Matched after dropping one trailing quote from your text. The tool "
            "call is already JSON - `find` holds the literal passage, so it does "
            "not need a closing quote of its own.",
        )
    # Line numbers must be stripped AFTER the escapes are decoded, not before.
    # `_without_read_line_numbers` works line by line, and a passage whose
    # newlines are still the two characters `\n` is one long line to it - so it
    # strips the first number and leaves every other one in place. Applying it
    # to each decoded candidate is what handles a passage copied out of a read
    # and then escaped, which is the ordinary way this arrives.
    for candidate in list(seen - {wanted}):
        add(
            _without_read_line_numbers(candidate),
            "Matched after decoding your escapes and then removing `read_file`'s "
            "line numbers. Copy the passage from the file itself, without the "
            "numbers and without escaping it.",
        )
    return out


def _without_json_escaping(wanted: str) -> str | None:
    """`wanted` with JSON escape sequences interpreted, or None if it has none.

    The mirror image of `_without_double_escaping`. That one is for a `find`
    carrying `\\\\n` against a file holding a literal backslash-n. This one is for
    a `find` carrying `\\n` and `\\"` against a file holding a real newline and a
    plain quote - a model that escaped its payload as if it were writing the
    JSON string by hand, one level too deep.

    Observed on one run at 10:28: the agent read `todo-app/package.json`,
    then issued the same edit three times, each with
    `'"devDependencies": {\\n    \\"jest\\": ...'` where the file holds a newline
    and unescaped quotes. Collapsing doubled backslashes does nothing for it -
    there are none - so every fallback missed and the agent had no signal that
    its transcription rather than its intent was wrong.

    Only the unambiguous sequences are decoded. `\\b` and `\\f` are left alone
    because a file is far likelier to contain that text than those control
    characters, and an unknown escape is left intact rather than guessed at.

    Like the other fallbacks this only proposes a candidate; the caller still
    requires it to match exactly once, so a file that genuinely contains the
    literal text is not at risk.
    """
    decoded: list[str] = []
    index = 0
    changed = False
    simple = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "/": "/", "\\": "\\"}
    while index < len(wanted):
        character = wanted[index]
        if character == "\\" and index + 1 < len(wanted):
            following = wanted[index + 1]
            if following in simple:
                decoded.append(simple[following])
                index += 2
                changed = True
                continue
        decoded.append(character)
        index += 1
    return "".join(decoded) if changed else None


def _indentation_insensitive_span(content: str, wanted: str) -> tuple[int, int] | None:
    """The one region matching `wanted` ignoring each line's indentation.

    Returns `(start, end)` character offsets, or None when there is no match or
    more than one - the uniqueness requirement is the whole safety property of
    an exact-match edit tool and is not relaxed here.

    Why this exists: indentation is the difference an agent gets wrong, because
    it is the part of a line it reconstructs rather than reads. Twice on
    one run a stage was stopped as a loop for re-issuing the same edit; the
    second time the file was indented with two spaces and every attempt used
    four, and the agent re-read the region four times without seeing it. Nothing
    else about those edits was wrong.

    Only leading and trailing whitespace is ignored. Text inside the line must
    still match character for character, so this cannot silently hit a different
    statement that merely looks similar.
    """
    wanted_lines = [line.strip() for line in wanted.splitlines()]
    if not wanted_lines or not any(wanted_lines):
        return None

    lines = content.splitlines(keepends=True)
    stripped = [line.strip() for line in lines]
    span = len(wanted_lines)

    matches: list[tuple[int, int]] = []
    for start in range(0, len(lines) - span + 1):
        if stripped[start : start + span] != wanted_lines:
            continue
        offset = sum(len(line) for line in lines[:start])
        region = lines[start : start + span]
        end = offset + sum(len(line) for line in region)
        # Stop at the end of the last matched line's *text*, not its newline.
        # Swallowing the terminator merges whatever followed onto the
        # replacement's final line - it put a closing brace on the end of a
        # return statement the first time this ran.
        last = region[-1]
        end -= len(last) - len(last.rstrip("\r\n"))
        matches.append((offset, end))
        if len(matches) > 1:
            return None
    return matches[0] if matches else None


def _blank_line_insensitive_span(content: str, wanted: str) -> tuple[int, int] | None:
    """The one region matching `wanted` ignoring indentation *and* blank lines.

    The same reasoning as `_indentation_insensitive_span`, one step further.
    Blank lines are the other part of a passage an agent reconstructs rather
    than reads: it remembers the statements and not the spacing between them.

    Measured on one run's `specialist_testing_3`, four failed edits of
    `app.test.mjs` in one stage. Two of them sent

          // Reset storage
          mockLocalStorage._data = {};
          // Add a task
          addTask({ title: 'Persisted', status: 'todo' });

    against a file holding exactly those four lines with a blank line between
    the second and third. Every non-blank line matched, character for
    character, and the edit was refused.

    Uniqueness is still required, and still on the non-blank lines only, so
    this cannot hit a different statement that merely looks similar. The span
    returned runs from the first matched line to the end of the last, which
    means the blank lines *inside* it are replaced along with the rest - which
    is what an agent that did not know they were there intends.
    """
    wanted_lines = [line.strip() for line in wanted.splitlines() if line.strip()]
    if not wanted_lines:
        return None
    if len(wanted_lines) == 1 and len(wanted_lines[0]) < _ONE_LINE_IS_ENOUGH:
        # A single short line - `}`, `});`, `return;` - is in every file
        # several times over, and matching one of them is a guess. A long one
        # identifies a passage on its own, and uniqueness is still required
        # below either way.
        #
        # The single-line case is here because blank lines around a passage are
        # as easy to misremember as blank lines inside it: one run sent
        # `"\nconst { loadTasks } = await import('./app.js');\n"` against a file
        # whose line above is a comment, so the leading blank line it invented
        # was the only thing wrong.
        return None

    lines = content.splitlines(keepends=True)
    significant = [
        (index, line.strip()) for index, line in enumerate(lines) if line.strip()
    ]
    matches: list[tuple[int, int]] = []
    for position in range(0, len(significant) - len(wanted_lines) + 1):
        window = significant[position : position + len(wanted_lines)]
        if [text for _, text in window] != wanted_lines:
            continue
        first_line, last_line = window[0][0], window[-1][0]
        start = sum(len(line) for line in lines[:first_line])
        end = start + sum(len(line) for line in lines[first_line : last_line + 1])
        last = lines[last_line]
        end -= len(last) - len(last.rstrip("\r\n"))
        matches.append((start, end))
        if len(matches) > 1:
            return None
    return matches[0] if matches else None


#: A single line this long identifies a passage by itself.
_ONE_LINE_IS_ENOUGH = 20

_SMALL_FILE_LINES = 40
"""At or under this, a failed edit is shown the whole file rather than a guess."""

_NEAR_MATCH_LINES = 3
"""Lines of context to quote back around the closest match."""


def _closest_passage(content: str, wanted: str) -> str | None:
    """The text in `content` most like `wanted`, quoted with its line numbers.

    An exact-match edit tool is only usable if a failure says *how* it failed.
    Without this the agent is told the text is absent and nothing else, so its
    only move is to read again and guess again - measured on one run,
    `specialist_ui_ux_0` issued the identical failing edit five times, re-reading
    the file between each, and was stopped as a loop. Every one of those was a
    model call spent discovering a difference this function can simply show.

    Matched on the first line of `wanted`, because that is where an edit's
    `find` usually goes wrong - a leading indent, a smart quote, a line the
    model reconstructed from memory rather than copied.
    """
    import difflib

    lines = content.splitlines()
    if not lines:
        return None

    # A short file is quoted whole. The fuzzy match below refuses to guess when
    # nothing scores above 0.6, which is right for a large file - a "closest"
    # line sharing one keyword sends the agent somewhere unrelated - but for a
    # file this size there is nowhere unrelated to send it, and the whole text
    # costs a few lines.
    #
    # Measured on one run: `specialist_backend_2` edited a five-line
    # `test-json.cjs`, missed, and was told only "Read the section first and
    # copy the passage from what you read". It read the file twice more and
    # missed twice more, and the run was stopped as a loop at 1,137 events. The
    # five lines it needed were available every time.
    first = next((line for line in wanted.splitlines() if line.strip()), "")

    if len(lines) <= _SMALL_FILE_LINES:
        # Marked if anything resembles the find, unmarked otherwise - either way
        # the whole file is there, which is the part the agent could not get.
        best = _best_matching_line(first, lines)
        return _quote(lines, 0, len(lines), best)

    if not first:
        return None

    best = _best_matching_line(first, lines)
    # Below the threshold the "closest" line shares a keyword and nothing else,
    # and quoting it would send the agent somewhere unrelated.
    if best is None:
        return None

    return _quote(
        lines,
        max(0, best - _NEAR_MATCH_LINES),
        min(len(lines), best + _NEAR_MATCH_LINES + 1),
        best,
    )


#: How alike the sent passage and the file's must be before naming the
#: differences. Below this they are different passages, and a line-by-line
#: comparison of two unrelated things reads as noise.
_WORTH_DIFFING = 0.7

#: At most this many differing lines in one report. A model that got every line
#: wrong needs the first few and a fresh read, not a wall of text.
_MAX_REPORTED_DIFFERENCES = 5

#: Longer lines are cut, with a marker, so one minified line cannot fill the
#: whole message.
_MAX_DIFF_LINE = 160


def _clip(line: str) -> str:
    return line if len(line) <= _MAX_DIFF_LINE else line[:_MAX_DIFF_LINE] + " ..."


def _refuse_an_edit_that_goes_backwards_again(relative_path: str, updated: str) -> None:
    """Refuse an edit that undoes another, once the note has been ignored twice.

    `_an_edit_that_undoes_an_earlier_one` says so and lets the edit through,
    which is right the first time and the second. Measured across every stored
    transcript, that is enough: of the three stages ever to receive the note,
    two stopped after one.

    The third is what this is for. One run's `test_round_1` was told five
    times and went on swapping a single line between four spellings -
    `++nextId`, `nextId; nextId++`, `nextId++`, `current.length > 0 ? ... : 1`
    and back - for eight edits, while the stage grew to the longest in the run.
    A note the model has ignored twice is not a note that needs rewording; the
    same reasoning, and the same threshold, as the no-op write refusal.

    Refused before anything is written, so the file keeps the state it has
    rather than taking one more step round the loop.
    """
    try:
        from app.tools.seen_content import (
            UNDO_WARNINGS_BEFORE_REFUSING,
            returned_to_an_earlier_state,
            times_warned_about_undoing,
        )

        if times_warned_about_undoing(relative_path) < UNDO_WARNINGS_BEFORE_REFUSING:
            return
        if not returned_to_an_earlier_state(relative_path, updated):
            return
    except Exception:  # noqa: BLE001 - a bookkeeping miss must not refuse an edit
        logger.debug("Could not check the edit history of %s", relative_path, exc_info=True)
        return
    raise RepositoryToolError(
        f"Refusing to change '{relative_path}': this edit puts the file back "
        "into a state it already had, and you have been told that twice "
        "already in this stage. Nothing was changed. The passage you keep "
        "rewriting is not where the problem is - if it were, one of the "
        "versions you have already tried would have worked. Read the failure "
        "again and look at a different part of the code."
    )


#: What was put right in a file on its way to disk, by resolved path, for the
#: result of the call that wrote it. Read once and cleared.
_PUT_RIGHT_ON_THE_WAY: dict[str, str] = {}


def _json_with_its_commas_put_right(target: Path, relative_path: str, content: str) -> str:
    """`content` with a JSON file's commas repaired, when that is all that is wrong.

    See `syntax_balance.json_with_its_commas_put_right`. The note is kept for
    the result, because a repair nobody is told about teaches nothing and the
    next edit makes the same mistake. Never raises.
    """
    if not relative_path.lower().endswith(".json"):
        return content
    try:
        from app.analysis.syntax_balance import _TOLERATES_COMMENTS, json_with_its_commas_put_right

        if relative_path.rsplit("/", 1)[-1] in _TOLERATES_COMMENTS:
            return content
        repaired = json_with_its_commas_put_right(content)
    except Exception:  # noqa: BLE001 - a repair that cannot run changes nothing
        return content
    if repaired is None:
        return content
    text, done = repaired
    _PUT_RIGHT_ON_THE_WAY[str(target)] = (
        "Your change left this JSON invalid only for its commas, so it was written "
        f"with them put right: {'; '.join(done)}. In JSON every member but the last "
        "of an object or array ends with a comma, and the last has none - adding or "
        "removing a line changes which one is last."
    )
    return text


def _what_was_put_right(target: Path) -> str:
    """The note `_json_with_its_commas_put_right` left for this file, once."""
    return _PUT_RIGHT_ON_THE_WAY.pop(str(target), "")


def _refuse_to_switch_a_suite_off(relative_path: str, before: str, after: str) -> None:
    """Refuse a change that leaves a working test file with no test that runs.

    See `test_discovery.a_suite_this_change_switches_off`. Never raises for
    any other reason: a check that cannot run refuses nothing.
    """
    try:
        from app.analysis.test_discovery import a_suite_this_change_switches_off

        problem = a_suite_this_change_switches_off(relative_path, before, after)
    except Exception:  # noqa: BLE001
        return
    if problem:
        raise RepositoryToolError(problem)


def _the_dom_unit_tests_get(target: Path | None) -> str:
    """Where the unit tests' browser globals come from in the project `target`
    is in, or "" when its pack gives them none (or no pack set it up)."""
    try:
        from app.stacks.contract import the_pack_above

        found = the_pack_above(target)
    except Exception:  # noqa: BLE001 - a note is not worth failing a write
        return ""
    return found[0].unit_dom if found else ""


#: Product code replacing a method every browser already defines. A polyfill
#: is never needed for these, so a rewrite is the product bent around something
#: else - in the run that prompted this, a unit test asking `querySelector`
#: for a selector the DOM does not define.
_REWRITES_THE_PLATFORM = re.compile(
    r"(?<![\w$.])(?:document|window|globalThis|self"
    r"|(?:Element|HTMLElement|Node|Document|EventTarget|DocumentFragment)\s*\.\s*prototype)"
    r"\s*\.\s*(querySelector(?:All)?|getElementById|getElementsBy(?:TagName|ClassName|Name)"
    r"|createElement|(?:add|remove)EventListener|dispatchEvent|matches|closest|contains"
    r"|appendChild|insertBefore|removeChild|replaceChild|append|prepend|setAttribute|getAttribute)"
    r"\s*=(?!=)"
)
_SCRIPT_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")


def _refuse_rewriting_the_platform(relative_path: str, content: str, original: str = "") -> None:
    """Refuse product code that replaces a method the browser already defines.

    Measured on one run. A unit test asked `querySelector` for
    `button:text("Edit")`, which the DOM does not define, and threw. The stage
    fixing it did not change the test: it replaced `document.querySelector`
    and `Element.prototype.querySelector` in the product's entry module with a
    version that understood the test's selector. The test passed, and the
    product shipped with every query on its page going through the rewrite.

    Only product files: a test may stub what it likes. An edit to a file that
    already rewrites one is let through unless it adds another, so the rewrite
    can be taken out a piece at a time.
    """
    from app.analysis.file_kinds import is_test

    name = PurePosixPath(relative_path).name
    if not name.endswith(_SCRIPT_SUFFIXES) or is_test(relative_path) or name.startswith(("tmp-", "tmp_")):
        return
    found = _REWRITES_THE_PLATFORM.findall(content)
    if len(found) <= len(_REWRITES_THE_PLATFORM.findall(original or "")):
        return
    raise RepositoryToolError(
        f"Refusing to write '{relative_path}': it replaces `{found[0]}`, which every "
        "browser already defines. Nothing was changed. Product code that works only on a "
        "rewritten platform changes every query on the page to suit one caller. If a test "
        "needs the rewrite, the test is asking for something the platform does not "
        "define: change the test to find what it needs with what the platform does "
        "define, or through what a person reads on the page."
    )


def _refuse_a_hand_built_dom_again(relative_path: str, content: str, target: Path | None = None) -> None:
    """Refuse a hand-built browser API, once the note has been ignored twice.

    `a_dom_built_by_hand` says so and lets the write through, on the reasoning
    that "a tiny stub for one function is a reasonable thing to write, and
    this cannot tell that from a mock that is about to collapse". That is
    right the first time and the second.

    The third is what this is for. One run's `specialist_testing_1` was
    told nine times, and grew `app.test.mjs` from 145 lines to 1,195 while
    being told - a `Proxy` over a `Map` standing in for `dataset`, a
    `mockStorage` throwing `QUOTA_EXCEEDED`, an `eventListeners` registry -
    and then spent three whole conversations debugging the mock instead of the
    product. Every one reached the model-call budget. The run failed with
    13.5 million tokens spent and nothing delivered.

    Refused before anything is written, so the file keeps the state it has
    rather than taking one more step into a browser it is writing itself.
    """
    try:
        from app.analysis.test_discovery import a_dom_built_by_hand
        from app.tools.seen_content import (
            MOCK_DOM_WARNINGS_BEFORE_REFUSING,
            times_warned_about_a_mock_dom,
        )

        if times_warned_about_a_mock_dom(relative_path) < MOCK_DOM_WARNINGS_BEFORE_REFUSING:
            return
        given = _the_dom_unit_tests_get(target)
        if not a_dom_built_by_hand(relative_path, content, given):
            return
    except Exception:  # noqa: BLE001 - a bookkeeping miss must not refuse a write
        logger.debug("Could not check the DOM history of %s", relative_path, exc_info=True)
        return
    if given:
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': it sets up a page of its own, and "
            "you have been told twice already in this stage what that costs. Nothing "
            f"was changed. Unit tests here already run with a browser's globals, from "
            f"{given}, which the harness keeps; a second page swaps them out halfway "
            "and the code under test fails on elements and events that are not its "
            "own. Delete the setup, use `document` and `window` as they are, and put "
            "the markup a test needs into `document.body.innerHTML` in `beforeEach`."
        )
    raise RepositoryToolError(
        f"Refusing to write '{relative_path}': it assigns `global.document` or "
        "`global.window`, and you have been told twice already in this stage "
        "what that costs. Nothing was changed. A hand-built browser holds only "
        "until the code under test touches something the mock does not have, "
        "and the failure then appears inside application code that is correct "
        "- which is how a stage ends up debugging its own mock instead of the "
        "product.\n"
        "Take a real one instead. `npm install -D jsdom` and import it, or "
        "`npm install -D @playwright/test` and drive a browser. `-D` matters: "
        "a brief that forbids external dependencies constrains the product, "
        "not the machine that builds it, and `npm ci --omit=dev` ships none of "
        "it. If neither is possible here, test the logic that does not touch "
        "the DOM and say in your response that the UI is untested - an honest "
        "gap is worth more than a suite that passes against a browser you "
        "wrote yourself."
    )


def _an_edit_that_undoes_an_earlier_one(relative_path: str, content: str) -> str:
    """Note that this edit put the file back where it already was, or "".

    Bookkeeping only: a failure here must not cost a successful edit its
    result. See `app.tools.seen_content.returned_to_an_earlier_state`.
    """
    try:
        from app.tools.seen_content import returned_to_an_earlier_state

        if not returned_to_an_earlier_state(relative_path, content):
            return ""
        from app.tools.seen_content import record_undo_warning

        record_undo_warning(relative_path)
    except Exception:  # noqa: BLE001 - no note is better than a failed edit
        logger.debug("Could not check the edit history of %s", relative_path, exc_info=True)
        return ""
    return (
        f"This edit put '{relative_path}' back into a state it already had earlier "
        "in this stage - it undoes a change made here rather than moving past it. "
        "Two edits that swap one passage back and forth make no progress and cost "
        "a model call each. Read the file, decide which of the two versions is "
        "right, and if the problem is not in this passage stop editing it and look "
        "somewhere else."
    )


def _what_this_stage_replaced_it_with(relative_path: str, find: str) -> str | None:
    """What this stage put in place of `find`, or None if it never replaced it.

    Bookkeeping only; a failure falls through to the messages below.
    """
    try:
        from app.tools.seen_content import what_replaced_it

        return what_replaced_it(relative_path, find)
    except Exception:  # noqa: BLE001 - fall through to the diff
        logger.debug("Could not check replacements in %s", relative_path, exc_info=True)
        return None


def _who_changed_it(root: Path, relative_path: str) -> str:
    """Who rewrote a file under a stage that had read it, as a clause.

    Always "a command you ran" until now, which was true when the stages ran
    one at a time. With parallel stages the writer is as often a stage working
    alongside: one run's `specialist_ui_ux_0` read `app.js`, and
    `specialist_testing_1` edited it twice before the edit that read was for.
    Blaming a command the stage never ran sends it looking for one.
    """
    try:
        from app.analysis import project_memory
        from app.observability.transcript import _stage_from_config

        writer = project_memory.who_changed(root, relative_path)
        me = _stage_from_config("")
    except Exception:  # noqa: BLE001 - the generic cause is still true
        writer, me = "", ""
    if writer and me and writer != me:
        return f"'{writer}', a stage working alongside you, changed it since"
    return "a command you ran (an installer, a formatter, a generator) rewrote it"


def _changed_underneath(relative_path: str, original: str) -> bool:
    """True when this stage read the file and it no longer holds what it read.

    Bookkeeping only, so a failure here falls back to the diff rather than
    costing the edit its error message.
    """
    try:
        from app.tools.seen_content import changed_since_seen

        return changed_since_seen(relative_path, original)
    except Exception:  # noqa: BLE001 - fall through to the messages below
        logger.debug("Could not check whether %s changed", relative_path, exc_info=True)
        return False


def _only_the_whitespace_differs(sent: str, actual: str) -> str:
    """How two lines differ when they differ only in spacing, or "".

    A diff that prints `you sent: X` above `file has: X` is worse than no
    diff: the reader cannot see the difference, concludes the tool is wrong,
    and sends the identical text again. Leading indentation and trailing
    space are both invisible, and both are what a model reconstructing a
    passage from memory gets wrong.

    Returns a phrase naming the difference in words, so it survives being
    read rather than looked at.
    """
    if sent == actual or sent.strip() != actual.strip():
        return ""
    sent_indent = len(sent) - len(sent.lstrip())
    actual_indent = len(actual) - len(actual.lstrip())
    notes: list[str] = []
    if sent_indent != actual_indent:
        difference = actual_indent - sent_indent
        direction = "more" if difference > 0 else "less"
        notes.append(
            f"indented {abs(difference)} space{'s' if abs(difference) != 1 else ''} {direction}"
            f" ({actual_indent} not {sent_indent})"
        )
    if "\t" in actual and "\t" not in sent:
        notes.append("indented with tabs, not spaces")
    elif "\t" in sent and "\t" not in actual:
        notes.append("indented with spaces, not tabs")
    if sent.rstrip() != sent and actual.rstrip() == actual:
        notes.append("with no trailing space")
    elif actual.rstrip() != actual and sent.rstrip() == sent:
        notes.append("with trailing space")
    if not notes:
        notes.append("spaced differently")
    return ", ".join(notes)


def _how_it_differs(content: str, wanted: str) -> str:
    """Name the differences between the sent passage and the file's, or "".

    Quoting the nearest passage - which this tool already did - shows the model
    the right text and leaves it to spot what changed. Measured on
    one run's `defect_fix_2_0`, it does not. The model sent

        // function saveTasks() {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
        }

    against a file holding exactly that without the `// `, got the passage
    quoted back at it, tried twice more, and finished the stage reporting
    "Unable to locate exact saveTasks function code for editing; cannot apply
    fix" - a real defect abandoned over three characters it could not see.

    The existing fallbacks forgive the differences that are mechanical: line
    numbers from `read_file`, doubled backslashes, JSON escaping, a different
    left margin. They cannot forgive this one, because a comment marker
    changes what the code means and guessing which side the model wanted would
    be editing on its behalf. So say precisely what differs and let it decide.
    """
    import difflib

    lines = content.splitlines()
    wanted_lines = wanted.splitlines()
    if not lines or not wanted_lines:
        return ""
    first = next((line for line in wanted_lines if line.strip()), "")
    anchor = _best_matching_line(first, lines)
    if anchor is None:
        return ""
    # The passage starts wherever its first non-blank line matched, so back up
    # by however many blank lines the sent text opened with.
    lead = next((i for i, line in enumerate(wanted_lines) if line.strip()), 0)
    start = max(0, anchor - lead)
    window = lines[start:start + len(wanted_lines)]
    if not window:
        return ""
    ratio = difflib.SequenceMatcher(None, "\n".join(wanted_lines), "\n".join(window)).ratio()
    if ratio < _WORTH_DIFFING:
        return ""

    # Aligned, not zipped. Comparing line 1 to line 1, line 2 to line 2 and so
    # on is only true while the two texts stay in step: one inserted line makes
    # every line after it look different. Measured on one run,
    # `specialist_testing_1` sent a 31-line passage against a 29-line file that
    # had gained two import lines at the top and was told 21 lines differed. Two
    # of them did. It sent the same passage twice more.
    differences: list[str] = []
    reported = 0
    for tag, sent_from, sent_to, file_from, file_to in difflib.SequenceMatcher(
        None, wanted_lines, window
    ).get_opcodes():
        if tag == "equal":
            continue
        if reported >= _MAX_REPORTED_DIFFERENCES:
            differences.append("  ... and more")
            break
        reported += 1
        if tag == "replace":
            for sent, actual, offset in zip(
                wanted_lines[sent_from:sent_to],
                window[file_from:file_to],
                range(file_from, file_to),
            ):
                # A whitespace-only difference prints as two identical lines
                # and teaches nothing. Measured on one run's
                # `test_round_1`, which was answered with
                #
                #   you sent:  const url = `file://...index.html`;
                #   file has:    const url = `file://...index.html`;
                #
                # and re-sent the same text. The only difference was the left
                # margin, which is invisible in a message. Say it in words and
                # count it, rather than showing the reader two things that
                # look the same.
                gap = _only_the_whitespace_differs(sent, actual)
                if gap:
                    differences.append(f"  you sent:  {_clip(sent)}")
                    differences.append(f"  file has:  the same text, {gap}   (line {start + offset + 1})")
                    continue
                differences.append(f"  you sent:  {_clip(sent)}")
                differences.append(
                    f"  file has:  {_clip(actual)}   (line {start + offset + 1})"
                )
        elif tag == "delete":
            for sent in wanted_lines[sent_from:sent_to]:
                differences.append(f"  you sent:  {_clip(sent)}")
                differences.append(
                    f"  file has:  nothing there - that line is not in the file"
                )
        elif tag == "insert":
            for actual, offset in zip(window[file_from:file_to], range(file_from, file_to)):
                differences.append(
                    f"  you left out:  {_clip(actual)}   (line {start + offset + 1})"
                )
    if not differences:
        return ""

    # Naming `replace_lines` here, with the numbers already in hand.
    #
    # This message knew exactly which lines it nearly matched and told the
    # model to try quoting them again - the one thing that had just failed.
    # Measured across the fifty stored transcripts: 292 edits failed with
    # "could not find that text", 113 of them close enough to diff, while
    # `replace_lines` - which cannot fail this way, because a line number
    # needs no quoting - was called 42 times against `edit_artifact`'s 1,707.
    # A tool used in 2% of edits is a tool nobody was told to reach for.
    first_line = window[0] if window else ""
    return (
        f"\n\nIt is nearly the passage at line {start + 1}. These lines differ:\n"
        + "\n".join(differences)
        + "\n\nTwo ways forward. Either send `find` exactly as the file has it "
        "above, with what you want instead in `replace` - or skip the quoting "
        "entirely and call `replace_lines` with "
        f"start_line={start + 1}, end_line={start + len(window)}, "
        f"expect_start={_clip(first_line).strip()!r}, and your new text as "
        "`content`. That names the passage by position, so nothing has to "
        "match character for character."
    )


#: At most this many copies are shown with their surroundings. Past a handful
#: the message is longer than the file and the passage is the wrong one.
_MAX_AMBIGUOUS_MATCHES_SHOWN = 4

#: Below this, `replace` is too small for its presence in the file to mean
#: anything - `}` or `0` is in every file already.
_REPLACE_LONG_ENOUGH_TO_RECOGNISE = 24


def _where_the_replacement_already_wraps_every_match(
    original: str, find: str, replace: str
) -> int:
    """The line of the replacement when it already contains every match of `find`, or 0.

    `_already_applied` looks for an edit whose `find` is gone. That misses the
    edit whose `replace` contains its own `find`: once applied, `find` is still
    there - inside the replacement - so a second send matches again and wraps
    it again. Measured on one run's `defect_fix_1_1`: `find: "let tasks = [];"`,
    `replace: "export let tasks = [];"`, applied at 16:40, sent again at 16:45,
    and the file would have read `export export let tasks = [];`. Node's parse
    check refused it; a stylesheet, a Python module or a README has no such
    check and would have been changed twice.

    Only when every occurrence of `find` lies inside an occurrence of `replace`:
    one that does not is a place the edit has not been made yet.
    """
    if not find or find == replace or find not in replace or find not in original:
        return 0
    offset = replace.find(find)
    covered = 0
    start = original.find(find)
    while start != -1:
        begin = start - offset
        if begin < 0 or original[begin : begin + len(replace)] != replace:
            # `find` may sit in `replace` more than once; any placement will do.
            placements = [
                i for i in range(len(replace)) if replace.startswith(find, i)
            ]
            if not any(
                start - i >= 0 and original[start - i : start - i + len(replace)] == replace
                for i in placements
            ):
                return 0
        covered += 1
        start = original.find(find, start + 1)
    if not covered:
        return 0
    return original[: original.find(replace)].count("\n") + 1


def _already_applied(original: str, find: str, replace: str) -> int:
    """The message for an edit that has already been made, or "".

    Measured on one run's `defect_fix_2_0`. At 14:15:33 it edited
    `saveTasks` to read `localStorage` through a `global` fallback, and the
    tool returned `"status": "edited"`. At 14:15:51, 14:16:19, 14:16:36 and
    14:16:46 it sent the byte-identical call again - same `find`, same
    `replace` - and got "Could not find that text" each time, because its own
    edit had removed the text it was looking for. Four model calls, and a stage
    that finished reporting the fix could not be applied. It had been applied
    in the first thirty seconds.

    Nothing in the failure message could have told it: "could not find that
    text" is true, and the quoted nearest passage was its own edit, which reads
    like a near miss rather than like success. The file itself has the answer -
    what the model asked to put there is already there.

    Returns the 1-based line where `replace` sits, or 0 when this is not an
    edit that has already been made. A line number rather than a sentence,
    because the caller answers with a success now and not with an error - see
    `_already_there` for what that costs and why it changed.
    """
    if len(replace.strip()) < _REPLACE_LONG_ENOUGH_TO_RECOGNISE:
        # A short `replace` proves nothing by being present, and a deletion
        # (empty `replace`) has nothing to look for at all.
        return 0
    if replace not in original:
        return 0
    return original[: original.index(replace)].count("\n") + 1


def _already_there(
    target: Path, root: Path, relative_path: str, replace: str, line: int
) -> dict[str, Any]:
    """The answer to an edit whose text is already in the file.

    This was an error until it was measured. Across 85 stored runs it fired 247
    times in 46 of them, and the message it raised opened with "Could not find
    that text" and only then explained that the edit was already made. Leading
    with the failure is what the model answered: 41 of those 247 re-sent the
    byte-identical edit immediately, which cannot do anything but fail again.

    It also said "Read the file if you want to confirm it", and 65 stages did
    exactly that. Eighteen of those reads were then refused by the repeated-read
    guard - the harness inviting a read and denying it - and the invitation was
    never worth anything, because this function only runs once `replace` has
    been found in the file. The confirmation the model was sent to fetch had
    already been made on its behalf.

    So the edit is not a failure. The requested `find` is gone and the requested
    `replace` is present: the file reads the way the call asked for it to read.
    That is the success condition of a declarative edit, and reporting it as one
    is what lets a stage move to its next change.

    `status` is `already_applied` rather than `edited` because nothing was
    written just now. No authorship is recorded for the same reason - whoever
    made the edit was recorded when they made it, and claiming the write here
    would credit this call for a change it did not make.
    """
    written = target.read_text(encoding="utf-8")
    summary = replace[:80] + ("..." if len(replace) > 80 else "")
    return {
        "path": str(target.relative_to(root)),
        "status": "already_applied",
        "summary": summary,
        "lines": _line_count(written),
        "detail": (
            f"This edit is already in '{relative_path}', at line {line}. "
            f"{_who_applied_it(root, relative_path)}, which is why the text in "
            "`find` is no longer there. Nothing was written just now and nothing needed to be - the "
            "file already reads the way you asked for, and this was checked "
            "against its current contents, so there is nothing to confirm. "
            "Move on to your next change. If you meant a further change to that "
            "same passage, send the text that is there now as `find`."
        ),
    }


def _who_applied_it(root: Path, relative_path: str) -> str:
    """Whose change an already-applied edit found, as the start of a sentence.

    "It was applied earlier" did not stop one stage re-sending its own first
    edit three times: it had lost track of having made it. Saying that it was
    this stage's own change is the fact that ends the repeat.
    """
    try:
        from app.analysis import project_memory
        from app.observability.transcript import _stage_from_config

        writer = project_memory.who_changed(root, relative_path)
        me = _stage_from_config("")
    except Exception:  # noqa: BLE001 - the generic sentence is still true
        writer, me = "", ""
    if writer and me and writer == me:
        return "You made this change yourself, earlier in this stage"
    return "It was applied earlier"


def _best_matching_line(first: str, lines: list[str]) -> int | None:
    """Index of the line most like `first`, or None if nothing is close."""
    import difflib

    if not first or not lines:
        return None
    # Earliest on a tie, not latest. `max` over (ratio, index) tuples breaks
    # ties toward the *highest* index, so a file of `const lineN = N;` pointed
    # at line 50 for a near miss on line 41 - every line scores alike and the
    # last one won. Everything else in this tool means the first occurrence
    # when it says "the" one, and a wrong pointer is worse than none.
    best_ratio, best_index = 0.0, None
    for index, line in enumerate(lines):
        ratio = difflib.SequenceMatcher(None, first.strip(), line.strip()).ratio()
        if ratio > best_ratio:
            best_ratio, best_index = ratio, index
    return best_index if best_ratio >= 0.6 else None


def _quote(lines: list[str], start: int, end: int, marked: int | None) -> str:
    """Numbered lines `start`..`end`, with `marked` flagged in column zero."""
    return "\n".join(
        f"{'>' if index == marked else ' '} {index + 1:>4} | {lines[index]}"
        for index in range(start, end)
    )


#: Package manifests, whatever the language. A test round fixing the `test`
#: script in one is changing test configuration, not the product.
PACKAGE_MANIFESTS = frozenset({
    "package.json", "pyproject.toml", "setup.cfg", "requirements.txt", "requirements-dev.txt",
    "Pipfile", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "Gemfile", "composer.json", "mix.exs", "deno.json",
})

#: The stage name of a verification round, `test_round_<n>`.
_A_TEST_ROUND = "test_round_"
_THE_TESTING_TASK = "specialist_testing_"


#: What a defect is reported with. A document carrying most of these is a
#: defect report, whatever it is called.
_PARTS_OF_A_DEFECT_REPORT = (
    "severity", "reproduc", "expected", "actual", "owner", "affected file",
)
_PARTS_THAT_MAKE_IT_A_DEFECT_REPORT = 4


def _reads_as_a_defect_report(content: str) -> bool:
    lowered = str(content or "").lower()
    return (
        sum(1 for part in _PARTS_OF_A_DEFECT_REPORT if part in lowered)
        >= _PARTS_THAT_MAKE_IT_A_DEFECT_REPORT
    )


#: The stage that writes the acceptance suite, and the only one that may change it.
_THE_ACCEPTANCE_AUTHOR = "acceptance_author"


def _a_file_the_harness_keeps(root: Path, relative: str) -> str | None:
    """The refusal for changing runner configuration a stack pack set up, or None.

    `app.stacks.contract.enforce` puts these files back before the harness
    runs anything, which keeps the harness's own runs honest but came too late
    for the stage that changed one: its own runs of the suite used the broken
    copy. One run's stages edited the acceptance configuration in a work order
    and two fixes, then reported the suite unable to reach the product.
    """
    try:
        from app.stacks import contract

        if contract.owned_by_the_harness(root, relative) != contract.KEPT_SETUP:
            return None
        record = contract.read(root) or {}
    except Exception:  # noqa: BLE001 - no contract, nothing kept
        return None
    project = str(record.get("project") or "")
    command = " ".join(str(part) for part in record.get("acceptance_test") or [])
    return (
        f"'{relative}' is test configuration the harness set up and keeps: it starts the "
        f"product for the acceptance suite and already works. It cannot be changed. Run "
        f"`{command}` in `{project}/` as it is; if it fails, the cause is in the product."
    )


def _the_harness_s_own_or_the_locked_suite(root: Path, target: Path) -> str | None:
    """The refusal for a change to the harness's records or the acceptance suite, or None.

    The acceptance suite is the product's definition of done: QA wrote it from
    the criteria before anything was built, a review approved it, and the
    harness runs it. A stage that could edit it could make the product "done" by
    weakening a test, which is the failure the suite exists to prevent - so only
    the QA stage, reopened through a recorded change, may touch it. And the QA
    stage writes nothing else: the product is not its to build.
    """
    try:
        relative = target.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    if relative == ".harness" or relative.startswith(".harness/"):
        return (
            f"'{relative}' is the harness's own record of what it set up and locked; "
            "no stage may change it."
        )
    kept = _a_file_the_harness_keeps(root, relative)
    if kept is not None:
        return kept
    try:
        from app.acceptance import suite

        where = suite.relative_directory(root)
        protected = suite.is_protected(root, relative)
    except Exception:  # noqa: BLE001 - an unreadable lock protects nothing
        where, protected = "", False
    inside = bool(where) and (relative == where or relative.startswith(where + "/"))
    try:
        from app.observability.transcript import _stage_from_config

        stage = str(_stage_from_config("") or "")
    except Exception:  # noqa: BLE001
        stage = ""
    if stage.startswith(_THE_ACCEPTANCE_AUTHOR):
        if where and not inside:
            return (
                f"'{relative}' is not part of the acceptance suite. QA writes only "
                f"`{where}/`; the product is built by the stages that own it, after "
                "this suite is locked."
            )
        return None
    if not protected:
        return None
    return (
        f"'{relative}' is part of the acceptance suite, which QA wrote from the "
        "acceptance criteria and the harness has locked: the product is done when this "
        "suite passes, so it is never changed to make it pass. Change the product "
        "instead. If you are certain a test there is wrong, name the test and why in "
        "`blockers`; the review decides."
    )


def _a_tester_changing_the_product(root: Path, target: Path, content: str = "") -> str | None:
    """The refusal for a testing stage changing application code, or None.

    A test round finds what fails and reports each failure as a defect for the
    role that owns it; the owner fixes it and the Sprint Record logs the defect,
    its cause and its fix. On one run the test round's engineer edited the
    product's `app.js` itself to get a failing unit test through - a real
    fix, possibly, but one no defect log, no owner and no review round ever
    heard of.

    The testing work order is held to the same line. It writes tests against
    the other work orders' interfaces while that code is being written, and the
    ownership check stops it only at a file some work order lists. Measured
    over 25 runs: testing specialists wrote product code nine times - a page,
    an `app.js`, a server - and on one run wrote the stub `src/ui.js` that no
    work order listed, over the version another stage had just written.

    Tests, test configuration, documents and package manifests stay theirs.
    """
    try:
        from app.observability.transcript import _stage_from_config

        stage = str(_stage_from_config("") or "")
    except Exception:  # noqa: BLE001 - outside a run there is no round to guard
        return None
    if not stage.startswith((_A_TEST_ROUND, _THE_TESTING_TASK)):
        return None
    from app.analysis.file_kinds import classify_file

    try:
        shown = target.relative_to(root).as_posix()
    except ValueError:
        return None
    if (
        stage.startswith(_A_TEST_ROUND)
        and classify_file(shown) != "test"
        and target.name not in PACKAGE_MANIFESTS
        and not target.exists()
        and _reads_as_a_defect_report(content)
    ):
        # A round's findings written as a file. One run's test round wrote
        # `defects_report.md` into the project - two defects with severity,
        # reproduction and owner, which is the `defects` field word for word -
        # and it shipped with the product. By its content, and only a new
        # file: a round's own notes, and corrections to a document already
        # there, are still its to write. Whatever the format - another round
        # wrote the same findings as `test_results.json`, was told that was
        # product code, and tried again as `test_defects.json`.
        return (
            f"'{shown}' would be a new file in the product, and this is a test "
            "round: what it finds is returned in `defects`, not written to a file. "
            "The workflow reads the defects from your structured response, routes "
            "each to its owner and logs it in the Sprint Record; a report file is "
            "read by none of them and ships with the product. Put each finding in "
            "`defects` and return. Nothing was written."
        )
    if target.name in PACKAGE_MANIFESTS or classify_file(shown) != "application":
        return None
    from app.analysis.file_kinds import is_scratch

    if is_scratch(shown):
        # A probe some stage left, named as one: not the product, and the sweep
        # between stages removes it anyway. Refusing a tester its delete as
        # "product code" cost one stage seven calls on `temp2.js`.
        return None
    if stage.startswith(_THE_TESTING_TASK) and _created_here(root, shown, stage):
        # Its own file, not the product's: a probe renamed out of the test
        # runner's way so it can be deleted, as the delete refusal suggests.
        return None
    if stage.startswith(_THE_TESTING_TASK):
        return (
            f"'{shown}' is product code, and this is the testing work order: it writes "
            "tests against the interfaces the other work orders promise, while they "
            "write the code. Write the test against the interface as the plan gives it, "
            "even if the code is not there yet. If the code a test needs is missing or "
            "does not match its interface, say exactly what in `blockers` - the "
            "milestone review reads it and the owner makes the change. Tests, test "
            "configuration and the package manifest are yours to change. "
            "Nothing was written."
        )
    return (
        f"'{shown}' is product code, and this is a test round: its job is to find "
        "what fails and report it, not to change the product. A fix made here is "
        "recorded nowhere - not in the defect log, not in the Sprint Record, not by "
        "the role that owns the file. Report it in `defects` with that role as the "
        "owner, the reproduction, and the change you would make; the owner makes it "
        "next. Tests, test configuration and the package manifest are yours to change. "
        "Nothing was written."
    )


def _as_a_planned_path(path: str) -> str:
    """A path as a plan or a tool call spells it, in one form: no leading `/` or `./`."""
    cleaned = str(path or "").strip().replace("\\", "/")
    while cleaned.startswith(("./", "/")):
        cleaned = cleaned[2:] if cleaned.startswith("./") else cleaned[1:]
    return cleaned.rstrip("/")


def record_work_order_files(root: str | Path, owners: Mapping[str, str]) -> None:
    """Record which stage each planned file belongs to, for this milestone.

    `owners` maps a path a work order lists in `files` to the stage that task
    runs as. A path two work orders both list has no single owner and is left
    out - the fan-out staggers those. Replaced whole on every plan, so a new
    milestone never inherits the last one's owners. Never raises.
    """
    base = Path(root)
    pinned = pinned_project_directory(base)
    table: dict[str, str] = {}
    for path, stage in owners.items():
        cleaned = _as_a_planned_path(path)
        if not cleaned or not stage:
            continue
        if pinned and "/" not in cleaned:
            cleaned = f"{pinned}/{cleaned}"
        table[cleaned] = str(stage)
    try:
        (base / WORK_ORDER_FILES).write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        logger.warning("Could not record the work orders' files", exc_info=True)


def _another_work_order_s_file(root: Path, target: Path) -> str | None:
    """The refusal for a specialist writing a file another work order owns, or None.

    Work orders list their files so that a newcomer knows exactly what to touch,
    and nothing held a specialist to it. On one run's first milestone the
    testing task wrote the backend task's `app.js` before the backend task
    did, and the documentation task wrote the testing task's unit test; the
    blind-overwrite guard kept either from being lost, and every refusal it
    issued was a call spent on a file the plan had given to someone else.

    Only specialist stages are held to it, only for a file one other work order
    lists, and only in the milestone whose plan recorded it. Files no work
    order lists stay open to whoever needs them.
    """
    try:
        from app.observability.transcript import _stage_from_config

        stage = str(_stage_from_config("") or "")
    except Exception:  # noqa: BLE001 - outside a run there is no plan to hold to
        return None
    if not stage.startswith("specialist_"):
        return None
    try:
        table = json.loads((root / WORK_ORDER_FILES).read_text(encoding="utf-8"))
        shown = target.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None
    if not isinstance(table, dict):
        return None
    owner = next(
        (
            str(stage_name)
            for planned, stage_name in table.items()
            if shown == planned or shown.startswith(f"{planned}/")
        ),
        None,
    )
    if owner is None or owner == stage:
        return None
    return _again_and_again(shown) + (
        f"'{shown}' belongs to another work order in this milestone: the plan gave it "
        f"to {owner}, which writes it. Change only the files your own work order "
        "lists. If your task needs something in that file - an export, an element, a "
        "script - say exactly what in `blockers`, where the milestone review reads it. "
        "Nothing was written."
    )


def _created_here(root: Path, shown: str, stage: str) -> bool:
    """Whether the running stage wrote this file first. False when unknown."""
    try:
        from app.analysis import project_memory

        return bool(stage) and project_memory.who_created(root, shown) == stage
    except Exception:  # noqa: BLE001 - unknown is not "its own"
        return False


#: Refusals of one file to one stage before the refusal says how many.
_REFUSALS_BEFORE_COUNTING = 3


def _again_and_again(shown: str) -> str:
    """A lead for the refusal when this stage has been refused this file before, or "".

    Each attempt was a different change, so the repeat notes - which compare
    the arguments - never fired. Measured on one run: `specialist_backend_1`
    was refused `src/ui.js`, the interface work order's file, six times with
    six different `replace_lines`, the same refusal each time.
    """
    try:
        from app.agents.stage_memory import store

        refused = store("files_refused_as_another_work_order_s", {})
        refused[shown] = refused.get(shown, 0) + 1
        count = refused[shown]
    except Exception:  # noqa: BLE001 - a count is a courtesy
        return ""
    if count < _REFUSALS_BEFORE_COUNTING:
        return ""
    return (
        f"This stage has now been refused '{shown}' {count} times. Rewording the "
        "change does not change whose file it is: stop changing it, put what your "
        "work needs from it in `blockers`, and finish the files that are yours. "
    )


def _not_this_stage_s_to_take(
    root: Path, target: Path, *, done: str, product_code: bool = True
) -> str | None:
    """Either refusal that holds a stage to its own files, for a delete or a move.

    `write_artifact` and the targeted changes asked both questions and
    `delete_artifact` and `move_artifact` asked neither, so a stage refused a
    write could take the file away instead. Measured on one run: the interface
    task, refused a write to the data task's `taskModel.js`, deleted it, and
    wrote it again - refused again, with the data task's module now gone and
    every import of it broken.
    """
    for refusal in (
        _installed_by_a_tool(root, target, done=done),
        _another_work_order_s_file(root, target),
        _a_tester_changing_the_product(root, target) if product_code else None,
    ):
        if refusal is not None:
            return refusal.replace("Nothing was written.", f"Nothing was {done}.")
    return None


def _guard_a_targeted_change(
    repo_root: str | Path, relative_path: str, replacement: str
) -> tuple[Path, Path]:
    """Every check a targeted change must pass, in one place.

    `edit_artifact` and `replace_lines` change part of a file and differ only
    in how they say *which* part. Every other question - is the path inside
    the workspace, is it a credential, is it a document the workflow renders,
    is this the stage's own structured response, does the file exist, does the
    replacement carry the model's own control tokens - has one answer, and it
    had one implementation only while there was one tool.

    Returning `(root, target)` rather than duplicating the sequence is the
    rule this codebase keeps arriving at: define the check once over the set
    it applies to. A third targeted-change tool gets these for free.
    """
    root = _normalize_repo_root(repo_root)
    target = (root / _repo_relative_path(root, relative_path)).resolve()
    _assert_within_repo(root, target)

    if is_secret_path(target):
        raise RepositoryToolError(
            f"Refusing to edit '{relative_path}': the path matches a credential file pattern."
        )
    cut_off = _cut_off_at_a_quote(relative_path, replacement, editing=True)
    if cut_off is not None:
        raise RepositoryToolError(cut_off)
    locked = _the_harness_s_own_or_the_locked_suite(root, target)
    if locked is not None:
        raise RepositoryToolError(locked)
    installed = _installed_by_a_tool(root, target)
    if installed is not None:
        raise RepositoryToolError(installed)
    # The owner first: it names who writes the file, which says more.
    someone_else_s = _another_work_order_s_file(root, target)
    if someone_else_s is not None:
        raise RepositoryToolError(someone_else_s)
    not_this_round_s = _a_tester_changing_the_product(root, target)
    if not_this_round_s is not None:
        raise RepositoryToolError(not_this_round_s)
    returning = _the_response_it_should_be_returning(
        tuple(_repo_relative_path(root, relative_path).parts)
    )
    if returning is not None:
        raise RepositoryToolError(returning)
    if not target.is_file():
        canonical = _supersedes_existing(target)
        if canonical is not None:
            raise RepositoryToolError(
                f"Cannot edit '{relative_path}': it does not exist. "
                f"Edit '{canonical.name}' instead - it is the current version of "
                "this document. Do not recreate the file you just tried to edit."
            )
        moved_to = _where_this_stage_put_it(relative_path)
        if moved_to is not None:
            raise RepositoryToolError(
                f"Cannot edit '{relative_path}': it does not exist, because "
                f"this stage moved it to '{moved_to}'. Edit that instead. "
                "Writing this path again would put back the file you renamed "
                "and leave two copies of the same module."
            )
        raise RepositoryToolError(
            f"Cannot edit '{relative_path}': it does not exist yet. "
            "Use write_artifact to create it."
        )
    _refuse_control_tokens(relative_path, replacement)
    owned = _a_workflow_document(tuple(_repo_relative_path(root, relative_path).parts))
    if owned is not None:
        raise RepositoryToolError(owned)
    return root, target


def _without_the_quotes_it_added(expected: str, actual: str) -> str:
    """`expected` without one pair of surrounding double quotes, when that makes it `actual`.

    A model quoting a line as a string literal wraps it in quotes: one run's
    specialist sent `expect_start='"    "scripts": {"'` for the line
    `"scripts": {` of `package.json`, which can never match, so a correctly
    counted edit was refused. Forgiven only when the quotes are the whole
    difference - the line itself is compared exactly, as before.
    """
    wanted = expected.strip()
    if (
        len(wanted) >= 2
        and wanted[0] == wanted[-1] == '"'
        and wanted != actual.strip()
        and wanted[1:-1].strip() == actual.strip()
    ):
        return wanted[1:-1].strip()
    return expected


#: The least of a line that pins it when the rest of the line is left off.
#: Shorter than this, a prefix such as `}` or `if (` names half the file.
_A_PREFIX_THAT_PINS = 8


def _the_line_it_cut_short(expected: str, actual: str) -> str:
    """`actual`, when `expected` is that line with only its end left off.

    Measured over 25 runs: 17 of 52 `replace_lines` refused as "not what you
    expected" pinned the right line without its last characters -
    `function loadTasks()` for `function loadTasks() {`, a `<link ...>` without
    its `>`, a property without its trailing comma - and were told the line
    was "not in the file at all". The line number and the start of the line
    agree, so the range is the one the model meant. Only a prefix of at least
    `_A_PREFIX_THAT_PINS` characters counts, compared as the rest of the check
    is, with the surrounding whitespace ignored.
    """
    wanted, there = _without_the_ellipsis_it_ended_on(expected), actual.strip()
    if len(wanted) >= _A_PREFIX_THAT_PINS and wanted != there and there.startswith(wanted):
        return actual
    return expected


def _without_the_ellipsis_it_ended_on(expected: str) -> str:
    """A pin, stripped, without the `...` a shortened line was closed with.

    A model that leaves off the end of a line sometimes says so: one run
    pinned its first line as `// state_and_...`, at the right line number.
    Only when something is left in front of it: `...args` is code.
    """
    wanted = str(expected or "").strip()
    for ending in ("...", "\u2026"):
        if wanted.endswith(ending) and wanted[: -len(ending)].strip():
            return wanted[: -len(ending)].rstrip()
    return wanted


def _without_the_escapes_it_doubled(expected: str, lines: list[str]) -> str:
    """`expect_start`/`expect_end` with `\\"` read as `"`, when only that makes it a line of the file.

    A pin is a line of the file inside a JSON string, and a line with quotes in
    it is where a model escapes twice. One run's fix stage sent

        expect_start: '"test\\": \\"node --test simple-to-do-list-app/store.test.js\\"'

    for line 8 of `package.json`, which reads `"test": "node --test ..."`. The
    line number was right and so was the replacement; it was told the line
    "is not in the file at all now" and to read the file again.

    Only when the pin as sent is no line of the file and the unescaped one is:
    a file that really holds a backslash before a quote matches as sent, and is
    never touched.
    """
    wanted = expected.strip()
    if "\\" not in wanted:
        return expected
    there = {line.strip() for line in lines}
    if wanted in there:
        return expected
    unescaped = re.sub(r"\\+([\"'])", r"\1", wanted)
    if unescaped != wanted and unescaped in there:
        return unescaped
    return expected


def _without_a_copied_gutter(expected: str, lines: list[str]) -> str:
    """`expect_start`/`expect_end` without a line-number gutter copied into it.

    This module quotes a file back as `   93 | text`, and a model copies what it
    is shown. One run's `specialist_ui_ux_0` sent
    `expect_start=" 1 | export class TaskItem extends HTMLElement{"` for a line
    reading `export class TaskItem extends HTMLElement{`, and was told the line
    was not what it expected - by the tool whose quoting it had copied.
    `find` already forgives this (`_READ_LINE_NUMBER`); the pins did not.

    Only when every line sent carries a gutter and none of them is in the file
    as sent, so a real line that starts with a number is compared as written.
    """
    written = [line for line in str(expected or "").splitlines() if line.strip()]
    if not written or not all(_READ_LINE_NUMBER.match(line) for line in written):
        return expected
    held = {line.strip() for line in lines}
    if any(line.strip() in held for line in written):
        return expected
    return "\n".join(
        _READ_LINE_NUMBER.sub("", line, count=1) for line in str(expected).splitlines()
    )


def _the_one_line_it_pins(expected: str) -> str:
    """`expect_start`/`expect_end` reduced to the single line they name.

    Both parameters pin one line - the tool's own docstring says "the LAST line
    of the range as you read it" - and a caller that sends two cannot match
    anything, because the comparison is against one line of the file.

    Measured on one run's `specialist_ui_ux_0`, twice in the same second.
    It sent `expect_start` as two lines of `package.json`:

        {
          "name": "simple-to-do-list-app"

    Line 1 of the file is `{`, so the call was right about where it was. The
    refusal read:

        Line 1 of 'package.json' is not what you expected, so the numbering has
        moved since you read it.
          you expected: {
            "name": "simple-to-do-list-app"
          line 1 is:  {
        That line is not in the file at all now.

    Three statements that contradict each other: it prints the line, prints the
    same line back, and then says the line is not in the file. Nothing in it
    could lead a reader to the newline that caused it.

    Forgiven rather than refused, which is what this module does with every
    other unambiguous transcription fault - line numbers, doubled backslashes,
    JSON escaping, indentation and blank lines are all already forgiven here.
    The first line is not a guess at what was meant: it is what the parameter
    is defined to carry.
    """
    for line in expected.splitlines():
        if line.strip():
            return line
    return expected


def _the_same_range_somewhere_else(
    lines: list[str],
    expect_start: str,
    expect_end: str,
    start_line: int,
    end_line: int,
) -> tuple[int, int] | None:
    """The range's new position when BOTH ends still match, else `None`.

    `_where_that_line_went` explains why a drifted edit is reported rather than
    applied: `expect_start` pins only the first line, so shifting the whole
    range by the same offset would delete whatever now sits at the other end.
    That reasoning is right, and it names its own remedy - pin the other end
    too.

    With both ends supplied this is no longer a guess. The range is moved only
    when the first line is found exactly once, the last line is found exactly
    once, and the gap between them is the length the caller asked for. Any other
    shape - either end missing, either end ambiguous, the range a different size
    than before - returns `None` and the caller refuses exactly as it did.

    Measured on the run of 2026-09-21: six of its twelve costly failures were
    this refusal on `task-manager/app.js`, every one recoverable and every one
    costing a model call to recover. Two examples, both with the numbering
    drifted by a line or two and the content otherwise intact.

    `expect_end` is optional, so a caller that sends only `expect_start` gets
    the old behaviour unchanged: reported, not applied.
    """
    if not expect_end.strip():
        return None

    wanted_start = _the_one_line_it_pins(expect_start).strip()
    if not wanted_start:
        return None

    starts = [n for n, line in enumerate(lines, 1) if line.strip() == wanted_start]
    if len(starts) != 1:
        return None
    for wanted_end in _the_lines_expect_end_may_pin(expect_end):
        found = _the_range_ending_at(lines, starts[0], wanted_end, start_line, end_line)
        if found is not None:
            return found
    return None


def _the_range_ending_at(
    lines: list[str], new_start: int, wanted_end: str, start_line: int, end_line: int,
) -> tuple[int, int] | None:
    """`_the_same_range_somewhere_else` for one reading of `expect_end`."""
    ends = [n for n, line in enumerate(lines, 1) if line.strip() == wanted_end]
    if len(ends) != 1:
        return None

    new_end = ends[0]
    if new_end < new_start:
        return None
    if (new_end - new_start) != (end_line - start_line):
        # The range is a different size than the caller described, so something
        # inside it changed as well. Refusing is right: the caller's `content`
        # was written against a range that no longer exists.
        return None
    return new_start, new_end


def _the_lines_expect_end_may_pin(expected: str) -> list[str]:
    """The lines a multi-line `expect_end` can mean, stripped, first reading first.

    `expect_end` pins one line, and callers that send several mean one of two
    things. Some send the pinned line and what follows it (the first line is
    the pin - see `_the_one_line_it_pins`). Others send the range's last lines
    and mean the final one: one run's `specialist_backend_2` sent
    `expect_end="  init();\n}"` for a range ending at the file's closing
    brace, and reading only the first line looked for `init();`, the line
    before it. Both are tried; neither is ever applied unless it matches the
    file exactly where the rest of the call says.
    """
    kept = [line.strip() for line in expected.splitlines() if line.strip()]
    if not kept:
        return [expected.strip()]
    return list(dict.fromkeys([kept[0], kept[-1]]))


#: How far a start line may be from where the call put it and still be taken as
#: miscounted rather than a different place. Reads come back without line
#: numbers, so a model counts them; the misses measured are one and two lines,
#: most often a blank line at the top of the window taken for none.
_MISCOUNT_TOLERANCE = 3


def _both_pins_found(
    lines: list[str], expect_start: str, expect_end: str
) -> tuple[int, int] | None:
    """The range two pins name, when each is the only such line in the file.

    A range whose ends are both miscounted, by different amounts, fits neither
    `_the_same_range_somewhere_else` (both moved together) nor
    `_the_start_miscounted` (the end is right). Measured on one run:
    `start_line=22, end_line=29` for a block whose first line was 18 and whose
    last was 22 - both pinned exactly. The refusal said "it is line 18 now ...
    send the same call with start_line=18 and end_line adjusted by the same
    amount", which would have replaced three lines too many.

    Only when nothing is left to guess: both pins given, each matching exactly
    one line, the end not before the start. The caller also declines a pinned
    range longer than the one asked for - that is a line added between the
    pins, not a miscount.
    """
    wanted_start = _the_one_line_it_pins(expect_start).strip()
    if not wanted_start or not expect_end.strip():
        return None
    starts = [n for n, line in enumerate(lines, 1) if line.strip() == wanted_start]
    if len(starts) != 1:
        return None
    for wanted_end in _the_lines_expect_end_may_pin(expect_end):
        ends = [n for n, line in enumerate(lines, 1) if line.strip() == wanted_end]
        if len(ends) == 1 and ends[0] >= starts[0]:
            return starts[0], ends[0]
    return None


def _the_start_miscounted(
    lines: list[str],
    expect_start: str,
    expect_end: str,
    start_line: int,
    end_line: int,
) -> int | None:
    """The real first line of a range whose END is right and whose start is not.

    `_the_same_range_somewhere_else` moves a range only when both ends moved
    together, which is the file changing. A miscount moves one end. One run's
    `specialist_backend_2` read lines 201-254 of `app.js`, whose line 201 is
    blank, and sent `start_line=201` for the comment on line 202 with
    `end_line=254` and `expect_end` naming line 254 correctly. It was refused,
    re-read the file, and sent the identical call again.

    Applied only when every part of it is pinned: the end is exactly where the
    call says, `expect_start` is on exactly one line of the file, and that line
    is within `_MISCOUNT_TOLERANCE` of `start_line` and before the end.
    """
    if not expect_end.strip() or not 1 <= end_line <= len(lines):
        return None
    wanted_start = _the_one_line_it_pins(expect_start).strip()
    if not wanted_start:
        return None
    if lines[end_line - 1].strip() not in _the_lines_expect_end_may_pin(expect_end):
        return None
    starts = [n for n, line in enumerate(lines, 1) if line.strip() == wanted_start]
    if len(starts) != 1:
        return None
    found = starts[0]
    if found > end_line or abs(found - start_line) > _MISCOUNT_TOLERANCE:
        return None
    return found


def _what_went_unchecked(expect_start: str, replaced: str, content: str) -> str:
    """Say what an unguarded replacement actually removed, or "".

    `expect_start` is optional, and the one time it was omitted in the completed
    run of 2026-09-21 it cost the product a requirement.
    `specialist_ui_ux_1` sent::

        replace_lines(relative_path="task-manager/index.html",
                      start_line=5, end_line=5,
                      content='  <meta http-equiv="Content-Security-Policy" ...>')

    Line 5 was `<meta name="viewport" content="width=device-width, ...">`. The
    intent was plainly to *add* a Content-Security-Policy tag; the effect was to
    replace the viewport tag with it, and the stylesheet's three width media
    queries became unreachable on every phone. The brief required "Responsive
    design for mobile and desktop". Forty-seven end-to-end tests, a security
    review and five milestone reviews all passed afterwards.

    Nothing in the result said what had been removed. The tool reported
    "Replaced lines 5-5 of 39", which is true and tells the reader nothing about
    the line that is now gone.

    So an unguarded replacement quotes what it deleted. Only when `expect_start`
    was not sent - with it, the caller has already said what it expected and the
    tool has already checked - and only when the replacement is not obviously a
    rewrite of the same line, because echoing an edit back to someone who just
    made it deliberately is noise.
    """
    if expect_start.strip() or not replaced.strip():
        return ""
    gone = replaced.strip().splitlines()
    kept = content.strip().splitlines()
    # A line the replacement clearly derives from is not a surprise.
    if gone and kept and gone[0][:24].strip() and gone[0][:24] in content:
        return ""
    shown = _clip(gone[0]) if gone else ""
    more = f" (and {len(gone) - 1} more line(s))" if len(gone) > 1 else ""
    return (
        f"\n\nNo `expect_start` was sent, so nothing checked what was there. "
        f"What this removed: {shown}{more}. If you meant to add lines rather "
        "than replace them, put what was removed back: `replace_lines` has no "
        "insert mode, so an addition is a replacement whose `content` keeps the "
        "original line. Pass `expect_start` so the tool can refuse a line you did "
        "not mean."
    )


#: Why a pinned line was not where the call said, without guessing which. The
#: file may have changed since it was read, or the count was off by a few; the
#: position reported after this is the file as it is now either way.
_EITHER_IT_CHANGED_OR_IT_WAS_MISCOUNTED = (
    "Either the file changed after you read it or the line was counted wrong; "
    "the position below is read from the file as it is now."
)


def _the_line_its_content_rewrites(
    lines: list[str], expected: str, start_line: int, end_line: int, content: str
) -> str:
    """Advice for a one-line edit whose pin is the line *before* the one it rewrites, or "".

    `expect_start` is the first line being replaced. A model sometimes sends
    the line above instead, as an anchor - "the line after this one". Measured
    on one run: `start_line` 13, a `content` that commented out line 13's
    assertion, and `expect_start` quoting line 12. The refusal found the pin at
    line 12 and said "send the same call with start_line=12", which would have
    replaced the wrong assertion with the commented-out other one. The stage
    sent the identical call twice more.

    Only when the line number is the one the content belongs to: one line
    replacing one line, the replacement closer to the line at `start_line`
    than to the pinned line, and the pin sitting directly above.
    """
    import difflib

    if start_line != end_line or not 1 <= start_line <= len(lines):
        return ""
    new = content.strip()
    if not new or "\n" in new:
        return ""
    here = lines[start_line - 1].strip()
    pinned = expected.strip()
    if not here or start_line < 2 or lines[start_line - 2].strip() != pinned:
        return ""

    def alike(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()

    if not (here in new or alike(new, here) >= 0.7) or alike(new, here) <= alike(new, pinned):
        return ""
    return (
        f"Your `content` reads as line {start_line} rewritten, and line {start_line} is "
        f"what this call would replace - so the line number is right and the pin is "
        f"not: `expect_start` quotes the first line being REPLACED, and you sent the "
        f"line above it (line {start_line - 1}). Send the same call with "
        f"`expect_start` set to line {start_line} as it is now:\n"
        f"  {_clip(here)}\n"
        "Do not move `start_line`. Nothing was changed."
    )


def _where_that_line_went(lines: list[str], expected: str, asked_for: int) -> str:
    """Where the line the caller expected actually is now.

    "Read the file again and use the new line numbers" costs a read of the
    whole file and a second attempt, to rediscover something this function
    already has in its hands.

    Measured on one run: three of the run's ten costly failures were
    this refusal, and in every one the expected line was two or three lines
    from where the caller looked - `specialist_testing_2` asked for
    `export function renderTaskList(...)` at line 195 twice, and it was at
    197 both times.

    Reports rather than applies. `expect_start` pins only the FIRST line, so
    shifting the whole range by the same offset would delete whatever now
    sits at the other end, and this tool exists because a wrong guess about
    position is expensive.
    """
    wanted = expected.strip()
    if not wanted:
        return "Read the file again and use the new line numbers. Nothing was changed."
    found = [n for n, line in enumerate(lines, 1) if line.strip() == wanted]
    if not found:
        # The line with its end left off, somewhere else: `function reset()`
        # for `function reset() {`. At the line asked for that is forgiven
        # (`_the_line_it_cut_short`); here it was reported as gone.
        start = _without_the_ellipsis_it_ended_on(expected)
        if len(start) >= _A_PREFIX_THAT_PINS:
            found = [n for n, line in enumerate(lines, 1) if line.strip().startswith(start)]
    if not found:
        return (
            "That line is not in the file at all now - it may have been "
            "changed or removed since you read it. Read the file again. "
            "Nothing was changed."
        )
    if len(found) == 1:
        moved = found[0]
        shift = moved - asked_for
        direction = f"{abs(shift)} line{'s' if abs(shift) != 1 else ''} " + (
            "further down" if shift > 0 else "further up"
        )
        return (
            f"It is line {moved} now, {direction}. Send the same call with "
            f"start_line={moved} and end_line adjusted by the same amount. "
            "You do not need to read the file again. Nothing was changed."
        )
    where = ", ".join(str(n) for n in found[:6])
    return (
        f"That line appears {len(found)} times now, at lines {where}. Pass the "
        "one you meant as `start_line`, with `end_line` adjusted by the same "
        "amount. Nothing was changed."
    )


#: Lines of a replaced range quoted back when the edit is refused.
MOST_REPLACED_LINES_QUOTED = 8


def _bracket_balance(text: str) -> int:
    """Openers minus closers, counting (), [] and {} alike. Strings are not skipped:
    this compares two texts from the same file, where they cancel out."""
    return sum(text.count(c) for c in "([{") - sum(text.count(c) for c in ")]}")


_HOW_TO_ADD_AROUND_A_LINE = (
    "`replace_lines` has no insert mode: to add after line {last}, begin `content` "
    "with that line as it is; to add before line {start}, end `content` with it."
)


#: A line that opens with one diff marker, then the text it marks. `--` and
#: `++` are left alone: they open decrements, comments and separators in many
#: languages, and a diff marks a line with one character.
_A_DIFF_LINE = re.compile(r"^([+-])(?![+-])(.*\S.*)$")


#: The lines a patch format wraps its changes in.
_A_PATCH_ENVELOPE_LINE = re.compile(
    r"^\s*\*{3}\s*(?:Begin Patch|End Patch|(?:Update|Add|Delete) File:|End of File)\b", re.I
)


def _written_as_a_diff(content: str, original: str) -> str:
    """A note when a refused `content` reads as a diff rather than new text, or "".

    Measured on one run: `defect_fix_1_1` sent
    `-      }));\\n+      completed: Boolean(t.completed)\\n+      }));` as the
    content of a `replace_lines` - a patch, which `content` is not - and was
    told "Unexpected token '-'" four times in a row, the last two by the repeat
    guard, without ever learning why. `defect_fix_1_2` then did the same.

    Asked only of an edit already refused for breaking the file, so it can
    never stop one that would have worked. It names markers only on lines whose
    marked text is in the file already, or when both `+` and `-` lines appear:
    a lone `- item` in a list is not a diff.

    Or when every marker is a `+` and the lines around them are the file's own.
    That is a patch which only adds - context lines kept, new lines marked - and
    it was the shape neither rule above saw: one run's fix stage sent
    `on(event, callback) {` and two more lines from the file, then
    `+        callback({ ...this.state });`, was told "Unexpected token" three
    times, and returned saying it could not do the task.
    """
    envelope = next(
        (
            (number, line.strip())
            for number, line in enumerate(content.splitlines(), 1)
            if _A_PATCH_ENVELOPE_LINE.match(line)
        ),
        None,
    )
    if envelope is not None:
        # The wrapper of a patch format, with or without marked lines inside
        # it. One run's fix stage ended four edits in a row with
        # `*** End Patch ***` and was told "Unexpected token '**'" each time.
        return (
            f"\n\nLine {envelope[0]} of your `content` is `{envelope[1]}`, which is "
            "the wrapper of a patch format and not part of any file. `content` is "
            "the new text of those lines exactly as the file should hold them: "
            "leave that line out, along with any `*** Begin Patch` or "
            "`*** Update File:` line and any leading '+' or '-'."
        )
    held = {line.strip() for line in original.splitlines() if line.strip()}
    marked = []
    unmarked = []
    for number, line in enumerate(content.splitlines(), 1):
        found = _A_DIFF_LINE.match(line)
        if found:
            marked.append((number, found.group(1), found.group(2).strip()))
        elif line.strip():
            unmarked.append(line.strip())
    if not marked:
        return ""
    signs = {sign for _, sign, _ in marked}
    both = signs == {"+", "-"}
    additions_among_the_file_s_own_lines = signs == {"+"} and any(
        text in held for text in unmarked
    )
    if (
        not both
        and not additions_among_the_file_s_own_lines
        and not any(text in held for _, _, text in marked)
    ):
        return ""
    number, sign, _ = marked[0]
    return (
        f"\n\nLine {number} of your `content` begins with '{sign}', which reads as a "
        "diff marker. `content` is the new text of those lines exactly as the file "
        "should hold them, not a patch: leave out every line you meant to remove "
        "(the '-' lines), and drop the leading '+' from every line you meant to add."
    )


def _a_diff_that_parses(relative_path: str, content: str, original: str, *, editing: bool) -> str | None:
    """The refusal for `content` that is a diff of the file, or None.

    `_written_as_a_diff` explains an edit already refused for breaking the
    file. A diff can also parse. Measured on one run: a fix stage sent
    `this.tasks.push(task);`, `-      this._emitUpdate();`,
    `+      storage.saveTasks(this.tasks);`, `+      this._emitUpdate();` as a
    `replace_lines` content. JavaScript reads `-x()` and `+x()` as unary minus
    and plus, so `node --check` passed, the edit was written, and the product
    shipped with the diff in it - the removed call made twice instead of once.

    Code only, and only both signs with a `-` line the file already holds:
    the removal marker on a line that is there is what makes it a diff and not
    a list or an expression.
    """
    from app.analysis.file_kinds import classify_file

    if classify_file(relative_path) == "document":
        return None
    held = {line.strip() for line in original.splitlines() if line.strip()}
    marked = [
        (number, found.group(1), found.group(2).strip())
        for number, line in enumerate(content.splitlines(), 1)
        if (found := _A_DIFF_LINE.match(line))
    ]
    removed = [(number, text) for number, sign, text in marked if sign == "-" and text in held]
    if not removed or not any(sign == "+" for _, sign, _ in marked):
        return None
    number, text = removed[0]
    verb = "change" if editing else "write"
    return (
        f"Refusing to {verb} '{relative_path}': line {number} of what you sent is "
        f"`-{text}` - a line this file already holds, marked for removal - and there "
        "are '+' lines beside it, so this is a diff, not the file's text. The parser "
        "would have accepted it (`-x()` and `+x()` are expressions), which is how one "
        "reached a product before. Nothing was written. Send the lines exactly as "
        "the file should hold them: leave out every '-' line and drop the leading "
        "'+' from every line you add."
    )


_WHERE_JSON_STOPPED = re.compile(r"not valid JSON at line (\d+)")


def _the_lines_json_stopped_at(refusal: str, updated: str) -> str:
    """The lines of the edited file around where a JSON parser gave up, or "".

    The JavaScript refusal quotes what the edit would have produced; the JSON
    one named a line and a column of a file the caller has never seen, because
    it is the file as it would be after the edit.
    """
    found = _WHERE_JSON_STOPPED.search(refusal)
    if not found:
        return ""
    after = updated.splitlines()
    at = int(found.group(1)) - 1
    if not 0 <= at < len(after):
        return ""
    return (
        "\n\nThis is what the file would hold around that line (> marks it). A "
        "parser reports where it gave up, which is usually the line after the "
        "one missing a comma or a bracket:\n"
        + _quote(after, max(0, at - 3), min(len(after), at + 2), at)
    )


def _the_end_it_pinned(
    target: Path,
    lines: list[str],
    start_line: int,
    last: int,
    expect_end: str,
    content: str,
    relative_path: str,
) -> tuple[int, str] | None:
    """The last line `expect_end` names, when `end_line` missed it by a little.

    `expect_end` was read only when the start had moved. Measured on one run:
    `expect_end="});"` with `end_line=24` for a block whose `});` is line 25 -
    the pin was right and the count one short - refused twice in one stage for
    unbalanced brackets, and the same shape a dozen times across the sprint.

    Asked only of an edit already refused for breaking the file, and answered
    only with an end the pin names, within `_MISCOUNT_TOLERANCE` lines, whose
    edit passes the checks a write does. The nearest such line wins. Returns
    `(last, updated)` or None.
    """
    if not expect_end.strip() or not 1 <= last <= len(lines):
        return None
    pins = _the_lines_expect_end_may_pin(expect_end)
    if lines[last - 1].strip() in pins:
        return None
    nearby = sorted(
        (
            n for n in range(max(start_line, last - _MISCOUNT_TOLERANCE),
                             min(len(lines), last + _MISCOUNT_TOLERANCE) + 1)
            if n != last and lines[n - 1].strip() in pins
        ),
        key=lambda n: (abs(n - last), n < last),
    )
    for new_last in nearby:
        body = content
        if body and not body.endswith("\n") and lines[new_last - 1].endswith("\n"):
            body += "\n"
        updated = "".join(lines[:start_line - 1]) + body + "".join(lines[new_last:])
        try:
            _refuse_if_broken(relative_path, updated, editing=True)
            _refuse_if_node_cannot_parse(target, relative_path, updated, editing=True)
        except RepositoryToolError:
            continue
        return new_last, updated
    return None


#: Lines outside a range that its `content` may be found to repeat, each side.
MOST_OVERLAPPING_LINES = 6


def _the_range_its_content_overlaps(
    target: Path, lines: list[str], start_line: int, last: int, content: str, relative_path: str
) -> tuple[int, int, str] | None:
    """The wider range a refused `content` was written for, and the file it gives.

    A `replace_lines` whose `content` opens or closes with the lines just
    outside its range - the function's header above it, the closing brace
    below - writes those lines twice. Measured on one run: 24 edits refused
    for breaking the file they changed, most of them this, each told the
    brackets did not balance and several sent again unchanged. One sent four
    lines ending `transform: {},` and `};` for a range that stopped one line
    short of the `transform: {},` and `};` already there.

    Asked only of an edit already refused for breaking the file, and answered
    only when the widened edit parses, so it can never change an edit that
    would have worked, nor apply one that leaves the file broken. Lines are
    compared ignoring indentation, and a run of blank lines alone is not an
    overlap. Returns `(start, last, updated)` or None.
    """
    sent = content.splitlines()
    if len(sent) < 2:
        return None

    def same(ours: list[str], theirs: list[str]) -> bool:
        ours = [line.strip() for line in ours]
        return ours == [line.strip() for line in theirs] and any(ours)

    def says_something(up: int, down: int) -> bool:
        # A repeated line of brackets alone is not evidence of anything: every
        # block ends in one. One run's edit dropped the `"devDependencies": {`
        # line and kept the `}` that closed it; widening the range over the
        # file's own closing `}` made it parse, and left the three packages as
        # top-level keys of a manifest with no devDependencies at all.
        repeated = sent[:up] + (sent[-down:] if down else [])
        return any(re.search(r"\w", line) for line in repeated)

    below = [
        k for k in range(1, min(MOST_OVERLAPPING_LINES, len(sent) - 1, len(lines) - last) + 1)
        if same(sent[-k:], lines[last:last + k])
    ]
    above = [
        k for k in range(1, min(MOST_OVERLAPPING_LINES, len(sent) - 1, start_line - 1) + 1)
        if same(sent[:k], lines[start_line - 1 - k:start_line - 1])
    ]
    # The longest overlap first, one side before both: the least widening that
    # yields a file the parser accepts.
    candidates = (
        [(0, k) for k in reversed(below)]
        + [(k, 0) for k in reversed(above)]
        + [(up, down) for up in reversed(above) for down in reversed(below)]
    )
    for up, down in candidates:
        if up + down >= len(sent) or not says_something(up, down):
            continue
        new_start, new_last = start_line - up, last + down
        body = content
        if body and not body.endswith("\n") and "".join(lines[new_start - 1:new_last]).endswith("\n"):
            body += "\n"
        updated = "".join(lines[:new_start - 1]) + body + "".join(lines[new_last:])
        try:
            _refuse_if_broken(relative_path, updated, editing=True)
            _refuse_if_node_cannot_parse(target, relative_path, updated, editing=True)
        except RepositoryToolError:
            continue
        return new_start, new_last, updated
    return None


#: A line that only closes brackets: `}`, `});`, `],`, `)`.
_ONLY_CLOSING = re.compile(r"^\s*[\]\)\}]+\s*[;,]?\s*$")

#: The most closing lines at the end of a range that its `content` may be
#: found to have left out.
MOST_CLOSING_LINES_LEFT_OUT = 3


def _the_closing_lines_it_left_out(
    target: Path, lines: list[str], start_line: int, last: int, content: str, relative_path: str
) -> tuple[int, str] | None:
    """The shorter range a refused `content` was written for, and the file it gives.

    The opposite slip to `_the_range_its_content_overlaps`: a range that runs
    one line past what `content` replaces, over a line that only closes a
    bracket. Measured on one run: `package.json` lines 17-18 held
    `"playwright": "^1.45.0"` and the `}` closing `devDependencies`; the
    content was that line with a comma and one new dependency, and no `}`.
    Refused twice, identically, for invalid JSON - the stage was told the
    lines closed one more bracket than its content, and sent the same call.

    Asked only of an edit already refused for breaking the file, and answered
    only when keeping those closing lines gives a file the parser accepts, so
    it never changes an edit that would have worked. Returns `(last, updated)`
    or None.
    """
    sent = [line.strip() for line in content.splitlines() if line.strip()]
    for k in range(1, min(MOST_CLOSING_LINES_LEFT_OUT, last - start_line) + 1):
        kept = lines[last - k:last]
        if not all(_ONLY_CLOSING.match(line) for line in kept):
            break
        if sent[-k:] == [line.strip() for line in kept]:
            # It does close them itself; the fault is elsewhere.
            break
        new_last = last - k
        if len(sent) < sum(1 for line in lines[start_line - 1:new_last] if line.strip()):
            # Shorter than what it would still replace: it leaves lines out, and
            # which ones is a guess. Replacing `it(...) {` and its body with the
            # `it(...) {` line alone parses, and silently deletes the body.
            break
        body = content
        if body and not body.endswith("\n"):
            body += "\n"
        updated = "".join(lines[:start_line - 1]) + body + "".join(lines[new_last:])
        updated = _json_with_its_commas_put_right(target, relative_path, updated)
        try:
            _refuse_if_broken(relative_path, updated, editing=True)
            _refuse_if_node_cannot_parse(target, relative_path, updated, editing=True)
        except RepositoryToolError:
            continue
        return new_last, updated
    return None


def _the_overlap_in_words(above: int, below: int) -> str:
    def count(n: int) -> str:
        return f"{n} line{'s' if n != 1 else ''}"

    parts = []
    if above:
        parts.append(f"opens with the {count(above)} just above that range")
    if below:
        parts.append(f"ends with the {count(below)} just below it")
    return " and ".join(parts)


def _what_the_range_held(
    lines: list[str], start: int, last: int, expect_start: str, content: str = ""
) -> str:
    """The lines a refused `replace_lines` would have removed, numbered.

    A refusal quoted the text the edit would produce, and never the text it
    would remove - which is the half that shows a stale range. Measured on one
    run's `specialist_documentation_3`, in parallel mode: lines 127-130 had
    moved under it since it read them, the range now ended on the first line
    of `filterTasks`, and the refusal said "Illegal return statement" at a body
    whose function header had been replaced by a comment block.
    """
    held = lines[start - 1:last]
    shown = held[:MOST_REPLACED_LINES_QUOTED]
    quoted = "".join(
        f"  {number:>4} | {text.rstrip()}\n" for number, text in enumerate(shown, start)
    )
    more = f"  ... and {len(held) - len(shown)} more\n" if len(held) > len(shown) else ""
    advice = (
        "If those are not the lines you meant, the file changed since you read it: "
        "read that part again, or send `expect_start` and `expect_end` so the edit "
        "follows the text wherever it has moved."
        if not expect_start
        else "Check those against what you meant to replace."
    )
    # One run's `specialist_testing_1` meant to append two blocks after a
    # file's last line, `});`, and replaced that line with them instead. The
    # refusal quoted `});` and the model sent the same edit again before
    # seeing that its content no longer held it.
    # Presence alone cannot tell: that content ended with a `});` of its own.
    # What it could not do is close the block the replaced line closed.
    difference = _bracket_balance("".join(held)) - _bracket_balance(content)
    dropped = [text.strip() for text in held if text.strip() and text.strip() not in content]
    if difference:
        advice = (
            f"Those lines {'close' if difference < 0 else 'open'} {abs(difference)} "
            f"more bracket{'s' if abs(difference) != 1 else ''} than your `content` "
            "does, so replacing them leaves the file unbalanced. "
            + _HOW_TO_ADD_AROUND_A_LINE.format(start=start, last=last)
            + " "
            + advice
        )
    elif dropped:
        advice = (
            f"Your `content` does not contain {_clip(dropped[0])!r}"
            + (f" or {len(dropped) - 1} more of those lines" if len(dropped) > 1 else "")
            + ", so this edit deletes it. "
            + _HOW_TO_ADD_AROUND_A_LINE.format(start=start, last=last)
            + " "
            + advice
        )
    return f"\n\nThe lines this edit would have replaced, {start}-{last}, hold:\n{quoted}{more}{advice}"


def replace_approved_lines(
    repo_root: str | Path,
    relative_path: str,
    start_line: int,
    end_line: int,
    content: str,
    expect_start: str = "",
    expect_end: str = "",
) -> dict[str, str]:
    """Replace a numbered range of lines, with no text to transcribe.

    Why this exists. Swept across 45 stored transcripts on 2026-09-19:
    "Could not find that text" was 247 of 371 costly tool failures, 67%, and
    the largest single cause by a factor of eight. The repair chain already
    forgave line numbers, doubled backslashes, JSON escaping, indentation and
    blank lines, and replaying the real failures against it resolved 7 of 75 -
    so transcription repair had reached its limit.

    The measurement that redirected this: of 330 failed edits, 294 were
    against a file the same stage had already read. The model is not editing
    blind. It reads the file and still cannot reproduce a passage from it
    byte for byte, because reproducing bytes from context is the hard part
    and it is a requirement this tool invented.

    A line range removes the requirement. `read_file` numbers every line it
    returns, so "replace lines 21 to 23" is something the model can read off
    the output it already has, and there is nothing to quote, escape or
    indent. No language is special: a line range means the same thing in Go,
    Rust, Ruby and Markdown.

    `expect_start` is an optional guard against stale numbers, compared with
    surrounding whitespace ignored. It is checked loosely on purpose: a strict
    comparison would put back the exact-transcription requirement this tool
    exists to remove.

    Inputs:
        start_line: 1-based, inclusive.
        end_line: 1-based, inclusive. Equal to `start_line` replaces one line.
        content: the replacement text. Empty deletes the range.
        expect_start: optional. The first line as you read it, for safety.
        expect_end: optional. The LAST line of the range as you read it. Send
            it whenever you send `expect_start`: with both ends pinned, an edit
            whose line numbers have drifted is applied at the range's new
            position instead of being refused, and costs you nothing.
    """
    content = _content_without_a_copied_gutter(content, start_line)
    root, target = _guard_a_targeted_change(repo_root, relative_path, content)

    with _MUTATION_LOCK:
        original = target.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        total = len(lines)

        if start_line == total + 1 and end_line in (total, start_line) and content.strip():
            # The line after the last one: there is nothing there to replace, so
            # this is "add these lines at the end", and it means nothing else.
            # Measured on two runs: `start_line 115, end_line 114` on a 114-line
            # file was "not a range", `start_line 115` alone was "line 115 does
            # not exist", and the stage fell back to an `edit_artifact` whose
            # `find` matched 44 times.
            pinned = _the_one_line_it_pins(expect_start).strip() if expect_start else ""
            if pinned and total and pinned != lines[-1].strip():
                raise RepositoryToolError(
                    f"'{relative_path}' has {total} lines, so line {start_line} is the "
                    "line after its last and this call would add your `content` at "
                    "the end of the file. `expect_start` does not match the last line, "
                    f"which is:\n  {_clip(lines[-1].strip())}\n"
                    "If the end of the file is where you mean, send the call again "
                    "without `expect_start`. Nothing was changed."
                )
            joined = original if not original or original.endswith("\n") else original + "\n"
            body = content if content.endswith("\n") else content + "\n"
            updated = joined + body
            _write_unless_it_changes_nothing(target, original, updated, relative_path)
            added = len(body.splitlines())
            return _edited(
                target, root, relative_path, content,
                f"Added {added} line{'s' if added != 1 else ''} after line {total}, the "
                f"last line: there was no line {start_line} to replace. The file now "
                f"has {len(updated.splitlines())} lines.",
                "",
            )
        if start_line < 1 or end_line < start_line:
            raise RepositoryToolError(
                f"Line range {start_line}-{end_line} is not a range. Lines are "
                "numbered from 1 and `end_line` must not be before `start_line`."
            )
        if start_line > total:
            raise RepositoryToolError(
                f"'{relative_path}' has {total} line{'s' if total != 1 else ''}, so "
                f"line {start_line} does not exist. Read the file to see the "
                "current numbering - a previous edit may have shortened it."
            )
        # A range running past the end is clamped rather than refused: asking to
        # replace "from line 40 to the end" by naming a generous end is
        # reasonable, and refusing it costs a call to learn the line count.
        last = min(end_line, total)

        shifted_note = ""
        expect_start = _without_the_escapes_it_doubled(
            _without_a_copied_gutter(expect_start, lines), lines
        )
        expect_end = _without_the_escapes_it_doubled(
            _without_a_copied_gutter(expect_end, lines), lines
        )
        if expect_start:
            actual_first = lines[start_line - 1]
            # One line, whatever arrived. A caller that sent two could not match
            # anything and was told the line was not in the file while the
            # message printed it - see `_the_one_line_it_pins`.
            pinned = _the_one_line_it_pins(expect_start)
            if pinned.strip() != expect_start.strip():
                shifted_note = (
                    " `expect_start` pins one line and this call sent "
                    f"{len(expect_start.strip().splitlines())}; only its first "
                    "line was compared."
                )
            expect_start = _the_line_it_cut_short(
                _without_the_quotes_it_added(pinned, actual_first), actual_first
            )
            if expect_start.strip() != actual_first.strip():
                moved = _the_same_range_somewhere_else(
                    lines, expect_start, expect_end, start_line, end_line
                )
                real_start = (
                    _the_start_miscounted(lines, expect_start, expect_end, start_line, end_line)
                    if moved is None else None
                )
                both = (
                    _both_pins_found(lines, expect_start, expect_end)
                    if moved is None and real_start is None else None
                )
                if both is not None and both[1] - both[0] > end_line - start_line:
                    # Longer than the range that was asked for: something has
                    # been put between the pins since they were read, and the
                    # replacement was not written with it in view.
                    both = None
                if both is not None:
                    shifted_note += (
                        f" Neither line number was where its pin is: `expect_start` "
                        f"is line {both[0]} and `expect_end` is line {both[1]}, each "
                        f"the only such line in the file. Lines {both[0]}-{both[1]} "
                        f"were replaced, not {start_line}-{end_line}."
                    )
                    moved = both
                    real_start = both[0]
                elif real_start is not None:
                    shifted_note += (
                        f" Line {start_line} was miscounted: the line you pinned "
                        f"with `expect_start` is line {real_start}, and line "
                        f"{end_line} is the last line you pinned, as you said. "
                        f"Lines {real_start}-{end_line} were replaced."
                    )
                    moved = (real_start, end_line)
                elif moved is None:
                    # The range is gone and what was to replace it is there:
                    # the edit has been made, usually by this stage. One run's
                    # `specialist_backend_0` changed an import line with
                    # `edit_artifact`, then sent `replace_lines` for the same
                    # change four times, each told "read the file again".
                    done_at = _already_applied(original, expect_start.strip(), content)
                    if done_at:
                        return _already_there(target, root, relative_path, content, done_at)
                    # Not "the numbering has moved": that blames a change the
                    # file may never have had. One run's `specialist_backend_0`
                    # read `app.js`, sent `let filterMode` as line 151 when it
                    # was 154, was told the numbering had moved, and read the
                    # unchanged file twice more before rewriting all of it.
                    raise RepositoryToolError(
                        f"Line {start_line} of '{relative_path}' is not what you "
                        f"expected. {_EITHER_IT_CHANGED_OR_IT_WAS_MISCOUNTED}\n"
                        f"  you expected: {_clip(expect_start.strip())}\n"
                        f"  line {start_line} is:  {_clip(actual_first.strip())}\n"
                        + (
                            _the_line_its_content_rewrites(
                                lines, expect_start, start_line, end_line, content
                            )
                            or _where_that_line_went(lines, expect_start, start_line)
                        )
                    )
                new_start, new_end = moved
                shift = new_start - start_line
                shifted_note += "" if real_start is not None else (
                    f" The numbering had moved: lines {start_line}-{end_line} are "
                    f"now {new_start}-{new_end}, "
                    f"{abs(shift)} line{'s' if abs(shift) != 1 else ''} "
                    + ("further down" if shift > 0 else "further up")
                    + ". Both ends matched what you expected, so the edit was "
                    "applied there rather than refused."
                )
                start_line, end_line = new_start, new_end
                last = min(end_line, total)

        replaced = "".join(lines[start_line - 1:last])
        # Keep the file's own line ending on the replacement, so replacing the
        # last line of a file that ends with a newline does not silently drop it.
        body = content
        if body and not body.endswith("\n") and replaced.endswith("\n"):
            body += "\n"
        updated = "".join(lines[:start_line - 1]) + body + "".join(lines[last:])

        a_diff = _a_diff_that_parses(relative_path, content, original, editing=True)
        if a_diff is not None:
            raise RepositoryToolError(a_diff)

        # Only when the edit is what breaks it. A file that arrived broken is
        # being repaired, and refusing every step that has not yet finished
        # the repair is the trap measured on one run - four consecutive
        # refusals at lines 22, 59, 83 and 72 of one file, the moving line
        # number showing the model was getting closer each time. See the same
        # rule in `_write_unless_it_changes_nothing`.
        updated = _json_with_its_commas_put_right(target, relative_path, updated)
        try:
            if _what_is_structurally_wrong(target, relative_path, original) is None:
                # As an edit, so the refusal is in this tool's terms. Without
                # it a range that left `package.json` one comma short was
                # answered "Refusing to write ... Send the file again as
                # complete, valid JSON", and the stage did: three whole-file
                # writes and a delete, for a comma.
                _refuse_if_broken(relative_path, updated, editing=True)
            _write_unless_it_changes_nothing(target, original, updated, relative_path)
        except RepositoryToolError as exc:
            # Only a refusal about the file's syntax. A refusal that the edit
            # changes nothing, or undoes a recent one, is not about the range.
            said = str(exc).lower()
            if "parse" not in said and "not valid " not in said:
                raise
            exc = RepositoryToolError(
                str(exc).replace("Fix `replace` and send", "Fix `content` and send")
                + _the_lines_json_stopped_at(str(exc), updated)
            )
            pinned_end = _the_end_it_pinned(
                target, lines, start_line, last, expect_end, content, relative_path
            )
            if pinned_end is not None:
                new_last, updated = pinned_end
                _write_unless_it_changes_nothing(target, original, updated, relative_path)
                note = (
                    f"Replaced lines {start_line}-{new_last} of {total}, not "
                    f"{start_line}-{last}: `expect_end` names line {new_last}, and "
                    f"`end_line` was {abs(new_last - last)} line"
                    f"{'s' if abs(new_last - last) != 1 else ''} off it. Replacing "
                    "only the range you gave would have left the file unparseable. "
                    f"The file now has {len(updated.splitlines())} lines." + shifted_note
                )
                return _edited(
                    target, root, relative_path, content, note,
                    "".join(lines[start_line - 1:new_last]),
                )
            wider = _the_range_its_content_overlaps(
                target, lines, start_line, last, content, relative_path
            )
            if wider is not None:
                new_start, new_last, updated = wider
                _write_unless_it_changes_nothing(target, original, updated, relative_path)
                note = (
                    f"Replaced lines {new_start}-{new_last} of {total}, not "
                    f"{start_line}-{last}: your `content` "
                    + _the_overlap_in_words(start_line - new_start, new_last - last)
                    + ", so replacing only the range you gave would have "
                    "written those lines twice and left the file unparseable. "
                    f"The file now has {len(updated.splitlines())} lines." + shifted_note
                )
                return _edited(
                    target, root, relative_path, content, note,
                    "".join(lines[new_start - 1:new_last]),
                )
            shorter = _the_closing_lines_it_left_out(
                target, lines, start_line, last, content, relative_path
            )
            if shorter is not None:
                new_last, updated = shorter
                _write_unless_it_changes_nothing(target, original, updated, relative_path)
                kept = last - new_last
                note = (
                    f"Replaced lines {start_line}-{new_last} of {total}, not "
                    f"{start_line}-{last}: the last {kept} line"
                    f"{'s' if kept != 1 else ''} of that range only close"
                    f"{'' if kept != 1 else 's'} a bracket, and your `content` does "
                    "not, so replacing the whole range would have left the file "
                    "unparseable. Kept: "
                    + " ".join(line.strip() for line in lines[new_last:last])
                    + f". The file now has {len(updated.splitlines())} lines."
                    + shifted_note
                )
                return _edited(
                    target, root, relative_path, content, note,
                    "".join(lines[start_line - 1:new_last]),
                )
            raise RepositoryToolError(
                f"{exc}{_written_as_a_diff(content, original)}"
                f"{_what_the_range_held(lines, start_line, last, expect_start, content)}"
            ) from exc
        note = (
            f"Replaced lines {start_line}-{last} of {total}. "
            f"The file now has {len(updated.splitlines())} lines."
            + shifted_note
            + _what_went_unchecked(expect_start, replaced, content)
        )
        return _edited(target, root, relative_path, content, note, replaced)


def edit_approved_artifact(
    repo_root: str | Path, relative_path: str, find: str, replace: str
) -> dict[str, str]:
    """Replace one exact passage inside an existing artifact.

    Purpose:
        Change part of a document without regenerating it. `write_approved_artifact`
        replaces a whole file, which is the only reason a 71KB specification had to
        be rewritten end to end to correct a single contradictory sentence. Asked to
        do that, an agent produced a shorter second file called
        `technical_specification_v2.md` instead, and the reviewer then read both and
        reported the differences between them as contradictions in the design.

    Inputs:
        find: the exact text to replace. Must appear exactly once.
        replace: what to put in its place. Empty string deletes the passage.

    Errors:
        RepositoryToolError if the file is missing, or if `find` appears zero or
        several times. Both refusals say what to do next, because a silent
        first-match replacement in a long document corrupts it somewhere the
        agent is not looking.
    """
    # Shared with `replace_approved_lines` - see `_guard_a_targeted_change`.
    # These were inline here while this was the only tool that changed part of
    # a file; a second one would have had to copy nine checks or quietly go
    # without them.
    root, target = _guard_a_targeted_change(repo_root, relative_path, replace)
    if not find:
        raise RepositoryToolError(
            "The `find` text is empty. Give the exact passage to replace, or use "
            "write_artifact to replace the whole file, or use replace_lines to "
            "change a numbered range without quoting it."
        )

    # Read, replace and write as one step. Parallel tool calls in the same turn
    # would otherwise each replace a passage in their own copy of the file and
    # overwrite one another, reporting success for changes that were discarded.
    with _MUTATION_LOCK:
        original = target.read_text(encoding="utf-8")
        occurrences = original.count(find)

        a_diff = _a_diff_that_parses(relative_path, replace, original, editing=True)
        if a_diff is not None:
            raise RepositoryToolError(a_diff)

        wrapped = _where_the_replacement_already_wraps_every_match(original, find, replace)
        if wrapped:
            return _already_there(target, root, relative_path, replace, wrapped)

        if occurrences == 0:
            # Before refusing, try the two things that are wrong with a `find`
            # far more often than the agent's intent is: line-number prefixes
            # copied out of `read_file`, and a different left margin. Each
            # fallback still requires a *unique* match, so the exactness
            # guarantee is unchanged - only the transcription is forgiven.
            attempts: list[tuple[str, str]] = []
            # Composed, not tried one at a time. Each repair used to be applied
            # to the original `find` alone, so a passage carrying BOTH faults
            # defeated both: `\\\\n` collapses to `\\n`, which is still a
            # literal backslash-n and still not the newline the file holds, and
            # neither candidate ever matched.
            #
            # Measured on one run's `test_round_1`, which sent
            # `...index.html`;\\n    await page.evaluate(...)` - double-escaped
            # around a JSON-escaped newline - and was answered with a quoted
            # near-miss it could not act on. Composing costs three extra string
            # searches on a call that has already failed.
            for candidate, explanation in _transcription_repairs(find):
                attempts.append((candidate, explanation))
            attempts.append((
                find,
                "Matched ignoring indentation - the passage you gave was indented "
                "differently from the file. Copy indentation exactly from what you read.",
            ))

            for candidate, explanation in attempts:
                if candidate != find and original.count(candidate) == 1:
                    start = original.index(candidate)
                    span = (start, start + len(candidate))
                else:
                    span = _indentation_insensitive_span(original, candidate)
                if span is None:
                    # Blank lines are the other part of a passage an agent
                    # reconstructs rather than reads. See
                    # `_blank_line_insensitive_span`.
                    span = _blank_line_insensitive_span(original, candidate)
                    if span is not None:
                        explanation = (
                            "Matched ignoring blank lines and indentation - every line "
                            "you gave is in the file, in that order, but the spacing "
                            "between them differs. Copy the passage exactly from what "
                            "you read, blank lines included."
                        )
                if span is None:
                    continue
                start, end = span
                written = _the_replacement_without_its_find_s_gutter(find, replace)
                if written != replace:
                    explanation += " The same line numbers were removed from your `replace`."
                _write_unless_it_changes_nothing(
                    target,
                    original,
                    original[:start] + written + original[end:],
                    relative_path,
                )
                return _edited(target, root, relative_path, written, explanation, find)

            # Before anything else: the model may be re-sending an edit it
            # already made, in which case every other message here is a
            # distraction from the one fact that matters.
            line = _already_applied(original, find, replace)
            if line:
                return _already_there(target, root, relative_path, replace, line)

            if len(find.strip()) < 10:
                raise RepositoryToolError(
                    f"Could not find that text in '{relative_path}'. The text you gave is "
                    f"only {len(find)} characters, which rarely identifies one passage. "
                    "Give the whole line you want changed, copied from a read, and put the "
                    "change in `replace`."
                )

            # A `find` this stage has already replaced is not a near miss to
            # be diffed against the replacement it wrote itself.
            replaced = _what_this_stage_replaced_it_with(relative_path, find)
            if replaced is not None:
                shown = replaced.strip()[:200] + ("..." if len(replaced.strip()) > 200 else "")
                raise RepositoryToolError(
                    f"Could not find that text in '{relative_path}' because you "
                    "already replaced it earlier in this stage. That passage is no "
                    "longer in the file; what you put there reads:\n\n"
                    f"{shown}\n\n"
                    "If this edit is a second change to the same place, send the "
                    "text above as `find`. If you meant the change you have already "
                    "made, it is made - move on."
                )

            # Before the diff: a `find` that was correct when it was copied
            # and is wrong now needs the reason, not a character comparison.
            # `npm install` rewriting package.json is the common case; see
            # `app.tools.seen_content`.
            if _changed_underneath(relative_path, original):
                raise RepositoryToolError(
                    f"Could not find that text in '{relative_path}' because the file "
                    f"changed after you last read it - {_who_changed_it(root, relative_path)}. "
                    "The passage you sent was correct for the version you had. Read "
                    "the file again and copy the passage from what you read."
                )

            # What differs, before what is nearby: a model that is three
            # characters out needs the three characters, not the paragraph.
            differences = _how_it_differs(original, find)
            if differences:
                raise RepositoryToolError(
                    f"Could not find that text in '{relative_path}'. It must match "
                    f"exactly, including whitespace and punctuation.{differences}"
                )

            nearest = _closest_passage(original, find)
            if not nearest:
                detail = " Read the section first and copy the passage from what you read."
            elif any(line.startswith(">") for line in nearest.splitlines()):
                # The marker sits in column zero. Testing for ">" anywhere in
                # the block reads the file's own content - `btn => {...}` is
                # enough - and mislabels a whole-file quote as a near match.
                detail = (
                    f"\n\nThe closest text in the file is (> marks the nearest line):"
                    f"\n{nearest}\n\nCopy the passage from there exactly, including "
                    "its indentation."
                )
            else:
                # The whole file, because it is short enough to quote. Saying
                # "closest text" and "> marks the nearest line" here would both
                # be untrue, and an agent that goes looking for a marker that is
                # not there has been sent on an errand instead of given an
                # answer.
                detail = (
                    f"\n\nThis is the entire file:\n{nearest}\n\nCopy the passage "
                    "you want to change from there exactly, including its indentation."
                )
            raise RepositoryToolError(
                f"Could not find that text in '{relative_path}'. It must match exactly, "
                f"including whitespace and punctuation.{detail}"
            )
        if occurrences > 1:
            raise RepositoryToolError(
                f"That text appears {occurrences} times in '{relative_path}', so it is "
                "ambiguous which one to change. It starts at "
                f"{_where_each_match_starts(original, find)}. Either add whichever "
                "of these surrounding lines differs between them to your `find` "
                "and send it again, or - simpler - call `replace_lines` with the "
                "line numbers of the one you meant. A position is never "
                "ambiguous, and the numbers are in the list above."
                f"{_a_collision_on_one_line(original, find)}"
                f"{_what_sits_around_each_match(original, find)}"
            )

        _write_unless_it_changes_nothing(
            target, original, original.replace(find, replace, 1), relative_path
        )
    return _edited(target, root, relative_path, replace, find=find)


#: Lines of context to quote either side of an edit, so the result answers
#: "did it land, and what does it look like now" without a read.
_EDIT_CONTEXT_LINES = 3


def _where_it_landed(written: str, replace: str) -> str:
    """The edited passage in place, with line numbers, or "".

    A model that has just edited a file reads the whole file back to see what
    it now says. Measured on one run's `specialist_testing_1`: five full
    reads of a 96-line `app.test.mjs`, one after each single-line edit, in a
    stage of twenty-six calls. None of them is a repeat the notices can catch -
    the file genuinely changed each time, because the model had just changed
    it.

    The re-read is asking a reasonable question that the result did not answer:
    `summary` was the first eighty characters of the replacement, with no line
    number and nothing around it. This answers it.
    """
    if not replace.strip():
        return ""
    at = written.find(replace)
    if at < 0:
        return ""
    lines = written.splitlines()
    first = written.count("\n", 0, at)
    last = first + replace.rstrip("\n").count("\n")
    start = max(0, first - _EDIT_CONTEXT_LINES)
    end = min(len(lines), last + _EDIT_CONTEXT_LINES + 1)
    quoted = "\n".join(
        f"{'>' if first <= index <= last else ' '} {index + 1:>4} | {lines[index]}"
        for index in range(start, end)
    )
    return f"Now reads (> marks what you changed):\n{quoted}"


def _what_is_still_wrong_after_a_repair(
    target: Path, relative_path: str, content: str
) -> str:
    """The structural problem remaining, as a note rather than a refusal.

    `_structural_note` raises for the file types whose grammar is certain, and
    that is right at the gate: a write that breaks a healthy Python or JSON
    file is refused. It is wrong *after* a write that has already happened.
    Once an edit to an already-broken file is allowed through, raising here
    would report a failure for a change that is on disk - the tool lying about
    what it did, which is the failure this codebase has spent the most time
    removing.

    So the same problem is reported, in the same words, as a note.
    """
    problem = _what_is_structurally_wrong(target, relative_path, content)
    if not problem:
        return ""
    # `_what_is_structurally_wrong` reports through the refusal path, so its
    # text opens "Refusing to write 'x': ...". Nothing was refused here - the
    # change is on disk - and saying otherwise is the contradiction the model
    # then has to resolve instead of fixing the file.
    return (
        f"The file still does not parse: {problem} It was already broken before "
        "your change and your change was kept, so you are part-way through a "
        "repair. Keep going until the parser is satisfied."
    )


def _line_count(content: str) -> int:
    """Lines as `wc -l` would count them, plus a trailing unterminated line.

    `wc -l` counts newlines, so a file with no final newline reports one fewer
    line than it visibly has. An agent comparing this against its own `wc -l`
    output should see the same number for a well-formed file and a truthful one
    for a file missing its final newline.
    """
    if not content:
        return 0
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def _remember_who_wrote_it(root: Path, relative_path: str) -> None:
    """Record the authoring stage in the project memory. Never raises.

    Called from the two success paths every mutation funnels through, so a
    third path cannot reopen the gap - the mistake `_edited`'s own docstring
    names. See `app.analysis.project_memory`.
    """
    try:
        from app.analysis import project_memory
        from app.observability.transcript import _stage_from_config

        project_memory.record(root, relative_path, _stage_from_config(""))
    except Exception:  # noqa: BLE001 - bookkeeping must never fail a write
        pass


def _edited(
    target: Path,
    root: Path,
    relative_path: str,
    replace: str,
    detail: str | None = None,
    find: str | None = None,
) -> dict[str, str]:
    """The result of a successful edit, with every note that applies.

    One exit for both matching paths. `edit_approved_artifact` succeeds in two
    places - the exact match, and the forgiving match that tolerates line
    numbers, JSON escaping or a different indent - and the notes were attached
    to the first only.

    That cost one run. At 12:52:03 `test_round_0` removed a passage
    through the forgiving path and got no structural note; the edit left a
    brace unclosed, and `node --test` then failed four times with
    "Unexpected end of input" before the next edit - through the exact path -
    finally reported it.

    Two success returns and a check on one of them is the "reached twelve of
    thirteen" mistake this codebase names in its own tests, and building the
    result in one place is what stops a third path from reopening it.
    """
    _remember_who_wrote_it(root, str(target.relative_to(root)))
    summary = replace[:80] + ("..." if len(replace) > 80 else "")
    written = target.read_text(encoding="utf-8")
    result: dict[str, Any] = {
        "path": str(target.relative_to(root)),
        "status": "edited",
        "summary": summary or "(passage removed)",
        # As on a write: a stage editing towards a size limit needs the new
        # length, and a separate `wc -l` for it is a whole round trip. Read back
        # from disk rather than computed from `replace`, because an edit changes
        # part of a file and only the file knows the total.
        "lines": _line_count(written),
    }
    if detail:
        result["detail"] = detail
    # So the next call is not a read of the whole file. See `_where_it_landed`.
    landed = _where_it_landed(written, replace)
    if landed:
        result["context"] = landed
    notes = [
        _what_was_put_right(target),
        _what_is_still_wrong_after_a_repair(target, relative_path, written),
        _discovery_note(relative_path, written, target),
        _import_note(root, target, written),
        # From the path, not from a caller's variable: this is the edit path,
        # and it has no `relative_parts` of its own.
        _nearly_a_workflow_document(_repo_relative_path(root, relative_path).parts),
        _unrunnable_script_note(relative_path),
        # The module-system notes the write path gives, on the whole file as it
        # now stands. They were on the write path only: one run's
        # `defect_fix_1_2` used `replace_lines` to turn a test's `import` lines
        # into `require(...)` under `"type": "module"`, was told nothing, and
        # the next test round reported "require is not defined".
        _the_module_type_this_declares_breaks_files_here(target, written),
        _the_module_type_here_rejects_this_file(target, written),
        _the_page_and_this_module_disagree_on_how_it_loads(root, target, written),
        _budget_note(root, str(target.relative_to(root))).strip(),
    ]
    if find is not None:
        # Both success paths reach here, which is why the record is taken here
        # and not at either of them. See `app.tools.seen_content`.
        try:
            from app.tools.seen_content import record_replacement

            record_replacement(relative_path, find, replace)
        except Exception:  # noqa: BLE001 - bookkeeping must not fail an edit
            logger.debug("Could not record the replacement in %s", relative_path, exc_info=True)

    landed = ""
    try:
        landed = target.read_text(encoding="utf-8")
    except OSError:  # noqa: PERF203 - the file was just written; this is paranoia
        logger.debug("Could not read back %s after editing it", relative_path)
    # Checked before the new state is recorded, or every edit looks like a
    # return to the state it just created.
    notes.append(_an_edit_that_undoes_an_earlier_one(relative_path, landed) if landed else "")

    joined = " ".join(n for n in notes if n)
    if joined:
        result["note"] = joined
    # The stage has now seen the file it just changed, so a following edit is
    # judged against this and not against the read before it.
    if landed:
        try:
            from app.tools.seen_content import record_state, remember

            remember(relative_path, landed)
            record_state(relative_path, landed)
        except Exception:  # noqa: BLE001 - a bookkeeping miss must not fail an edit
            logger.debug(
                "Could not record the edited content of %s", relative_path, exc_info=True
            )
    return result


def _each_match_starts_at(text: str, find: str) -> list[int]:
    """The offset of every match, counted as `str.count` counts them.

    The two helpers below each scanned for themselves, advancing one character
    at a time, while the sentence that quotes them says `original.count(find)`.
    `str.count` does not count overlapping matches, so the two disagreed
    whenever a match could overlap itself: `find: "aa"` against `aaaa` was
    reported as "appears 2 times ... It starts at lines 1, 1 and 1".
    """
    if not find:
        return []
    positions: list[int] = []
    start = 0
    while True:
        at = text.find(find, start)
        if at < 0:
            return positions
        positions.append(at)
        start = at + len(find)


def _matches_by_line(text: str, find: str) -> dict[int, int]:
    """How many matches each 1-based line holds, in the order they appear."""
    counts: dict[int, int] = {}
    for at in _each_match_starts_at(text, find):
        line = text.count("\n", 0, at) + 1
        counts[line] = counts.get(line, 0) + 1
    return counts


def _a_collision_on_one_line(text: str, find: str) -> str:
    """The extra sentence for copies that share a line, or "".

    The advice to "call `replace_lines` with the line numbers of the one you
    meant" is right for copies on separate lines and cannot be followed for
    copies on the same one: a position identifies a line, and a line holding
    three copies of the passage does not say which.
    """
    crowded = sorted(line for line, count in _matches_by_line(text, find).items() if count > 1)
    if not crowded:
        return ""
    where = ", ".join(str(line) for line in crowded)
    return (
        f" Note that more than one copy is on the same line ({where}), and a line "
        "number cannot pick between those - for them, either extend your `find` "
        "along the line, or send the whole corrected line with `replace_lines`."
    )


def _what_sits_around_each_match(text: str, find: str) -> str:
    """The line before and after each copy, so the agent can tell them apart.

    "Include a line from above or below one of them" is advice the agent cannot
    act on: it does not have the file in front of it, and the two copies are
    near-identical or it would not have collided with both. So show the lines
    that differ.

    Measured on one run, where the model wrote `app.test.mjs` with the
    same three-line block at lines 52 and 73, tried to edit it, and sent the
    byte-identical failing call again rather than guess. Six of that run's
    thirteen edit failures were this.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    # One block per line, not per match. Several copies on one line have the
    # same line above and below them by definition, so quoting the surroundings
    # once per copy printed the same three lines three times - in the helper
    # whose whole purpose is to show what differs.
    for line, copies in list(_matches_by_line(text, find).items())[
        :_MAX_AMBIGUOUS_MATCHES_SHOWN
    ]:
        first = line - 1
        if copies > 1:
            blocks.append(
                f"  {copies} copies are on line {line} itself:\n"
                f"  {line:>5} | {_clip(lines[first])}\n"
                f"  ({copies} times on this line - the lines around it are the same "
                f"for every one of them, so extend your `find` along the line.)"
            )
            continue
        last = first + find.rstrip("\n").count("\n")
        before = f"{first:>5} | {_clip(lines[first - 1])}" if first > 0 else "      | (start of file)"
        after = (
            f"{last + 2:>5} | {_clip(lines[last + 1])}"
            if last + 1 < len(lines)
            else "      | (end of file)"
        )
        blocks.append(
            f"  the copy at line {line}:\n"
            f"  {before}\n"
            f"  {'':>5} | ... your passage ...\n"
            f"  {after}"
        )
    if not blocks:
        return ""
    return "\n\n" + "\n\n".join(blocks)


def _where_each_match_starts(text: str, find: str) -> str:
    """"line 7 and line 10", or "lines 7, 10 and 14".

    The old message said only "include more surrounding text to make the
    passage unique", which is advice rather than information: the agent cannot
    see where the copies are, so it guesses at more context and often collides
    with the other copy again.

    Measured on one run: 7 of 24 `edit_artifact` failures were this, on a
    test file whose blocks the model had duplicated - exactly the case where
    knowing which lines differ is the whole problem.
    """
    counts = _matches_by_line(text, find)
    if not counts:
        return "several places"
    # A line that holds several copies is named once, with how many. Listing it
    # per copy produced "lines 7, 12, 12, 12, 13, ..." on one run, in a
    # message that then points at those numbers as the way to pick one.
    parts = [
        f"{line} ({count} times)" if count > 1 else str(line)
        for line, count in counts.items()
    ]
    if len(parts) == 1:
        return f"line {parts[0]}"
    listed = ", ".join(parts[:-1])
    return f"lines {listed} and {parts[-1]}"


def _content_a_model_escaped_twice(relative_path: str, content: str) -> tuple[str, str] | None:
    """Content that only fails because its escapes were written twice, repaired.

    Measured live on one run at 03:37. `test_round_0` sent

        {"relative_path": "todo-app/package.json",
         "content": "{\\n  \"name\": \"todo-app\", ... }"}

    where every newline is the two characters backslash-n rather than a
    newline. The content is therefore `{\\n  "name": ...`, `json.loads` stops
    at column 2, and the write is refused - correctly, because a broken
    `package.json` breaks every module in its directory. The model sent the
    identical bytes three times and the stage made no progress.

    The repairs that fix this have existed since two runs.
    They were reachable only from `edit_artifact`'s `find`. `write_artifact`
    had none, so the same transcription fault was forgiven on one path and
    fatal on the other - twelve of thirteen again, with the thirteenth being
    the path that carries whole files.

    Deliberately conservative, on the same rule the edit repairs use: the
    content must be structurally invalid as sent AND structurally valid after
    the repair. A file that legitimately contains a literal backslash-n is
    already valid, so it is never touched, and a repair that does not fix the
    problem is discarded rather than written.

    Returns `(repaired, explanation)` or None.
    """
    from app.analysis.syntax_balance import structural_problem

    # A page parses whatever it holds, so for markup the evidence is the
    # escape itself, against a tag. See `_markup_with_its_escapes_resolved`.
    if escapes_between_tags(relative_path, content):
        for candidate, _ in _transcription_repairs(content):
            if candidate.strip() and not escapes_between_tags(relative_path, candidate):
                return candidate, (
                    f"Your content for '{relative_path}' was escaped twice over - it carried "
                    "the two characters backslash-n where the page needs a real newline, and "
                    "a browser shows those as text. It has been written with the escapes "
                    "decoded, which is what you meant. The tool call is already JSON: put the "
                    "literal text in `content`, not an escaped copy of it."
                )
    if structural_problem(relative_path, content) is None:
        return None
    for candidate, _ in _transcription_repairs(content):
        if not candidate.strip():
            continue
        if structural_problem(relative_path, candidate) is None:
            # The explanations on `_transcription_repairs` are written for
            # `edit_artifact`'s `find`. Saying "your `find`" to a write would
            # send the model looking for an argument it did not pass.
            return candidate, (
                f"Your content for '{relative_path}' was escaped twice over - it "
                "carried the two characters backslash-n where the file needs a "
                "real newline, so it did not parse. It has been written with the "
                "escapes decoded, which is what you meant. The tool call is "
                "already JSON: put the literal text in `content`, not an escaped "
                "copy of it."
            )
    return None


def _structural_note(
    relative_path: str, content: str, *, editing: bool = False, refuse: bool = True
) -> str:
    """Warn about a file that was just written broken, or refuse it.

    Python is parsed with `ast` and JSON with `json.loads`, which are the real
    grammars, so a failure is certain and worth refusing over. Brace-counting
    for the C family is a structure check rather than a parse - it cannot see a
    missing semicolon - so it warns and lets the write stand.

    Either way the agent hears it while it is still looking at the edit it just
    made. One run heard it two stages later, as "Syntax error in app.mjs
    at line 206", and spent three remediation attempts editing line 206 - which
    was where the parser gave up, not where the mistake was.
    """
    try:
        from app.analysis.syntax_balance import structural_problem

        problem = structural_problem(relative_path, content)
    except Exception:  # noqa: BLE001 - a check must never fail a write
        return ""
    if not problem:
        return ""
    if refuse and _refuses_a_broken_file(relative_path):
        raise RepositoryToolError(_refusal_for(relative_path, problem, editing=editing))
    return problem


#: Whole-file writes a grammar has refused, by path and content, with how often.
_REFUSED_ON_A_GRAMMAR: dict[tuple[str, str], int] = {}

#: Identical sends a grammar's refusal withstands before the write goes through.
GRAMMAR_REFUSALS_BEFORE_IT_IS_WRITTEN = 2


def _sent_again_past_a_grammar(relative_path: str, content: str) -> bool:
    """Whether this exact file has now been refused on a grammar's word often enough.

    Python, JSON, TOML, YAML and XML are refused by the parser that will load
    them, and that is final. A language read through a bundled grammar is
    refused on a measurement - no correct file was reported in a few hundred -
    and a measurement is not a proof. If the grammar is ever wrong about a
    file, a stage could send it forever and never be allowed to write it, so
    the same content sent a third time is written, with the grammar's reading
    as a note. A stage that changes anything between sends starts the count
    again, which is the ordinary case: it read the refusal and acted on it.
    """
    try:
        from app.analysis.grammar_parse import is_measured_not_proven

        if not is_measured_not_proven(relative_path):
            return False
    except Exception:  # noqa: BLE001
        return False
    import hashlib

    key = (relative_path, hashlib.sha1(content.encode("utf-8", "replace")).hexdigest())
    if len(_REFUSED_ON_A_GRAMMAR) > 2000:
        _REFUSED_ON_A_GRAMMAR.clear()
    seen = _REFUSED_ON_A_GRAMMAR.get(key, 0)
    _REFUSED_ON_A_GRAMMAR[key] = seen + 1
    return seen >= GRAMMAR_REFUSALS_BEFORE_IT_IS_WRITTEN


def _refuses_a_broken_file(relative_path: str) -> bool:
    """Whether a failure for this file is certain enough to refuse over.

    Python and JSON have real grammars, so `ast.parse` and `json.loads` are
    proof. Brace counting for the C family is a structure check and warns
    instead - but `node --check` is a parse, so JavaScript is refused on that
    and warned on the rest. See `_javascript_parse_error`.
    """
    # And stylesheets, for their braces alone: an unpaired one is never meant,
    # and a browser's recovery from it drops rules without saying so.
    if relative_path.lower().endswith((".py", ".json", ".css", ".scss", ".less")):
        return True
    # And every language or format that has a parser of its own here.
    try:
        from app.analysis.grammar_parse import is_certain

        return is_certain(relative_path)
    except Exception:  # noqa: BLE001 - a check that cannot run refuses nothing
        return False


def _javascript_parse_error(target: Path, relative_path: str, content: str) -> str:
    """Node's own syntax error for this content, or "". Never raises.

    Separate from `_structural_note` because it needs a real path: `.js` is
    ESM or CommonJS depending on the nearest `package.json`, so the check has
    to happen where the file will live.
    """
    from app.analysis.javascript_parse import parse_error

    try:
        return parse_error(target, content) or ""
    except Exception:  # noqa: BLE001 - a check that cannot run says nothing
        return ""


def _refuse_if_node_cannot_parse(
    target: Path, relative_path: str, content: str, *, editing: bool = False
) -> None:
    """Refuse a JavaScript file the parser that loads it cannot read.

    One run wrote `app.js` with a stray `try` and spent the whole of
    `test_round_0` discovering `SyntaxError: Unexpected token 'try'` at line
    83, then a triage and a defect-fix stage routing it back - for something
    the parser names in seventeen milliseconds at the moment of the write.
    """
    problem = _javascript_parse_error(target, relative_path, content)
    if problem:
        raise RepositoryToolError(_refusal_for(relative_path, problem, editing=editing))


def _what_is_structurally_wrong(
    target: Path, relative_path: str, content: str
) -> str | None:
    """The structural problem in this content, or None. Never raises.

    The same two checks the write guard refuses on, asked as a question
    instead of enforced as a rule, so a caller can tell "this edit broke the
    file" from "this file was already broken".
    """
    try:
        from app.analysis.syntax_balance import structural_problem

        # The raw problem, not the refusal that wraps it. The wrapper ends
        # "Nothing was written. Send the file again with that fixed.", which
        # is true at a gate and false in a note about a change that landed.
        problem = structural_problem(relative_path, content)
        if problem:
            return problem
        return _javascript_parse_error(target, relative_path, content) or None
    except Exception:  # noqa: BLE001 - a probe must never fail its caller
        return None


def _cut_off_at_a_quote(relative_path: str, content: str, *, editing: bool = False) -> str | None:
    """The refusal for text that stops on a backslash, or None.

    What the call's JSON does to a double quote written as `\\\\"`: the pair is
    a backslash and then the quote that ends the string, so nothing after it
    reaches the tool. Measured on one run: two stages sent `app.js` fifteen
    times, every copy ending `return String(input).replace(/[&<>\\` on line
    18 - the model's `/[&<>"']/g` cut at its quote. Each was refused as
    "Invalid regular expression: missing /", which is true of the seventeen
    lines that arrived and says nothing about the hundred that did not, so the
    same call came back unchanged and the page was never written.

    Only text that ends on the backslash itself: no complete file or edit does,
    while a line continuation is followed by its newline.
    """
    if not content or not content.endswith("\\"):
        return None
    lines = content.split("\n")
    verb = "change" if editing else "write"
    return (
        f"Refusing to {verb} '{relative_path}': what arrived ends with a backslash, "
        f"partway through line {len(lines)}:\n    {lines[-1].strip()}\n"
        "Nothing after that reached the tool. A double quote in the code sent as "
        "`\\\\\"` does this: in the call's JSON that is a backslash and then the quote "
        "that ends the string, so everything you wrote after it was cut off. "
        "Nothing was written. Send it again with that quote as `\\\"`, or write that "
        "part of the code with no backslash before a double quote - inside a "
        "regular expression's [...] or a template string the quote needs none."
    )


def _refusal_for(relative_path: str, problem: str, *, editing: bool = False) -> str:
    """The refusal text for `problem`, in terms of the call that was made.

    Two things went wrong here, both measured on one run.

    The instruction was said twice. Some checks end with the remedy already
    ("Send the file again as complete, valid JSON.") because they are also used
    as notes, where nothing else supplies one, and appending the generic
    sentence produced "... Send the file again as complete, valid JSON. Nothing
    was written. Send the file again with that fixed."

    And an `edit_artifact` was answered in `write_artifact`'s words. Six edits
    to package.json were refused with "Refusing to write ... Send the file
    again as complete, valid JSON" - a verb naming a tool the model had not
    called, and an instruction it could not follow through the one it had. It
    eventually switched to `write_artifact`, which is what the message had been
    describing all along, after six calls.
    """
    verb = "change" if editing else "write"
    if editing:
        # The check's own remedy is written for `write_artifact` ("Send the
        # file again as complete, valid JSON"), which is not available through
        # this tool. Drop it and give the one that is.
        problem = re.sub(r"\s*Send the file again[^.]*\.", "", problem).strip()
        # `find`/`replace` is what the model can act on; the whole file is not.
        tail = "Nothing was changed. Fix `replace` and send the edit again."
    elif problem.rstrip().endswith(".") and "Send the file again" in problem:
        tail = "Nothing was written."
    else:
        tail = "Nothing was written. Send the file again with that fixed."
    return f"Refusing to {verb} '{relative_path}': {problem} {tail}"


def _refuse_if_broken(relative_path: str, content: str, *, editing: bool = False) -> None:
    """Raise before anything is written, for the file types that are certain.

    Run *before* the write, not after it. The check used to sit beside the
    result, so a refused file had already been saved and the refusal said
    "Nothing was written" while the broken file sat on disk - a tool lying
    about what it did, which is the failure this codebase has spent the most
    time removing from other tools.
    """
    if _refuses_a_broken_file(relative_path):
        _structural_note(relative_path, content, editing=editing)


#: Scripts the sandbox has no interpreter for. `make`, `npm`, `node`, `python`
#: and the rest of the allowlist are all available; a shell is not.
_UNRUNNABLE_SCRIPTS = (".sh", ".bash", ".zsh", ".command")


def _unrunnable_script_note(relative_path: str) -> str:
    """Warn about a script this environment can never execute, or "".

    Measured on one run, where `simple-to-do-list-app/build.sh` was the
    most-written file of the entire run - 22 writes and edits across several
    stages - for a file the sandbox cannot run. `specialist_backend_0` then
    sent `sh ./build.sh` five times, and `specialist_backend_8` wrote
    `docs/blocker.md` five times because being blocked was all it had left to
    report. That ended a run which had already completed a full sprint, a test
    round, a security review and a milestone review.

    The refusal exists, but only fires once the command is attempted - after
    the spec is written, the task delegated, and the script authored. This
    fires at the write, which is the first moment anyone could have known.

    A note rather than a refusal: a project may legitimately ship a shell
    script for a human to run elsewhere. What it may not do is depend on
    running one here, and saying so is enough.
    """
    if not relative_path.lower().endswith(_UNRUNNABLE_SCRIPTS):
        return ""
    return (
        "This environment has no shell, so this script cannot be run here - "
        "`sh` and `bash` are not available and never will be. If anything in "
        "this project needs to execute these steps, put them in a package.json "
        "script and run `npm run <name>`, or run a program directly (`node`, "
        "`python3`). `make` is not installed here, so a Makefile is not an "
        "option either."
    )


#: Documents the workflow itself writes, at `docs/<name>` in the workspace
#: root and nowhere else. Each is rendered from a stage's structured response,
#: so a copy of one is a copy of a record - stale the moment the next stage
#: runs, and read by nothing.
from app.analysis import document_manifest as _document_manifest

#: Derived from `document_manifest`, not restated. Two copies of this list is
#: how the set drifts between the tool that enforces it, the prompt that
#: describes it and the audit that reads it.
WORKFLOW_DOCUMENTS = frozenset(
    f"{stem}.md" for stem in _document_manifest.RENDERED_STEMS
)


#: The stem an agent reaches for when it mistakes "return your structured
#: response" for "write it down". Any extension: `.md` and `.json` have both
#: been tried.
_THE_RESPONSE_ITSELF = "structured_response"


#: The fields of `SpecialistOutput`. A JSON object carrying several of these
#: IS the structured response, whatever the file it is being written into is
#: called.
_THE_RESPONSE_SCHEMA = frozenset(
    {
        "changed_files",
        "decisions",
        "tests",
        "verification",
        "documentation",
        "risks",
        "blockers",
        "defects",
        "summary",
        "role",
        "output",
    }
)

#: How many of them make it certain rather than a coincidence. Three, because
#: `summary` and `tests` alone could plausibly be some other document's keys,
#: and every real instance in the corpus carries five or more.
_FIELDS_THAT_MAKE_IT_THE_RESPONSE = 3


def _the_response_written_under_another_name(
    relative_parts: tuple[str, ...], content: str
) -> str | None:
    """Refuse the structured response written as a file, by its content.

    `_the_response_it_should_be_returning` refuses it by name, and the name is
    whatever the agent invents. Five runs died on this and it caught three:

        one run  docs/structured_response.md    32 writes
        one run  todo-list/structured_response.json   8
        one run  docs/structured_response.json        4
        one run  final_response.json                  6   - fell through
        one run  docs/summary.json                    5   - fell through

    Fifty-five writes across the five, every one of them carrying the same
    thing: `{"changed_files": [...], "decisions": [...], "tests": [...]}`.
    The content is identical; only the filename varies, so the content is what
    this reads. A stage writing its own answer to a file leaves the workflow
    with nothing, is asked again, and writes it again until the loop guard
    stops the run - eighteen of the fifty-five recorded failures are a stage
    repeating one write, and this is the largest single cause among them.
    """
    try:
        import json as _json

        document = _json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(document, dict):
        return None
    present = _THE_RESPONSE_SCHEMA & {str(key).lower() for key in document}
    if len(present) < _FIELDS_THAT_MAKE_IT_THE_RESPONSE:
        return None
    # The invariant sentence leads, and the field list - which varies with
    # whatever the agent included - comes after it. `_the_same_refusal` keys on
    # the first 60 characters after the colon, so a varying opening would reset
    # the repeat count on every attempt, which is the exact weakness that
    # helper exists to close. Leading this way also makes it share a key with
    # `_the_response_it_should_be_returning`, so the two count as one event.
    return (
        f"Refusing to write '{'/'.join(relative_parts)}': your structured "
        "response is returned, not written. The workflow reads it from the "
        "response itself, so writing it to a file under any name leaves the "
        "workflow with nothing and you will be asked for it again. This "
        f"content is that response - it carries {', '.join(sorted(present)[:4])}. "
        "Stop calling tools and return the structured response now, in the "
        "required schema."
    )


def _the_response_it_should_be_returning(relative_parts: tuple[str, ...]) -> str | None:
    """Refuse a write of the agent's own structured response, or None.

    This is not a document the workflow renders; it is a stage trying to
    deliver its answer by writing a file instead of returning it. The write
    succeeds or is auto-approved, the workflow still has no structured
    response, the stage is asked again, and it writes the same file again.

    One run died of exactly this: `defect_fix_1_0` requested
    `docs/structured_response.md` five times in a row, carrying
    `{"role":"Testing and Quality Engineering Specialist","output":{...}}` as
    its content, and the loop guard stopped the run. Twenty model calls in that
    run went into writing that file; one run spent eight more on
    `structured_response.json`.

    Nothing refused it before, because nothing renders a file of that name -
    it fell through every guard precisely by not being one of the workflow's
    own documents.
    """
    if not relative_parts:
        return None
    stem = relative_parts[-1].lower().split(".", 1)[0]
    if stem != _THE_RESPONSE_ITSELF:
        return None
    return (
        f"Refusing to write '{'/'.join(relative_parts)}': your structured "
        "response is returned, not written. The workflow reads it from the "
        "response itself - writing it to a file leaves the workflow with "
        "nothing, and you will be asked for it again. Stop calling tools and "
        "return the structured response now, in the required schema."
    )


def _a_workflow_document(relative_parts: tuple[str, ...]) -> str | None:
    """Refuse an agent's write to a document the workflow owns, or None.

    Two shapes, one rule. A copy somewhere else drifts; a change at the
    canonical path is overwritten the next time the stage that produces it
    runs, so neither is worth a model call.

    One run's `specialist_documentation_2` spent six consecutive calls
    and ninety seconds failing to edit `docs/tools_and_models.md` - a document
    rendered from the `tools_models` stage's structured response. Succeeding
    would have been no better than failing.

    The workflow's own `_record_document` passes `by_the_workflow=True` and is
    unaffected; that is the only writer of these paths that should exist.

    The message names the channel that does work, because the first version did
    not and the model found the worst way round it: refused the specification,
    `specialist_ui_ux_0` wrote `docs/specification_update.md` instead - in
    one run and again in one run, written once each and never read by
    anything. A specialist's `decisions`, `risks` and `blockers` are read by the
    workflow; a sibling document is read by nobody.

    Measured on one run: a specialist wrote
    `simple-to-do-list-app/docs/architecture_review.md`, a copy of the review
    the workflow had already rendered to `docs/architecture_review.md` from the
    reviewer's structured decision. Two files with the same name and different
    contents, in a workspace where every later stage is told to read the
    documents - and only one of them is ever updated again.

    The one canonical location is not a matter of taste here: `_record_document`
    writes to `docs/<name>` unconditionally, so a copy anywhere else can only
    ever drift.
    """
    if not relative_parts:
        return None
    name = relative_parts[-1].lower()
    if name not in WORKFLOW_DOCUMENTS:
        return None
    where = "/".join(relative_parts)
    if relative_parts[:-1] == ("docs",):
        return (
            f"Refusing to change '{where}': the workflow writes this file from "
            "the structured response of the stage that produces it, and rewrites "
            "it whole every time that stage runs. Any change you make here is "
            "discarded then, so this call cannot achieve anything. Read it if you "
            "need what it says. If it is wrong or out of date, say so in your "
            "structured response - `blockers` for something that stops the work, "
            "`risks` for something that does not, `decisions` for a change you "
            "made and want recorded. Those reach the workflow and the next "
            "stage; a document written beside this one reaches nobody. "
            "CRITICAL: STOP TRYING TO EDIT THIS FILE. RETURN YOUR FINAL STRUCTURED RESPONSE NOW."
        )
    return (
        f"Refusing to write '{where}': '{name}' is written by "
        f"the workflow itself, at 'docs/{name}', from the structured response of "
        "the stage that produced it. A second copy is read by nothing and is "
        f"stale as soon as that stage runs again. Read 'docs/{name}' instead of "
        "copying it, and put your own work in a file of its own."
    )


#: How alike two document names must be before a reader would confuse them.
#: Measured against the names agents have actually written beside the
#: workflow's own: `tech_specification` scores 0.88 against
#: `technical_specification`, `tools_and_model` 0.97 against
#: `tools_and_models`, while `architecture_notes` (0.76), `test_plan` (0.70)
#: and `testing_results` (0.45) stay below, which is where they belong.
_CONFUSABLE_WITH_A_WORKFLOW_DOCUMENT = 0.8


def _nearly_a_workflow_document(relative_parts: tuple[str, ...]) -> str:
    """Warn about a document named almost like one the workflow writes, or "".

    `_a_workflow_document` refuses the exact names and `_supersedes_existing`
    refuses an explicit `_v2`. Between them sits the near-miss spelling, which
    one run produced: `docs/tech_specification.md`, 470 bytes, beside the
    workflow's own `docs/technical_specification.md`, 5,847 bytes.

    The harm is the one the architect's `technical_specification_v2.md` caused:
    a reviewer with two specifications in front of it read the differences
    between them as contradictions in the design, reported a blocking finding
    that existed only because the second file did, and the run stopped
    unresolved.

    A note, because this cannot tell a careless near-duplicate from a
    deliberate companion document - `security_review_notes.md` is a reasonable
    thing to write and scores 0.83.
    """
    import difflib

    if len(relative_parts) != 2 or relative_parts[0] != "docs":
        return ""
    name = relative_parts[-1].lower()
    if not name.endswith(".md") or name in WORKFLOW_DOCUMENTS:
        return ""
    stem = name[:-3]
    ratio, closest = max(
        (difflib.SequenceMatcher(None, stem, other[:-3]).ratio(), other)
        for other in WORKFLOW_DOCUMENTS
    )
    if ratio < _CONFUSABLE_WITH_A_WORKFLOW_DOCUMENT:
        return ""
    return (
        f"This name is very close to 'docs/{closest}', which the workflow writes "
        "from a stage's structured response. A reviewer reading both will treat "
        "the differences between them as contradictions - that has ended a run "
        f"before now. If you meant to change that document, you cannot: read it "
        "instead. If this is genuinely a different document, give it a name a "
        "reader can tell apart at a glance."
    )


def _import_note(root: Path, target: Path, content: str) -> str:
    """Warn about a relative import that will fail when the file loads, or "".

    A note, never a refusal: a test written before the module it imports is a
    specialist doing the right thing in the right order, and this cannot tell
    that from a wrong path. See `app.analysis.local_imports`.
    """
    from app.analysis.local_imports import import_problems, who_would_break

    try:
        project = target.parent
        pinned = pinned_project_directory(root)
        if pinned:
            project = root / pinned
        # What an IDE would underline, from the TypeScript language service,
        # where it can read the file: exact, and it covers the imports this
        # module's regular expressions approximate in both directions, and the
        # names nothing defines that they cannot see at all. See
        # `app.analysis.language_service`.
        from app.analysis.language_service import underlined_any

        service = underlined_any(root, target, content, project)
        if service is not None:
            return service.note()
        problems = import_problems(target, content, project)
        # And the other direction: what breaks in the files that import this
        # one. Removing an export is otherwise silent until a test round.
        breaks = who_would_break(target, content, project)
    except Exception:  # noqa: BLE001 - never fail a write over a hint
        return ""
    note = ""
    if problems:
        note = "This file's imports: " + " ".join(problems)
    if breaks:
        note = (note + " " if note else "") + "What imports this file: " + " ".join(breaks)
    return note


#: A JavaScript file named inside a command string.
_NAMES_A_SCRIPT_FILE = re.compile(r"""[\w./-]+\.[cm]?js\b""")


def _the_runner_itself(token: str) -> bool:
    """Whether a script path in a command is an installed tool, not a suite.

    `node ./node_modules/jest/bin/jest.js` names a file, and that file is the
    test runner, which then searches the project the way `jest` alone does.
    One run's `specialist_testing_1` was told its new `app.test.js` "will not
    be reached" by exactly that script, and Jest ran it on the next call.
    """
    return any(part in IGNORED_DIRECTORIES for part in token.replace("\\", "/").split("/"))


def _refuse_a_script_path_that_repeats_its_own_directory(
    target: Path, content: str
) -> None:
    """Refuse a manifest script whose paths are relative to the wrong place.

    npm runs a script from the directory holding the `package.json`, so a path
    in it is already relative to that directory. Writing the directory's own
    name into the path doubles it, and the file is never found.

    Three of the stored workspaces end this way and every one of their suites
    reports nothing at all:

        t54  "test": "node --test todo-app/app.test.mjs"
             run from todo-app/, looks for todo-app/todo-app/app.test.mjs
        t63  "test": "node --test simple-to-do-list-app/app.test.mjs"
        t50  "test": "node --test simple-to-do-list-app/*.test.mjs"

    `Could not find '<path>'`, exit 1, and a stage that reads the failure as
    the product being broken rather than the command being wrong.

    `_manifest_scripts_that_cannot_resolve` reports this at a milestone
    review. This refuses it at the write, where the fix is deleting one path
    segment.
    """
    try:
        import json as _json

        scripts = (_json.loads(content) or {}).get("scripts") or {}
        if not isinstance(scripts, dict):
            return
        here = target.parent.name
        if not here:
            return
        for name, command in scripts.items():
            if not isinstance(command, str):
                continue
            # The directory's own name used as a path prefix, anywhere in the
            # command. Matched as a whole segment so a project called `app`
            # does not collide with `app.js`.
            if not re.search(rf"(?<![\w./-]){re.escape(here)}/", command):
                continue
            raise RepositoryToolError(
                f"Refusing to write '{target.name}': its `{name}` script runs "
                f"`{command}`, and npm runs that from '{here}/' - the "
                "directory this manifest is in. Paths in it are already "
                f"relative to '{here}/', so `{here}/...` resolves to "
                f"'{here}/{here}/...', which does not exist. Every path in "
                f"that command reports `Could not find` and nothing runs. Drop "
                f"the leading '{here}/' from the paths."
            )
    except RepositoryToolError:
        raise
    except Exception:  # noqa: BLE001 - never fail a write over a check that cannot run
        return


def _refuse_a_test_script_that_strands_suites(
    target: Path, content: str
) -> None:
    """Refuse a manifest whose `test` script leaves existing suites unrun.

    `_the_test_command_will_not_run_this` says so at the write of each test
    file, and that is the right first response. It is not enough. One
    run delivered that note 27 times across ten stages and still ended
    with

        "test": "node --test test_filter.mjs"

    beside `app.test.mjs`, `filter.test.mjs` and `test_filter.mjs` - two of
    three suites unrun, their assertions never executed, and every gate
    downstream reading a pass.

    Twelve of the fifty-five stored workspaces ship tests `npm test` never
    runs. A note the model has ignored twenty-seven times is not a note that
    needs rewording; the same reasoning as the no-op write and the edit that
    goes backwards.

    Only when suites already on disk would be stranded, so a manifest written
    before the tests exist is untouched, and a command that discovers rather
    than names is never refused.
    """
    try:
        import json as _json
        import shlex

        from app.analysis.file_kinds import is_test
        from app.analysis.integration_checks import _A_SCRATCH_SCRIPT

        command = str(
            (_json.loads(content).get("scripts") or {}).get("test", "")
        )
        if not command:
            return
        # A glob is the shell's discovery, not a list of names: `*.test.mjs`
        # expands to whatever is there, and reading it literally reports every
        # file it would have matched as stranded (one run).
        if any(character in command for character in "*?["):
            return
        # Only positional arguments name suites. `--config=jest.config.js`
        # names a configuration file, and jest with no pattern searches the
        # project (one run).
        named = {
            token
            for token in shlex.split(command)
            if not token.startswith("-") and _NAMES_A_SCRIPT_FILE.fullmatch(token)
        }
        # An installed runner named by path discovers like the bare command.
        if not named or any(_the_runner_itself(token) for token in named):
            return
        # A runner that imports the others strands nothing.
        already_run = set()
        for name in named:
            runner = target.parent / name
            if runner.is_file():
                already_run.update(
                    _NAMES_A_SCRIPT_FILE.findall(runner.read_text(errors="replace"))
                )
        stranded = sorted(
            path.name
            for path in target.parent.iterdir()
            if path.is_file()
            and is_test(path.name)
            and not _A_SCRATCH_SCRIPT.search(path.name)
            and path.name not in command
            and not any(reached.endswith(path.name) for reached in already_run)
        )
    except Exception:  # noqa: BLE001 - never fail a write over a check that cannot run
        return
    if not stranded:
        return
    raise RepositoryToolError(
        f"Refusing to write '{target.name}': its `test` script runs "
        f"`{command}`, which names {', '.join(sorted(named))} and leaves "
        f"{', '.join(stranded)} unrun. Those suites' assertions never execute "
        "and every stage after this reads the pass as though they did. Use "
        "`node --test` with no file arguments, which searches the project, or "
        "name every suite."
    )


def _the_test_command_will_not_run_this(target: Path | None) -> str:
    """Warn that the project's `test` script names files and not this one, or "".

    `undiscoverable_test` asks whether Node's own patterns would collect the
    file. This asks the other question, which a correctly-named file still
    fails: whether the command the project actually runs will reach it.

    A `test` script that names its files is the majority here - 17 of the 32
    manifests across the stored workspaces - and every one of them excludes
    whatever is written next. Twelve of fifty-five workspaces currently carry
    test files `npm test` never runs, their assertions never executed while
    every gate reads a passing suite.

    One run is what that costs. Its script ran three named files while the
    project held six, `npm test` passed on the curated subset, the real
    failures survived every green run, and the sprint exhausted all three
    remediation attempts. Said at the write, the fix is one edit to the
    manifest.
    """
    if target is None:
        return ""
    # Only a test file has assertions to strand. Measured across all twelve
    # stored transcripts this fired 215 times on files that are not tests and
    # 41 times on files that are: `app.js` was told 83 times that "this one's
    # assertions never execute" and to "Add it to the script", which would put
    # the application file into `node --test`. Four in five of this note's
    # firings were false, in every run.
    from app.analysis.file_kinds import is_test

    if not is_test(target.name):
        return ""
    try:
        import json as _json

        for folder in (target.parent, *target.parents):
            manifest = folder / "package.json"
            if not manifest.is_file():
                continue
            command = str(
                (_json.loads(manifest.read_text(encoding="utf-8")).get("scripts") or {})
                .get("test", "")
            )
            if not command:
                return ""
            named = _NAMES_A_SCRIPT_FILE.findall(command)
            if not named or target.name in command:
                return ""
            # Only a command that names nothing but suites is known not to
            # reach this one. An installed runner named by path searches the
            # project, and a script of the project's own may import anything.
            if not all(is_test(name) and not _the_runner_itself(name) for name in named):
                return ""
            return (
                f"`npm test` here runs `{command}`, which names "
                + ", ".join(sorted(set(named))[:3])
                + f" and will not reach '{target.name}'. Nothing will report "
                "that: the suite passes on the files it does run and this one's "
                "assertions never execute. Add it to the script, or replace the "
                "named files with `node --test`, which searches the project."
            )
        return ""
    except Exception:  # noqa: BLE001 - never fail a write over a hint
        return ""


def _a_dom_built_by_hand_and_remember(relative_path: str, content: str, dom_given: str = "") -> str:
    """The hand-built-DOM note, counted so the third one can be a refusal.

    Counted here rather than at the refusal, because the refusal has to know
    how many times the model was *told*, and this is the only place that
    decides to tell it.
    """
    from app.analysis.test_discovery import a_dom_built_by_hand

    note = a_dom_built_by_hand(relative_path, content, dom_given)
    if note:
        try:
            from app.tools.seen_content import record_mock_dom_warning

            record_mock_dom_warning(relative_path)
        except Exception:  # noqa: BLE001 - never fail a write over bookkeeping
            logger.debug("Could not record the DOM warning for %s", relative_path)
    return note or ""


def _discovery_note(relative_path: str, content: str, target: Path | None = None) -> str:
    """Warn about a test file the project's runner will not collect, or "".

    A note rather than a refusal: the name is legal and the content is fine.
    What is wrong is invisible - an uncollected test does not error, it is
    simply absent, and every later stage reads a green run that never
    executed it. See `app.analysis.test_discovery`.
    """
    from app.analysis.test_discovery import (
        a_call_the_signature_does_not_accept,
        a_name_this_test_defines_instead_of_importing,
        a_suite_calling_a_global_node_does_not_define,
        a_suite_that_asserts_only_constants,
        a_suite_that_only_checks_things_exist,
        a_test_that_asserts_nothing,
        a_test_that_needs_a_dom,
        assertions_called_on_the_test_module,
        tests_nothing_of_the_project,
        tests_the_runner_will_never_call,
        undiscoverable_test,
    )

    given = _the_dom_unit_tests_get(target)
    try:
        notes = [
            undiscoverable_test(relative_path, content),
            tests_nothing_of_the_project(relative_path, content),
            assertions_called_on_the_test_module(relative_path, content),
            a_test_that_asserts_nothing(relative_path, content),
            tests_the_runner_will_never_call(relative_path, content),
            a_suite_that_only_checks_things_exist(relative_path, content),
            a_suite_that_asserts_only_constants(relative_path, content),
            _a_dom_built_by_hand_and_remember(relative_path, content, given),
            a_test_that_needs_a_dom(relative_path, content, target.parent if target else None, given),
            a_call_the_signature_does_not_accept(
                relative_path, content, target.parent if target else None
            ),
            a_suite_calling_a_global_node_does_not_define(
                relative_path, content, target.parent if target else None
            ),
            a_name_this_test_defines_instead_of_importing(
                relative_path, content, target.parent if target else None
            ),
            _the_test_command_will_not_run_this(target),
        ]
        return " ".join(note for note in notes if note)
    except Exception:  # noqa: BLE001 - never fail a write over a hint
        return ""


#: CommonJS at the start of a line: `require(...)`, `module.exports`,
#: `exports.x =`. Anchored per line so the words inside a string or a comment
#: about CommonJS do not match.
_COMMONJS_SYNTAX = re.compile(
    r"^\s*(?:(?:const|let|var)\s+[\w{},\s]+=\s*)?require\s*\("
    r"|^\s*module\.exports\s*="
    r"|^\s*exports\.\w+\s*=",
    re.M,
)


def _the_module_type_here_rejects_this_file(target: Path, content: str) -> str:
    """Why this file cannot run under the manifest beside it, or "".

    The mirror of `_the_module_type_this_declares_breaks_files_here`, which
    checks a manifest against the files around it. Nothing checked a file
    against the manifest already there, so the same contradiction was caught
    from one side and invisible from the other - the twelve-of-thirteen shape
    this codebase keeps meeting.

    Only the CommonJS-into-ESM direction needs saying. ESM into CommonJS is a
    parse error and `node --check` already refuses it at the write; `require`
    in an ES module is perfectly good syntax and fails only when it runs, so
    no parser sees it and the cost lands on whoever runs the file.

    Measured live on one run. `specialist_testing_5` wrote
    `todo-app/test_core.js` opening `const assert = require('assert');` into a
    project whose `package.json` says `"type": "module"`. The write was
    accepted in silence. The next call ran it and got
    `ReferenceError: require is not defined in ES module scope`; the stage
    then tried to delete the file (refused - it is a test), to write a `.cjs`
    twin (refused - a second copy of the module), read both files and the
    manifest, and finally rewrote it as ESM. Fourteen model calls to learn
    something both facts needed for were already on disk at the moment of the
    write.

    A note rather than a refusal: a file about to be renamed to `.cjs` is a
    legitimate intermediate state, and the refusal for that path already
    names `move_artifact`.
    """
    if target.suffix.lower() != ".js":
        # `.cjs` and `.mjs` carry their own answer and the manifest does not
        # apply to them.
        return ""
    if not _COMMONJS_SYNTAX.search(content or ""):
        return ""
    import json as _json

    for directory in (target.parent, *target.parent.parents[:4]):
        manifest = directory / "package.json"
        try:
            if not manifest.is_file():
                continue
            declared = _json.loads(manifest.read_text(encoding="utf-8")).get("type")
        except (OSError, ValueError):
            return ""
        if declared != "module":
            return ""
        return (
            f"This file uses CommonJS (`require` or `module.exports`), and "
            f"`{manifest.parent.name}/package.json` declares `\"type\": \"module\"`, "
            "so Node loads every `.js` here as an ES module. Running it fails with "
            "`ReferenceError: require is not defined in ES module scope` - not at "
            "import, which is why no parser catches it, but the moment it runs. "
            "Use `import` and `export` here, or rename the file to `.cjs` with "
            "`move_artifact` if it really must be CommonJS."
        )
    return ""


def _the_module_type_this_declares_breaks_files_here(target: Path, content: str) -> str:
    """Why this manifest's `"type"` contradicts files beside it, or "".

    One line of one file decides how Node parses every `.js` in the directory,
    and the stage that writes it is rarely the stage that wrote them. One
    run's `specialist_testing_3`, reaching for jest to get away from a
    failing assertion, rewrote `"type": "module"` to `"type": "commonjs"`
    while all seven exports in `app.js` were still ES syntax - and the write
    went through in silence. `node --check app.js` then gave
    `SyntaxError: Unexpected token 'export'`, and nothing in the product
    loaded under Node again.

    Seven of the fifty-one stored workspaces end with a manifest their own
    files contradict, all in the other direction: `"type": "module"` over a
    file still calling `require`.

    A note and not a refusal. Flipping the type is the legitimate first step
    of a conversion, and refusing it would leave no order in which the work
    could be done - the point is that the stage doing it should know what it
    has just taken on, in the same response, rather than at a milestone
    review several stages later.
    """
    if target.name != "package.json":
        return ""
    try:
        import json as _json

        from app.analysis.integration_checks import (
            _commonjs_loaded_as_a_module,
            _only_the_code,
        )

        declared = (_json.loads(content) or {}).get("type")
        if declared not in ("module", "commonjs"):
            return ""
        contradicting: list[str] = []
        for script in sorted(target.parent.iterdir()):
            if script.suffix != ".js" or not script.is_file():
                continue
            code = _only_the_code(script.read_text(encoding="utf-8", errors="replace"))
            commonjs = bool(re.search(r"""\b(?:require\s*\(|module\.exports\b)""", code))
            modular = bool(
                re.search(r"""^\s*(?:export\b|import\s+[\w{*])""", code, re.M)
            )
            if declared == "commonjs" and modular and not commonjs:
                contradicting.append(script.name)
            elif declared == "module" and commonjs and not modular:
                contradicting.append(script.name)
    except Exception:  # noqa: BLE001 - a hint must never fail a write
        return ""
    if not contradicting:
        return ""
    theirs = "CommonJS" if declared == "module" else "ES module"
    one = len(contradicting) == 1
    return (
        f'This declares `"type": "{declared}"`, which is how Node decides to '
        f"parse every `.js` file in this directory, and "
        f"{', '.join(contradicting[:4])} still "
        f"{'uses' if len(contradicting) == 1 else 'use'} {theirs} syntax. "
        f"Under this manifest {'that file no longer loads' if one else 'those files no longer load'}"
        f". Convert {'it' if one else 'them'} in this sprint or leave the `type` "
        "as it was - the module system is one choice for the whole directory, "
        "not a per-file one."
    )


_A_SCRIPT_TAG = re.compile(r"""<script\b([^>]*)>""", re.I)
_A_TAG_SRC = re.compile(r"""\bsrc\s*=\s*['"]([^'"]+)['"]""", re.I)
_A_TAG_TYPE = re.compile(r"""\btype\s*=\s*['"]([^'"]+)['"]""", re.I)


def _uses_module_syntax(source: str) -> bool:
    """Whether `source` is an ES module, reading only its code."""
    try:
        from app.analysis.integration_checks import _only_the_code

        code = _only_the_code(source)
    except Exception:  # noqa: BLE001
        code = source
    return bool(re.search(r"""^\s*(?:export\b|import\s+[\w{*'"])""", code, re.M))


def _the_page_and_this_module_disagree_on_how_it_loads(
    root: Path, target: Path, content: str
) -> str:
    """Why the page cannot run this script, or "".

    A `<script src="app.js">` with no `type="module"` makes the browser parse
    the file as a classic script. It reaches `export` on the first line and
    throws `Uncaught SyntaxError: Unexpected token 'export'`, and nothing on
    the page works at all. Nothing in the suite notices, because `node --test`
    imports the module directly and never opens the HTML.

    Nine of the fifty-eight stored workspaces ship exactly this - a page that
    is dead on arrival, in runs whose tests pass. It is the most
    product-destroying thing in the corpus and the cheapest to fix: one
    attribute.

    `_modules_loaded_as_plain_scripts` already finds it, at a milestone review
    several stages after both files were written. This says it at the write of
    either side, whichever comes second.
    """
    try:
        if target.suffix.lower() in {".html", ".htm"}:
            pages = [(target, content)]
            scripts_written_now = None
        elif target.suffix.lower() in {".js", ".mjs"}:
            pages = [
                (page, page.read_text(encoding="utf-8", errors="replace"))
                for page in sorted(target.parent.glob("*.htm*"))
                if page.is_file()
            ]
            scripts_written_now = target
        else:
            return ""
        for page, page_text in pages:
            for attributes in _A_SCRIPT_TAG.findall(page_text):
                src = _A_TAG_SRC.search(attributes)
                if not src:
                    continue
                referenced = (page.parent / src.group(1).lstrip("/")).resolve()
                if referenced.suffix.lower() not in {".js", ".mjs"}:
                    continue
                if scripts_written_now is not None:
                    if referenced != scripts_written_now.resolve():
                        continue
                    source = content
                elif referenced.is_file():
                    source = referenced.read_text(encoding="utf-8", errors="replace")
                else:
                    continue
                kind = _A_TAG_TYPE.search(attributes)
                as_module = bool(kind and kind.group(1).strip().lower() == "module")
                modular = _uses_module_syntax(source)
                if modular and not as_module:
                    return (
                        f"`{page.name}` loads `{referenced.name}` with a plain "
                        "`<script>` tag, and that file uses `import`/`export`. "
                        "The browser parses it as a classic script, reaches the "
                        "first `export` and throws `Uncaught SyntaxError: "
                        "Unexpected token 'export'` - the page does nothing at "
                        "all. The suite will not catch it: `node --test` "
                        "imports the module directly and never opens the page. "
                        f'Add `type="module"` to that tag in `{page.name}`.'
                    )
                if as_module and not modular and re.search(
                    r"""\b(?:require\s*\(|module\.exports\b)""", source
                ):
                    return (
                        f"`{page.name}` loads `{referenced.name}` with "
                        '`<script type="module">`, and that file uses '
                        "`require`/`module.exports`, which no browser "
                        "implements. The page throws `require is not defined` "
                        "and does nothing. Write it as an ES module, or drop "
                        f'`type="module"` from the tag in `{page.name}`.'
                    )
    except Exception:  # noqa: BLE001 - a hint must never fail a write
        return ""
    return ""


def _budget_note(root: Path, relative_path: str) -> str:
    """The line-budget note for a write, or "" - see `budget_note_for_a_write`."""
    try:
        from app.analysis.integration_checks import budget_note_for_a_write

        return budget_note_for_a_write(root, relative_path)
    except Exception:  # noqa: BLE001 - a hint must never fail a write
        return ""


def _with_one_trailing_newline(content: str) -> str:
    """`content` ending in exactly one newline, or "" if it is empty.

    Every text file convention and every formatter ends a file with one
    newline, so this is what the model meant either way. The reason it is done
    here rather than left alone is that "did this write change anything?" is a
    byte comparison, and a trailing newline the model happened to include one
    time and not the next makes two identical documents compare as different.

    Measured on one run's `specialist_backend_8`: it wrote `docs/blocker.md`
    with a trailing newline, then wrote the same 600 characters without one.
    That counted as a real change, so the second write reported "written"
    instead of "unchanged", and the "do not write it again" signal - and the
    no-op refusal behind it - both arrived a cycle late. The stage wrote the
    file five times and the run was stopped.
    """
    if not content:
        return content
    return content.rstrip("\n") + "\n"


def _with_escaped_newlines_resolved(original: str, updated: str) -> str | None:
    r"""`updated` with `\n` and `\t` resolved in the span the edit changed.

    None when the changed span holds no such escape, so the caller can tell
    "nothing to try" from "tried and it is still broken".

    Models send `replace` with newlines escaped as the two characters `\` and
    `n`. The forgiving matcher already resolves that on the `find` side - it is
    one of the four spellings it accepts - but the replacement was written
    through literally, which lands `\n` in the file and breaks it. One
    run, `specialist_ui_ux_0`, sent this twice:

        "replace": "\"type\":\"module\",\\n\"scripts\": {\\n ... }"

    and got "not valid JSON at line 6" both times, for a file whose line 6 it
    had never seen.

    Only the changed span is touched. Resolving escapes across the whole file
    would rewrite `console.log("a\nb")` in code the edit never mentioned.
    """
    prefix = 0
    limit = min(len(original), len(updated))
    while prefix < limit and original[prefix] == updated[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < limit - prefix
        and original[len(original) - 1 - suffix] == updated[len(updated) - 1 - suffix]
    ):
        suffix += 1

    middle = updated[prefix : len(updated) - suffix]
    resolved = middle.replace("\\n", "\n").replace("\\t", "\t")
    if resolved == middle:
        return None
    return updated[:prefix] + resolved + updated[len(updated) - suffix :]


#: Markup a person reads, as against code and preformatted text inside it.
_MARKUP_SUFFIXES = (".html", ".htm")
_NOT_MARKUP = re.compile(r"<(script|style|pre|textarea)\b.*?</\1\s*>", re.I | re.S)
#: The two characters backslash-n (or -t) against a tag: an escape that was
#: meant as a line break and lands on the page as text.
_ESCAPE_AT_A_TAG = re.compile(r">[ \t]*\\[nt]|\\[nt][ \t]*<")


def escapes_between_tags(relative_path: str, text: str) -> bool:
    """Whether a page's markup holds a backslash-n beside a tag, outside its scripts and styles."""
    if not relative_path.lower().endswith(_MARKUP_SUFFIXES):
        return False
    return bool(_ESCAPE_AT_A_TAG.search(_NOT_MARKUP.sub("", text or "")))


def _markup_with_its_escapes_resolved(relative_path: str, original: str, updated: str) -> str:
    """An edit to a page with the newlines it escaped twice turned back into newlines.

    Measured on one run. `specialist_ui_ux_0` replaced a line of `index.html`
    with `<meta charset="UTF-8">\\n  <!-- ... -->\\n  <meta name="viewport" ...>`:
    newlines sent as the two characters backslash-n. Nothing parses a page
    strictly, so nothing refused it - and the browser, finding text in the
    head, closed it there and showed "\\n" at the top of the page. The repair
    for the same slip in code applies only when a parser rejects the file.

    Only the span the edit changed, only when the escapes sit against a tag
    outside any script or style, and only when resolving them clears that.
    """
    if not escapes_between_tags(relative_path, updated) or escapes_between_tags(relative_path, original):
        return updated
    rescued = _with_escaped_newlines_resolved(original, updated)
    if rescued is None or escapes_between_tags(relative_path, rescued):
        return updated
    return rescued


def _write_unless_it_changes_nothing(
    target: Path, original: str, updated: str, relative_path: str
) -> None:
    """Write the edit, or refuse an edit that would leave the file as it is.

    An edit whose `replace` is byte-identical to the text it replaces is a
    no-op, and reporting "edited" for it is a lie the agent cannot see through:
    it reads the file back, finds its change absent, concludes the edit failed,
    and sends the identical call again.

    That is what killed one run. Its `specialist_backend_3` made three
    edits to `to-do-app/app.js` whose `find` and `replace` were the same 848
    characters, each answered with `"status": "edited"`, re-reading the file
    between them and seeing the same 73 lines every time. The fifth identical
    request tripped the run-level loop guard and the run failed at
    `awaiting_approval:specialist_backend_3`.

    Checked here, on the content about to be written, rather than by comparing
    `find` to `replace` at the top: the fallbacks that forgive line numbers,
    JSON escaping and indentation all replace a *candidate* rather than `find`,
    so a comparison of the arguments would miss a no-op arriving through any of
    them.
    """
    updated = _json_with_its_commas_put_right(target, relative_path, updated)
    updated = _markup_with_its_escapes_resolved(relative_path, original, updated)
    if updated != original:
        _refuse_an_edit_that_goes_backwards_again(relative_path, updated)
        # Edits are how one run's mock grew: 145 lines to 1,195, one
        # `edit_artifact` at a time. Refusing only the write would leave the
        # path that was actually used wide open.
        _refuse_a_hand_built_dom_again(relative_path, updated, target)
        _refuse_rewriting_the_platform(relative_path, updated, original)
        _refuse_to_switch_a_suite_off(relative_path, original, updated)
        try:
            _refuse_if_broken(relative_path, updated, editing=True)
            _refuse_if_node_cannot_parse(target, relative_path, updated, editing=True)
        except RepositoryToolError:
            # The replacement may have arrived with its newlines escaped. Try
            # the same edit with them resolved, and take it only if that turns
            # a file the parser rejects into one it accepts - which is the
            # evidence that the escaping, not the edit, was the mistake.
            rescued = _with_escaped_newlines_resolved(original, updated)
            if rescued is not None and rescued != original:
                _refuse_if_broken(relative_path, rescued, editing=True)
                _refuse_if_node_cannot_parse(target, relative_path, rescued, editing=True)
                target.write_text(rescued, encoding="utf-8")
                return
            # A file that was ALREADY broken cannot be repaired a piece at a
            # time if every piece is refused for leaving it broken. The model
            # is then trapped: the only move the guard allows is rewriting the
            # whole file correctly in one call, and `write_artifact` refuses
            # broken content too.
            #
            # Measured live on one run. `todo-app/main.js` had a
            # duplicate `li` declaration, and `specialist_ui_ux_2` and `_3`
            # were refused four consecutive edits - at lines 22, 59, 83 and
            # 72. The moving line number is the evidence it was making
            # progress; each step was rejected for not finishing the job.
            #
            # So the rule is the one a pre-merge gate uses: you may not make it
            # worse. An edit to an already-broken file is allowed through and
            # what remains wrong is reported as a note, which is what the
            # model needs to take the next step.
            if _what_is_structurally_wrong(target, relative_path, original) is None:
                raise
            target.write_text(updated, encoding="utf-8")
            return
        target.write_text(updated, encoding="utf-8")
        return
    lines = original.count("\n") + (0 if original.endswith("\n") else 1)
    raise RepositoryToolError(
        f"That edit would leave '{relative_path}' exactly as it is: the replacement "
        f"text is identical to the text it replaces, so nothing was written and the "
        f"file still has {lines} lines. Nothing is wrong with the file or the tool - "
        "this call simply asked for no change. If you meant to change what the code "
        "does, `replace` has to differ from `find`. If the file already contains what "
        "you need, this edit is not required: stop editing it and move on to the rest "
        "of your task."
    )


def search_text(repo_root: str | Path, query: str, *, max_matches: int = 25) -> list[dict[str, str]]:
    """Search repository text for a query and return bounded matches.

    Purpose:
        Help the agent locate references to a symbol, keyword, or config value.

    Inputs:
        repo_root: repository root to search.
        query: literal text to look for.
        max_matches: maximum number of matches to return.

    Returns:
        A list of dictionaries like {"path": "src/app/config.py", "match": "OPENAI_MODEL"}.

    Errors:
        RepositoryToolError if the repository root is invalid.

    Safety model:
        The search is limited to repository files and is bounded by max_matches so
        one agent cannot accidentally scan or dump the entire project.
    """
    root = _normalize_repo_root(repo_root)
    matches: list[dict[str, str]] = []
    
    # For safety, search_text should also probably respect allow_subdirectories, 
    # but the API doesn't pass it yet. We'll leave it as default True here unless modified.
    for path in _iter_repo_files(root):
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".woff", ".woff2"}:
            continue
        try:
            # Skip oversized files before reading: one large artefact would
            # otherwise pull hundreds of megabytes into memory per search.
            if path.stat().st_size > MAX_READABLE_FILE_BYTES:
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if query in content:
            matches.append({"path": path.relative_to(root).as_posix(), "match": query})
            if len(matches) >= max_matches:
                break
    return matches


def read_dependency_metadata(repo_root: str | Path) -> dict[str, object]:
    """Read common dependency metadata from well-known project files.

    Purpose:
        Extract the dependency and runtime metadata that a workflow agent needs to
        choose frameworks, verify compatibility, and understand the project stack.

    Inputs:
        repo_root: repository root to inspect.

    Returns:
        A small dictionary containing metadata such as project name and dependency
        declarations when they exist.

    Errors:
        RepositoryToolError if the repository root is invalid.

    Safety model:
        This helper reads only a narrow set of project metadata files and never runs
        code or evaluates scripts from the repo.
    """
    root = _normalize_repo_root(repo_root)
    metadata: dict[str, object] = {}
    files_to_read = ["pyproject.toml", "package.json", "requirements.txt"]

    for filename in files_to_read:
        candidate = root / filename
        if candidate.exists() and candidate.is_file():
            content = candidate.read_text(encoding="utf-8")
            if filename.endswith(".toml"):
                try:
                    metadata["project"] = tomllib.loads(content).get("project", {})
                except tomllib.TOMLDecodeError as exc:
                    logger.warning("Could not parse %s: %s", filename, exc)
                    metadata["project"] = {}
                metadata["raw_toml"] = content
            elif filename.endswith(".json"):
                try:
                    metadata["package_json"] = json.loads(content)
                except json.JSONDecodeError as exc:
                    logger.warning("Could not parse %s: %s", filename, exc)
                    metadata["package_json"] = {}
            else:
                metadata["requirements"] = content.splitlines()
    return metadata


_PROSE_SUFFIXES = frozenset({".md", ".markdown", ".rst", ".txt"})
"""Artifact extensions whose content is meant to be read by a person."""

_VERSION_SUFFIX = re.compile(
    r"^(?P<base>.+?)[ _.-]+(?:v\d+|copy|new|final|updated|revised)$", re.IGNORECASE
)
"""A filename that is a second copy of another: `spec_v2`, `plan-final`, `notes copy`."""


PROJECT_MARKER = ".project-directory"
"""Names the one directory this run's application code lives in.

A marker on disk rather than a value in graph state, because the thing it has to
survive is not a node boundary but a *process*: agents are built per stage, each
derives paths for itself, and none of them can see what an earlier stage decided.
The file is the only thing every stage shares.

One run built the same to-do application three times over - in
`simple-todo-list-app`, `simple_todo_list_app`, and `thehub` - because each
stage picked a name and nothing carried the first choice forward. None of the
three was ever finished.
"""

#: Files that define a Node/Python project. At the workspace root, once a
#: project directory is pinned, each of these creates a *second* project that
#: competes with it.
#:
#: One run ended with two: `package.json` at the root declaring jest 30 and
#: another in the project declaring jest 29, two `jest.config.js`, two
#: `jestSetup.js`, two `node_modules`. `npm test` ran the root's jest against
#: the project's tests and failed with "Identifier 'jest' has already been
#: declared" - three remediation rounds chased that and never had a chance.
_PROJECT_MANIFESTS = frozenset({
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", "jsconfig.json", "requirements.txt", "pyproject.toml",
    "setup.py", "setup.cfg", "Pipfile", "Cargo.toml", "go.mod",
})

_MANIFEST_PREFIXES = ("jest.config", "jest.setup", "jestsetup", "vite.config", "webpack.config", "babel.config")


#: Extensions that are source code, not a document a person reads.
_CODE_SUFFIXES = frozenset({
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".rb", ".go", ".rs",
    ".java", ".php", ".c", ".h", ".cpp", ".cs", ".sh", ".css", ".html", ".htm",
})


_SCAFFOLDABLE_SUFFIXES = frozenset({
    ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".rb", ".go", ".rs",
    ".java", ".html", ".htm", ".css", ".scss", ".vue", ".svelte",
})


def _scaffolding_at_the_workspace_root(
    root: Path, relative_parts: tuple[str, ...]
) -> str | None:
    """Why this file cannot go here, or None if it can.

    Every prompt says to build inside one top-level project directory, and
    until now nothing enforced it. Measured on one run: the UI specialist
    wrote `css/style.css` and `index.html` straight into the workspace root, so
    the pin took `css` as the project and the application would have been built
    inside a directory named after its stylesheets.

    Deliberately narrow, because a refusal that fires on a legitimate write
    costs a stage:

    - only source files, never documents or configuration;
    - only while NO project is pinned, so this can never contradict the pin;
    - only at the root or inside a conventional asset folder, which is the
      shape of the mistake. A file written to `my-app/index.html` pins
      `my-app` and is exactly what is wanted.
    """
    if not relative_parts:
        return None
    if Path(relative_parts[-1]).suffix.lower() not in _SCAFFOLDABLE_SUFFIXES:
        return None

    at_root = len(relative_parts) == 1
    in_asset_folder = len(relative_parts) > 1 and relative_parts[0] in _NON_PROJECT_DIRECTORIES
    if not (at_root or in_asset_folder):
        return None
    # `docs/` and `tests/` have their own rules and their own reasons.
    if relative_parts[0] in ("docs", "tests", "test"):
        return None

    shown = "/".join(relative_parts)
    project = pinned_project_directory(root)
    if project:
        # A source file at the root once a project exists is the other half of
        # the same mistake: on one run `index.html` sat at the workspace
        # root beside the `css/` that had been pinned, belonging to neither.
        return (
            f"Refusing to write '{shown}': this run's project is '{project}', and "
            f"source files belong inside it. Write '{project}/{shown}' instead - "
            "a file at the workspace root is part of no project and nothing will "
            "build or test it."
        )
    return (
        f"Refusing to write '{shown}': the application needs one top-level "
        "project directory, and this run does not have one yet. Writing here "
        "leaves the product scattered across the workspace root, and whichever "
        "folder is written to first becomes the project for every later stage - "
        f"on one run that was 'css'. Create the directory first by writing "
        f"inside it: name it after the product in lowercase-with-hyphens, for "
        f"example 'my-app/{shown}'."
    )


def _tests_outside_the_project(root: Path, relative_parts: tuple[str, ...]) -> str | None:
    """Why this test does not belong at the workspace root, or None if it does.

    The project pin decides where code lives, and a test is code: the runner is
    invoked inside the project, so a suite at the workspace root is one the
    project's own `npm test` will never collect.

    Measured on one run, which completed with two test directories -
    `tests/` at the workspace root and `simple-to-do-list-app/tests/` - holding
    three files of the same names. Nothing reconciled them, both were run by
    hand in different stages, and the milestone reviewer counted them twice.
    That is the two-sources-of-truth pattern that has cost this workflow a
    sprint every time it has appeared.

    Only refuses once a project directory exists. The first stage to write a
    test, before any project is pinned, has nowhere better to put it.
    """
    if not relative_parts or not looks_like_a_test("/".join(relative_parts)):
        return None
    project = pinned_project_directory(root)
    if not project or relative_parts[0] == project:
        return None

    destination = f"{project}/{'/'.join(relative_parts)}"
    return (
        f"Refusing to write '{'/'.join(relative_parts)}': the project is "
        f"'{project}', and its test runner only collects what is inside it. A "
        f"suite here would be run by whoever remembers it exists and by nothing "
        f"else. Write '{destination}' instead."
    )


def _code_in_the_documents_directory(
    root: Path, relative_parts: tuple[str, ...]
) -> str | None:
    """Why this file does not belong in `docs/`, or None if it does.

    `docs/` is what every reviewer reads as documentation, and what the
    workflow's own generated documents share. Code there is read as prose by
    one stage and imported by none.

    Measured on one run: the testing specialist wrote `/docs/test_suite.js`
    and then edited it five times running, fighting JSDOM scope problems in a
    file that no test runner would ever collect - the project's runner looks in
    the project directory. The repeat guard stopped the stage; the file was in
    the wrong place from the first write.

    Names the destination, not just the rule. A refusal that says only "not
    here" leaves an agent that has read the rule and cannot apply it: on
    one run the testing specialist was refused `docs/tests/playwright.config.js`,
    answered "the requirement conflicts, so we have a blocker", and shipped the
    milestone with no UI tests at all - the run then failed the review for
    missing them. `_test_outside_the_project` already names where to write
    instead, and this is the same refusal with the same information missing.
    """
    if len(relative_parts) < 2 or relative_parts[0] != "docs":
        return None
    suffix = Path(relative_parts[-1]).suffix.lower()
    if suffix not in _CODE_SUFFIXES:
        return None
    project = pinned_project_directory(root)
    destination = (
        f"{project}/{'/'.join(relative_parts[1:])}"
        if project
        else "/".join(relative_parts[1:]) or relative_parts[-1]
    )
    return (
        f"Refusing to write '{'/'.join(relative_parts)}': `docs/` is for documents "
        "a person reads, and a reviewer reads everything there as documentation. "
        f"A {suffix} file belongs in the project directory, where the test runner "
        "and the build will actually find it. "
        f"Write '{destination}' instead."
    )


def _is_project_manifest(name: str) -> bool:
    lowered = name.lower()
    return lowered in _PROJECT_MANIFESTS or lowered.startswith(_MANIFEST_PREFIXES)


#: Top-level directories that are not the project and never pin it.
_NON_PROJECT_DIRECTORIES = frozenset({
    "docs", "large_tool_results", "tests", "test",
    # Conventional folders that live INSIDE a project and are never the project
    # itself. Measured on one run: the UI specialist wrote
    # `css/style.css` before anything else, the pin took `css` as the project,
    # and every later stage would have built the application inside a directory
    # called `css` - with `index.html` stranded at the workspace root beside it.
    "css", "js", "scss", "sass", "less", "styles", "stylesheets", "scripts",
    "assets", "static", "public", "img", "images", "media", "fonts",
    "components", "lib", "vendor", "node_modules", "bin", "obj",
    # `src` is where a project keeps its source, not the name of one. Left out
    # of this list it pinned as readily as `css` did.
    "src", "source", "app_src",
    # The tiers of a product are parts of it, not the product. A brief asking
    # for a backend and a frontend - which `brief_medium` does - writes one of
    # them first, and whichever it is would be pinned as the whole project:
    # `backend/main.py` pins `backend`, and `frontend/App.jsx` is then refused
    # as a second project. Neither can be the project, so the agent has to
    # create one and put both inside it, which is the layout every prompt
    # already asks for.
    "backend", "frontend", "client", "server", "api", "web", "ui",
    "services", "apps", "packages",
})


def _is_project_directory(name: str) -> bool:
    return (
        bool(name)
        and not name.startswith(".")
        and name not in _NON_PROJECT_DIRECTORIES
        and name not in IGNORED_DIRECTORIES
    )


def pinned_project_directory(root: Path) -> str | None:
    """The project directory this run has already committed to, if any."""
    marker = root / PROJECT_MARKER
    try:
        name = marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return name or None


def _pin_project_directory(root: Path, name: str) -> None:
    """Record the project directory the first time one is written to.

    Written once and never rewritten: the point is that the first choice is the
    one that lasts. A failure to write is not worth failing the artifact over -
    the guard simply has nothing to enforce next time.
    """
    marker = root / PROJECT_MARKER
    if marker.exists():
        return
    try:
        marker.write_text(f"{name}\n", encoding="utf-8")
    except OSError:
        logger.warning("Could not record the project directory at %s", marker, exc_info=True)
        return
    # And made to exist. A pinned directory nobody has written into yet did not
    # exist, so every stage that looked before writing - the lead listing it,
    # a parallel specialist whose sibling had not written yet, a command run in
    # it - got path_not_found for the one directory the run had committed to.
    # Measured on the runs of 2026-09-30: four to six failed calls a run, and
    # the lead repeating the same `ls` until the tool was withheld. An empty
    # directory is the truthful answer to "what is in the project so far".
    try:
        (root / name).mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("Could not create the project directory %s", root / name, exc_info=True)


#: Folders a plan names that live inside a project, never the project itself.
_SUBDIRECTORY_NAMES = frozenset({
    "src", "test", "tests", "spec", "specs", "e2e", "lib", "public", "static",
    "assets", "scripts", "styles", "css", "js", "config", "dist", "build", "docs",
    "end-to-end", "unit-tests", "e2e-tests", "test-results", "node-modules",
})

#: A top-level folder as a plan spells it: a lowercase-with-hyphens name followed
#: by `/`, not itself part of a longer path.
_A_PLANNED_DIRECTORY = re.compile(r"(?<![\w./-])([a-z0-9]+(?:-[a-z0-9]+)+)/")


def pin_the_directory_a_plan_names(root: str | Path, plan_text: str) -> str | None:
    """Pin the project directory the technical lead's plan names, if none is yet.

    The pin was taken from the first file written. In parallel mode several
    specialists start before anything exists, each names its own directory, and
    whichever writes first wins; the rest are refused and redo their work. One
    run's lead named `simple-to-do-list-app/` in its plan, and
    `specialist_ui_ux_0` - given a task that said only "Write index.html" -
    wrote `task-manager/index.html` and was refused.

    The name is the most-mentioned hyphenated top-level folder in the plan,
    mentioned at least twice: the layout rules ask for "lowercase-with-hyphens",
    and a bare word followed by `/` in a plan is far more often a subfolder
    (`test/`) or prose (`empty/whitespace`). On the sprint-one plans of four
    runs this chose `simple-to-do-list-app` (twice), `todo-app` and
    `todo-list` - each the directory the run then used.

    Never overrides an existing pin, and does nothing once any project
    directory exists: then the code already says where it lives.
    """
    base = Path(root)
    if pinned_project_directory(base) is not None:
        return None
    try:
        if any(
            entry.is_dir() and _is_project_directory(entry.name) for entry in base.iterdir()
        ):
            return None
    except OSError:
        return None
    counts: dict[str, int] = {}
    for name in _A_PLANNED_DIRECTORY.findall(plan_text or ""):
        if name in _SUBDIRECTORY_NAMES or not _is_project_directory(name):
            continue
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    name, mentions = max(counts.items(), key=lambda item: (item[1], item[0]))
    if mentions < 2:
        return None
    _pin_project_directory(base, name)
    return name


#: The longest project directory name taken from a product name.
_MOST_NAME_CHARACTERS = 48


#: Where a product's name ends and a description of it begins: a spaced dash,
#: a colon, or an opening bracket. "To-Do" keeps its hyphen.
_A_SUBTITLE = re.compile(r"\s+[\u2014\u2013-]\s+|:\s|\s*[(\[|]")


def _directory_name_for(product_name: str) -> str:
    """The product's name as a directory: lowercase, words joined by hyphens.

    The name only, and cut between words. One run's intake named the product
    "Simple To-Do List App — greenfield single-page task manager
    (create/read/update/delete + status filter, browser-only persistence)", and
    the directory became `simple-to-do-list-app-greenfield-single-page-tas` -
    the description included and the last word cut in half.
    """
    text = str(product_name or "")
    title = _A_SUBTITLE.split(text, 1)[0].strip() or text
    name = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if len(name) > _MOST_NAME_CHARACTERS:
        cut = name[:_MOST_NAME_CHARACTERS]
        if name[_MOST_NAME_CHARACTERS] != "-" and "-" in cut:
            cut = cut[: cut.rfind("-")]
        name = cut
    return name.rstrip("-")


def pin_the_directory_the_product_names(root: str | Path, product_name: str) -> str | None:
    """Pin the product's name, as a directory, before any stage looks for one.

    The pin came from the lead's plan, after the lead had answered - so for the
    whole of the stages before it, and the lead's own exploration, the run had
    no project directory. Each stage derived one from the product name for
    itself: on the runs of 2026-09-30 the architect and the lead both listed
    `/simple-to-do-list-app` for a product called "Simple To-Do List App",
    before it existed, and the lead repeated the listing until the tool was
    withheld - five of one lead's eleven calls.

    So the name is fixed once, at intake, the way every one of them was
    deriving it: lowercase, words joined by hyphens. Only for a workspace with
    no project directory yet - an uploaded codebase already says where its code
    lives - and never over an existing pin. A name with no letters or digits
    in the Latin alphabet pins nothing, and the plan's own name is used later
    as before.
    """
    base = Path(root)
    if pinned_project_directory(base) is not None:
        return None
    try:
        if any(entry.is_dir() and _is_project_directory(entry.name) for entry in base.iterdir()):
            return None
    except OSError:
        return None
    name = _directory_name_for(product_name)
    if not name or name in _SUBDIRECTORY_NAMES or not _is_project_directory(name):
        return None
    _pin_project_directory(base, name)
    return name


def _file_blocking_directory(root: Path, target: Path) -> str | None:
    """The workspace-relative path of a plain file standing where a directory must go.

    Returns None when the parents are clear. Checked before `mkdir` rather than
    after, because the exception `mkdir` raises names the collision but not what
    the agent should do about it - and it escapes as a crash rather than as a
    tool result the agent can act on.
    """
    try:
        relative = target.relative_to(root)
    except ValueError:
        return None
    walked = root
    for part in relative.parts[:-1]:
        walked = walked / part
        if walked.exists() and not walked.is_dir():
            return str(walked.relative_to(root))
    return None


def _directory_slug(name: str) -> str:
    """A directory name reduced to what distinguishes it.

    Separators and case are exactly what agents disagree about when each one
    derives a folder name from the same product name, so they are what this
    removes: `simple-todo-list-app` and `simple_todo_list_app` both reduce to
    `simpletodolistapp`.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _forks_existing_directory(root: Path, target: Path) -> Path | None:
    """The top-level directory this write would fork, if it is forking one.

    The shared prompt tells every agent to put code in a folder named after the
    product, and every agent derives that name for itself. Sprint 1 of
    one run built `simple-todo-list-app`; sprint 2 derived
    `simple_todo_list_app` and rebuilt the application from scratch beside it,
    so the project existed twice and neither copy was finished.

    Matched on the slug rather than the exact name, because a name that differs
    only in separators or case is not a new component - it is the same folder
    spelled differently. `frontend` and `backend` share no slug and are left
    alone, which is the distinction that keeps this from refusing real work.
    """
    try:
        relative = target.relative_to(root)
    except ValueError:
        return None
    if len(relative.parts) < 2:
        return None  # a file at the root forks nothing

    wanted = relative.parts[0]
    slug = _directory_slug(wanted)
    if not slug:
        return None

    try:
        siblings = [
            entry
            for entry in root.iterdir()
            if entry.is_dir()
            and entry.name not in IGNORED_DIRECTORIES
            and not entry.name.startswith(".")
            and _directory_slug(entry.name) == slug
        ]
    except OSError:
        return None
    if not siblings:
        return None

    # When a fork already exists - because it was made before this guard, or by
    # hand - refusing writes to *both* copies leaves the agent unable to write
    # anywhere, which is worse than the duplication. Nominate the established
    # one and send everything there: the copy with more files, oldest first on a
    # tie, because the one that has been built in is the one to keep building.
    def _weight(directory: Path) -> tuple[int, float]:
        try:
            count = sum(1 for _ in directory.rglob("*") if _.is_file())
        except OSError:
            count = 0
        try:
            age = -directory.stat().st_mtime
        except OSError:
            age = 0.0
        return (count, age)

    canonical = max(siblings, key=_weight)
    return None if canonical.name == wanted else canonical


#: Extensions that are all the same language, so two of them side by side with
#: one stem are two copies of one module rather than two modules.
_SAME_LANGUAGE = ((".js", ".mjs", ".cjs"), (".ts", ".mts", ".cts"), (".jsx", ".tsx"))

#: How alike two files must be before the second is called a copy of the first.
#: Well below "identical", because a fork is edited after it is made, and well
#: above "shares a few lines", because two modules in one project share imports.
_COPY_SIMILARITY = 0.6


def _the_same_module_already_here(target: Path, content: str) -> Path | None:
    """The file this write forks by changing only its extension, or None.

    `_supersedes_existing` catches `spec_v2.md` beside `spec.md`. This catches
    the other spelling of the same mistake, which the extension hides.

    Measured on one run: `simple-to-do-list-app/app.js` (4,887 bytes) and
    `simple-to-do-list-app/app.mjs` (4,853 bytes), near-identical copies of one
    application. From there every fix lands in one of them, the test file
    imports whichever it imports, and half the remediation does nothing - which
    is what that run's two test rounds and 57-call defect fix were spent on.

    Similarity is required, not just the name. Two modules in a project can
    legitimately share a stem across a language boundary, and refusing a file
    that is genuinely different would be worse than allowing a fork.
    """
    import difflib

    suffix = target.suffix.lower()
    family = next((group for group in _SAME_LANGUAGE if suffix in group), None)
    if family is None:
        return None
    for other in family:
        if other == suffix:
            continue
        sibling = target.with_suffix(other)
        if not sibling.is_file():
            continue
        try:
            existing = sibling.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if difflib.SequenceMatcher(None, existing, content).quick_ratio() < _COPY_SIMILARITY:
            continue
        if difflib.SequenceMatcher(None, existing, content).ratio() >= _COPY_SIMILARITY:
            return sibling
    return None


def _this_stage_already_deleted(relative_path: str) -> bool:
    """Whether this stage removed the file itself - see `seen_content`.

    Wrapped so a missing or unwired memo can never turn a plain "not there"
    into an exception.
    """
    try:
        from app.tools.seen_content import this_stage_deleted_it

        return this_stage_deleted_it(relative_path)
    except Exception:  # noqa: BLE001 - see docstring
        return False


def _where_this_stage_put_it(relative_path: str) -> str | None:
    """Where this stage moved this file, or None - see `seen_content`.

    Wrapped so a missing or unwired memo can never turn a plain "not found"
    into an exception: the answer is a nicety, the refusal is the point.
    """
    try:
        from app.tools.seen_content import where_this_stage_moved_it

        return where_this_stage_moved_it(relative_path)
    except Exception:  # noqa: BLE001 - see docstring
        return None


def _supersedes_existing(target: Path) -> Path | None:
    """The canonical file this write would fork, if it is forking one.

    Agents asked to revise a document sometimes write a new one beside it
    instead. Observed live: the architect produced
    `docs/technical_specification_v2.md` while `docs/technical_specification.md`
    already existed. From that point the reviewer had two specifications to read
    and reported the differences between them as contradictions in the design -
    a blocking finding that existed only because the second file did. The run
    spent its last two revisions on it and stopped unresolved.

    Deliberately narrow. Only an explicit version marker counts, so a genuine
    series like `adr_1.md` and `adr_2.md` is untouched, and nothing is refused
    unless the file it forks is actually there.
    """
    match = _VERSION_SUFFIX.match(target.stem)
    if not match:
        return None
    canonical = target.with_name(f"{match.group('base')}{target.suffix}")
    return canonical if canonical.is_file() else None


def _is_json_document(content: str) -> bool:
    """Whether `content` is a whole JSON object or array rather than prose.

    Deliberately narrow. A Markdown file may well contain a fenced JSON example,
    so only content that is *entirely* one JSON value counts - that is the shape
    a model produces when it saves its structured response by mistake.
    """
    stripped = content.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        return isinstance(json.loads(stripped), (dict, list))
    except ValueError:
        return False


_CONTROL_TOKEN_DOC = """A model's own special tokens, in the `<|name|>` spelling every family uses.

`<|END_THINKING|>`, `<|START_ACTION|>`, `<|im_start|>`, `<|eot_id|>` and the
rest are the delimiters a chat template wraps around a turn. They are not
supposed to survive into content, and when they do the file is not what the
model meant to write - it is the model's transcript, cut off mid-thought.

Measured on one run, on North-Mini-Code-1.0. `Task.test.mjs` was written
ending:

    });

    ");<|END_THINKING|><|START_ACTION|>[{

That is a syntax error on line 963, and it broke the entire 963-line suite.
The agent could not diagnose it - a model does not read its own control tokens
as foreign text - so `defect_fix_1_0` spent the rest of the run editing
`TaskManager.js`, which was never the broken file, and the run died on the
repeat guard at 1,098 events.

The pattern is safe to refuse outright. No stylesheet, markup or program
contains it, and prose that genuinely discusses these tokens is rare enough
that being asked to write it a different way costs far less than shipping a
corrupted artifact nobody can see is corrupted.
"""


#: A top-level definition, in the languages a whole-file rewrite is most often
#: sent for. Deliberately shallow: this only has to notice that a name the file
#: used to define is no longer defined, not parse anything.
_A_DEFINITION = (
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=", re.M),
    re.compile(r"^\s*(?:export\s+)?class\s+(\w+)", re.M),
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.M),
    re.compile(r"^\s*(?:pub\s+)?fn\s+(\w+)", re.M),
    re.compile(r"^\s*func\s+(\w+)", re.M),
)

#: How many lost names one message lists.
MAX_LOST_DEFINITIONS_NAMED = 6

#: Warnings before the write is refused. The same two rungs as
#: `_refuse_an_edit_that_goes_backwards_again` and the no-op write refusal: a
#: rewrite that drops a definition is sometimes a deliberate refactor, and twice
#: is enough to establish it was not a slip.
LOSSES_BEFORE_REFUSING_A_REWRITE = 2

#: Per-instance fallback, for a write outside a graph run.
_LOSSES_OUTSIDE_A_RUN: dict[str, int] = {}

#: A whole-file write under this share of the lines of the file it replaces,
#: that would remove at least `FRAGMENT_DROPS` definitions, is a fragment sent
#: as the file: refused on the first send rather than noted. See
#: `_a_fragment_sent_as_the_file`.
FRAGMENT_SHARE = 0.25
FRAGMENT_DROPS = 5

#: Per-instance fallback for the fragments refused once, outside a graph run.
_FRAGMENTS_OUTSIDE_A_RUN: dict[str, bool] = {}


def _what_a_file_defines(content: str) -> set[str]:
    """The top-level names a file defines, by the shallowest reading that works."""
    found: set[str] = set()
    for pattern in _A_DEFINITION:
        found.update(pattern.findall(content or ""))
    return found


def _what_this_rewrite_would_drop(target: Path, content: str) -> list[str]:
    """Names the file defines now and would not after this write."""
    try:
        if not target.is_file():
            return []
        existing = target.read_text(encoding="utf-8")
    except OSError:
        return []
    if not existing.strip():
        return []
    return sorted(_what_a_file_defines(existing) - _what_a_file_defines(content))


def _who_has_it_now(root: Path, relative_path: str) -> str:
    """" (last written by specialist_testing_4)", or "". Never raises."""
    try:
        from app.analysis import project_memory

        stage = str(project_memory.who_changed(root, relative_path) or "").strip()
    except Exception:  # noqa: BLE001 - a description must not decide a write
        return ""
    return f" (last written by {stage})" if stage else ""


def _refuse_a_blind_overwrite_of_another_stage_s_file(
    root: Path, target: Path, relative_path: str, content: str
) -> None:
    """Refuse a whole-file write over another stage's file this stage has not seen.

    In parallel mode a stage decides what to write from the workspace as it was
    when it looked, and another stage can create the same file in the meantime.
    Measured on one run: `specialist_ui_ux_0` listed an empty workspace at
    16:14, spent twelve minutes on one reply, and at 16:26 wrote
    `todo-app/index.html` over the page `specialist_testing_4` had written at
    16:25 - never having seen it. `specialist_backend_2` rewrote `app.js` a
    minute later over `specialist_testing_4`'s DOM wiring the same way.
    `_a_rewrite_that_drops_what_the_file_defines` catches a lost function; a
    page has none, so nothing was said.

    Only when the file's last writer is a different stage and this stage has
    not read or written the version on disk. Reading it lifts the refusal, so it
    costs one call and never blocks: after that the write is a decision made
    with the other stage's work in view.
    """
    try:
        if not target.is_file():
            return
        existing = target.read_text(encoding="utf-8")
        if not existing.strip() or existing == content:
            return
        from app.analysis import project_memory
        from app.observability.transcript import _stage_from_config
        from app.tools.seen_content import has_seen_this_version

        writer = project_memory.who_changed(root, relative_path)
        me = _stage_from_config("")
        if not writer or not me or writer == me:
            return
        if has_seen_this_version(relative_path, existing):
            return
    except Exception:  # noqa: BLE001 - bookkeeping must never decide a write
        return
    shown = _the_version_there_now(relative_path, existing)
    if shown:
        # The refusal is the read. "Read it first" cost a call the stage often
        # did not make: measured across one day's runs, this was the most
        # common refusal there was, and one fix stage sent the same whole-file
        # write of a 13-line manifest twice, tried to delete the file, and
        # reported the change as blocked. Shown here, the other stage's work is
        # in view and the next write is a decision.
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': it already exists, '{writer}' wrote "
            f"the version there now ({_line_count(existing)} lines), and you had not "
            "seen it - writing the whole file would have replaced that work unread. "
            f"Nothing was written. This is the file as it stands:\n{shown}\n"
            "You have now seen it. Change your part with `edit_artifact` or "
            "`replace_lines`, keeping what the other stage wrote; or, if replacing "
            "the whole file is what you mean, send the write again with everything "
            "above that still has to be there."
        )
    raise RepositoryToolError(
        f"Refusing to write '{relative_path}': it already exists, '{writer}' wrote "
        f"the version there now ({_line_count(existing)} lines), and you have not "
        "seen it - writing the whole file would replace that work unread. Nothing "
        "was written. Read it first; then change your part with `edit_artifact`, or "
        "write the whole file again if replacing it is what you mean."
    )


#: The longest file a refusal quotes whole. Past this it is a read, and the
#: stage is told to make one.
MOST_LINES_A_REFUSAL_SHOWS = 60


def _the_version_there_now(relative_path: str, existing: str) -> str:
    """A short file, numbered, and recorded as seen by this stage; or "".

    "" for a file too long to quote, or when it cannot be recorded as seen -
    then showing it would promise a second write that is refused again.
    """
    lines = existing.splitlines()
    if not lines or len(lines) > MOST_LINES_A_REFUSAL_SHOWS:
        return ""
    try:
        from app.tools.seen_content import has_seen_this_version, remember

        remember(relative_path, existing)
        if not has_seen_this_version(relative_path, existing):
            return ""
    except Exception:  # noqa: BLE001 - then it is a read, as before
        return ""
    return _quote(lines, 0, len(lines), None)


def _a_fragment_sent_as_the_file(
    target: Path, relative_path: str, content: str, dropped: list[str]
) -> str:
    """The refusal for a fragment written over the whole file, or "".

    The rung below names a lost definition and lets the first such write land,
    because a rewrite that drops one is sometimes a deliberate refactor. A few
    lines written over a module that defined dozens of names is not one.
    Measured over the stored runs: of 78 first writes that rule let land, the
    largest losses were 1 to 17 lines sent over a module, removing 13 to 54
    definitions - one run's fix stage wrote a four-line function over its
    465-line `app.js`, every test failed, and the fix was reverted.

    Refused once per content: the same write sent again is a decision, and
    passes on to the rung below.
    """
    if len(dropped) < FRAGMENT_DROPS:
        return ""
    try:
        existing = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    before, after = _line_count(existing), _line_count(content)
    if after >= before * FRAGMENT_SHARE:
        return ""
    import hashlib

    digest = hashlib.sha1(f"{relative_path}\0{content}".encode("utf-8", "replace")).hexdigest()
    try:
        from app.agents.stage_memory import store

        refused = store("fragments_written_as_a_file", _FRAGMENTS_OUTSIDE_A_RUN)
    except Exception:  # noqa: BLE001 - bookkeeping must not decide a write
        refused = _FRAGMENTS_OUTSIDE_A_RUN
    if refused.get(digest):
        return ""
    refused[digest] = True
    return (
        f"Refusing to write '{relative_path}': a whole-file write replaces the file, "
        f"and what you sent is {after} line(s) where the file has {before}, so this "
        "would leave only what you sent. Nothing was written. To change one part, "
        "change that part with `edit_artifact` or `replace_lines` and the rest stays. "
        "If the file really is to become only this, send the same write again."
    )


def _a_rewrite_that_drops_what_the_file_defines(
    root: Path, target: Path, relative_path: str, content: str
) -> str:
    """The note for a whole-file write that would remove a definition, or "".

    Nothing compared a whole-file write against the file it replaces, so a
    rewrite that dropped a function removed it silently - no note, no refusal,
    and the next stage to look found the behaviour missing with no record of
    where it went.

    Measured on one run, which failed at the milestone revision limit. Its
    `todo-app/app.js`, by successful whole-file write, paired strictly by
    tool_call_id:

        16:42:39  specialist_ui_ux_1     4748B  18 definitions
        16:53:43  defect_fix_1_0         6906B  28
        16:59:45  defect_fix_1_2         8101B  33
        21:26:29  specialist_backend_0   5322B  28   deleteTask, handleTaskActions gone

    2,779 bytes and five definitions removed by one write from a different stage,
    among them `handleTaskActions` - the event-delegation handler - and
    `deleteTask`. The reviewer then reported, three times until the run died,

        [blocking] correctness: Checkbox toggle handler is missing from init()'s
        event delegation block ... clicking them has no effect
        [blocking] correctness: Filter functionality is entirely missing despite
        UI elements existing

    In parallel mode six specialists were writing that one file.

    Two rungs, as elsewhere in this module: the loss is named on the first write
    and the second is refused, because a rewrite that drops a definition is
    sometimes a deliberate refactor and twice is enough to show it was not a slip.
    """
    # Not a test file. Every test body has locals, so rewriting a suite reads as
    # losing a dozen definitions - and rewriting a suite is ordinary work.
    #
    # Measured in production on one run, the first firing this guard had:
    # `specialist_backend_2` rewrote `task-manager/app.test.mjs` and was told it
    # was removing `__dirname`, `__filename`, `after`, `err`, `exactTitle`,
    # `longTitle` and four more - module-scope consts, a `node:test` import and
    # locals inside test bodies. None of it is an interface anything depends on.
    #
    # Nested definitions are counted deliberately, because one run's lost
    # handler lived inside `init()`. That is right for product code and wrong
    # here, and a test file is the one place the two diverge. A suite that really
    # disappears is caught by `_a_suite_registered_twice` and by the case counts
    # in the execution ledger.
    from app.analysis.file_kinds import is_test

    if is_test(relative_path):
        return ""
    dropped = _what_this_rewrite_would_drop(target, content)
    if not dropped:
        return ""
    listed = ", ".join(f"`{name}`" for name in dropped[:MAX_LOST_DEFINITIONS_NAMED])
    more = f" and {len(dropped) - MAX_LOST_DEFINITIONS_NAMED} more" if len(dropped) > MAX_LOST_DEFINITIONS_NAMED else ""
    fragment = _a_fragment_sent_as_the_file(target, relative_path, content, dropped)
    if fragment:
        raise RepositoryToolError(fragment + f" It would remove {listed}{more}.")
    try:
        from app.agents.stage_memory import store

        seen = store("rewrites_that_dropped_definitions", _LOSSES_OUTSIDE_A_RUN)
        seen[relative_path] = seen.get(relative_path, 0) + 1
        losses = seen[relative_path]
    except Exception:  # noqa: BLE001 - bookkeeping must not decide a write
        losses = 1
    whose = _who_has_it_now(root, relative_path)
    if losses >= LOSSES_BEFORE_REFUSING_A_REWRITE:
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}'{whose}: it would remove {listed}{more}, "
            f"which the file defines now, and this is the {losses}{'nd' if losses == 2 else 'th'} "
            "rewrite of it in this stage that would. Nothing was written. Another "
            "task in this sprint may own the part you are dropping - in parallel "
            "mode it may have been written minutes ago. Change only your own part "
            "with `edit_artifact` or `replace_lines`. If those names really should "
            "go, delete them one at a time so the change is visible, or say in "
            "your structured response why the file should be replaced whole."
        )
    return (
        f" This write removes {listed}{more}, which the file{whose} defines now. If "
        "that was not deliberate, another task may own that code - in parallel mode "
        "it may have been written minutes ago - and a targeted `edit_artifact` keeps "
        "it. Nothing else in this pipeline will tell you it is gone."
    )


def _refuse_control_tokens(relative_path: str, content: str) -> None:
    """Refuse content carrying the model's own turn delimiters."""
    # Imported here, not at module scope: `app.agents` imports the role agent,
    # which imports the agent toolkit, which imports this module. At module
    # scope that cycle leaves `repository` half-built for whichever entrypoint
    # touches the sandbox first.
    from app.agents.model_output import find_leaked_marker

    found = find_leaked_marker(content or "")
    if found is None:
        return
    raise RepositoryToolError(
        f"Refusing to write '{relative_path}': the content contains "
        f"'{found}', which is one of your own special tokens and not "
        "part of the file. Content that carries these is a turn that was cut "
        "off mid-way, so what would be saved is a truncated transcript rather "
        "than the file you meant. Nothing was written. Send the file again, "
        "complete, with no such markers in it."
    )



def write_approved_artifact(
    repo_root: str | Path,
    relative_path: str,
    content: str,
    *,
    by_the_workflow: bool = False,
) -> dict[str, str]:
    """Write a generated artifact only inside the repository root or its subfolders.

    `by_the_workflow` is for `app.graph.workflow._record_document`, the one
    caller that is allowed to write the documents in `WORKFLOW_DOCUMENTS` -
    it renders them from a stage's structured response. Every agent-facing
    path leaves it false. See `_a_workflow_document`.

    Purpose:
        Save a reviewable artifact from an agent without allowing arbitrary writes.

    Inputs:
        repo_root: repository root.
        relative_path: target path under the repository root.
        content: text content to save.

    Returns:
        A dictionary containing the final artifact path and a short summary.

    Errors:
        RepositoryToolError if the target escapes the approved directory or the repo.

    Safety model:
        The output directory is fixed to the repo root. Any path outside it is
        rejected. This ensures the workflow can produce artifacts without exposure to
        unrelated files.
    """
    root = _normalize_repo_root(repo_root)
    artifact_root = Path(root).resolve()
    cleaned_path = _repo_relative_path(artifact_root, relative_path)
    target = (artifact_root / cleaned_path).resolve()
    if artifact_root not in target.parents and target != artifact_root:
        raise RepositoryToolError(
            f"Artifact path is outside the repository root: {relative_path}"
        )
    if not by_the_workflow:
        content = _content_without_a_copied_gutter(content, 1)

    if is_secret_path(target):
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': the path matches a credential file pattern."
        )
    locked = _the_harness_s_own_or_the_locked_suite(artifact_root, target)
    if locked is not None:
        raise RepositoryToolError(locked)
    cut_off = _cut_off_at_a_quote(relative_path, content)
    if cut_off is not None:
        raise RepositoryToolError(cut_off)
    installed = _installed_by_a_tool(artifact_root, target)
    if installed is not None:
        raise RepositoryToolError(installed)
    # The owner first: it names who writes the file, which says more.
    someone_else_s = _another_work_order_s_file(artifact_root, target)
    if someone_else_s is not None:
        raise RepositoryToolError(someone_else_s)
    not_this_round_s = _a_tester_changing_the_product(artifact_root, target, content)
    if not_this_round_s is not None:
        raise RepositoryToolError(not_this_round_s)

    # One project directory per run, pinned the first time code is written and
    # honoured by every stage afterwards. Without this each stage derived its own
    # name and the same application was built three times over.
    relative_parts = target.relative_to(artifact_root).parts
    misplaced = _code_in_the_documents_directory(artifact_root, relative_parts)
    if misplaced is not None:
        raise RepositoryToolError(misplaced)
    stranded = _tests_outside_the_project(artifact_root, relative_parts)
    if stranded is not None:
        raise RepositoryToolError(stranded)
    if not by_the_workflow:
        returning = _the_response_it_should_be_returning(relative_parts)
        if returning is not None:
            raise RepositoryToolError(returning)
        # By content as well as by name: the name is whatever the agent invents,
        # and `final_response.json` and `docs/summary.json` each cost a run.
        returning = _the_response_written_under_another_name(relative_parts, content)
        if returning is not None:
            raise RepositoryToolError(returning)
        owned = _a_workflow_document(relative_parts)
        if owned is not None:
            raise RepositoryToolError(owned)
        # And the other 334: a document `docs/` was never going to hold.
        # See `app.analysis.document_manifest`.
        intruding = _document_manifest.why_it_does_not_belong(relative_parts)
        if intruding:
            raise RepositoryToolError(intruding)
    scattered = _scaffolding_at_the_workspace_root(artifact_root, relative_parts)
    if scattered is not None:
        raise RepositoryToolError(scattered)
    if len(relative_parts) == 1 and _is_project_manifest(relative_parts[0]):
        pinned_here = pinned_project_directory(artifact_root)
        if pinned_here:
            raise RepositoryToolError(
                f"Refusing to write '{relative_path}': this is a project manifest and "
                f"this run's project is '{pinned_here}'. Write it to "
                f"'{pinned_here}/{relative_parts[0]}' instead. A manifest at the "
                "workspace root creates a second project, and the two then disagree "
                "about which dependency versions and test configuration apply."
            )
    if len(relative_parts) > 2 and relative_parts[0] == relative_parts[1]:
        # The project directory inside itself. Never a place anything belongs:
        # it is what a path looks like when it is given relative to the
        # workspace to something already running in the project. One run's test
        # read `simple-to-do-list-app/simple-to-do-list-app/index.html`, failed
        # with ENOENT, and the fix stage wrote a second copy of the page there
        # and a test asserting the copy exists.
        pinned_inside = pinned_project_directory(artifact_root)
        if pinned_inside and pinned_inside == relative_parts[0]:
            real = "/".join(relative_parts[1:])
            raise RepositoryToolError(
                f"Refusing to write '{relative_path}': that is the project directory "
                f"'{pinned_inside}/' inside itself, and nothing belongs there. The "
                f"file is '{real}'. If a test or a command looks for the doubled "
                "path, it is building a path relative to the workspace while "
                f"running inside '{pinned_inside}/' - fix the path it builds, "
                "do not make a second copy of the file to satisfy it."
            )
    if len(relative_parts) > 1 and _is_project_directory(relative_parts[0]):
        wanted_directory = relative_parts[0]
        pinned = pinned_project_directory(artifact_root)
        if pinned and pinned != wanted_directory:
            raise RepositoryToolError(
                f"Refusing to write '{relative_path}': this run's project directory is "
                f"'{pinned}', pinned when the first code was written. Write into "
                f"'{pinned}/' instead. Building the same application in a second "
                "directory leaves neither copy finished."
            )
        # NOT pinned here. Every check below can still reject this write, and a
        # rejected write must not pin anything: the pin is permanent and every
        # later path is measured against it.
        #
        # Observed on one run: the technical lead wrote a 1-byte file named
        # `med2`, then a specialist wrote `med2/app/__init__.py`. That pinned
        # `med2` and *then* failed, because `med2` was a file and not a
        # directory. The specialist removed the file, created `med2-app`, and
        # every write into it was refused for not being `med2` - as were
        # `med2-app-1` and `med2-application`. The run could not name any
        # directory it was allowed to use.
        pin_after_writing = wanted_directory if not pinned else None
    else:
        pin_after_writing = None

    forked = _forks_existing_directory(artifact_root, target)
    if forked is not None:
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': the directory '{forked.name}' already "
            f"exists and differs only in spelling. Write into '{forked.name}/' instead - "
            "two copies of one project means neither gets finished."
        )

    superseded = _supersedes_existing(target)
    if superseded is not None:
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': "
            f"'{superseded.name}' already exists and this would be a second copy of it. "
            "Update that file in place instead. Two versions of the same document "
            "disagree with each other, and a reviewer reads both."
        )

    # Before anything else about shape: content carrying the model's own turn
    # delimiters is not a document with a formatting problem, it is a
    # transcript that escaped.
    _refuse_control_tokens(relative_path, content)
    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = ""
        a_diff = _a_diff_that_parses(relative_path, content, existing, editing=False)
        if a_diff is not None:
            raise RepositoryToolError(a_diff)
    # Before refusing the shape: content that is broken only because its
    # escapes were written twice is a transcription fault, and the repairs for
    # it already exist on the edit path. See
    # `_content_a_model_escaped_twice` - the repair is applied only when the
    # content is invalid as sent and valid after, so nothing legitimate moves.
    repaired = _content_a_model_escaped_twice(relative_path, content)
    escape_note = ""
    if repaired is not None:
        content, escape_note = repaired
    content = _json_with_its_commas_put_right(target, relative_path, content)
    escape_note = " ".join(part for part in (escape_note, _what_was_put_right(target)) if part)
    try:
        _refuse_if_broken(relative_path, content)
    except RepositoryToolError:
        if not _sent_again_past_a_grammar(relative_path, content):
            raise
    _refuse_if_node_cannot_parse(target, relative_path, content)
    _refuse_a_hand_built_dom_again(relative_path, content, target)
    _refuse_rewriting_the_platform(
        relative_path, content, target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    )
    if target.is_file():
        try:
            _refuse_to_switch_a_suite_off(
                relative_path, target.read_text(encoding="utf-8"), content
            )
        except (OSError, UnicodeDecodeError):
            pass
    _refuse_a_blind_overwrite_of_another_stage_s_file(root, target, relative_path, content)
    # Before the write, because it compares against the file being replaced. The
    # note it returns is reported with the others once the write has landed.
    dropped_note = _a_rewrite_that_drops_what_the_file_defines(
        root, target, relative_path, content
    )

    if target.name == "package.json":
        _refuse_a_script_path_that_repeats_its_own_directory(target, content)
        _refuse_a_test_script_that_strands_suites(target, content)

    forked = _the_same_module_already_here(target, content)
    if forked is not None:
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': '{forked.name}' already holds "
            "this module, and this would be a second copy of it under another "
            "extension. Every later fix would land in one of them and the tests "
            "would import whichever they import, so half the work would do "
            f"nothing. Edit '{forked.name}' instead - or, if you mean to change "
            f"the extension, `move_artifact` from '{forked.name}' to "
            f"'{target.name}' first."
        )

    if _is_json_document(content) and target.suffix.lower() in _PROSE_SUFFIXES:
        # Agents conflate "write the artifact" with "return the structured
        # response" and save the schema as the document. Observed live: the
        # architect wrote a good Markdown specification, then overwrote it twice
        # with a JSON dump of its own answer, leaving the run's headline artifact
        # unreadable. Refusing is what makes it recoverable - the model gets a
        # correction it can act on, instead of silently shipping the corruption.
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': the content is JSON, but this "
            "is a prose document that a person reads. Write Markdown - headings, "
            "prose, lists, tables. Your structured response is returned through "
            "the response schema and must never be saved as an artifact."
        )

    # One trailing newline, whatever the model sent, so that two writes of the
    # same document compare equal. See `_with_one_trailing_newline`.
    content = _with_one_trailing_newline(content)

    # A rewrite of byte-identical content is reported as such rather than done
    # silently. Models re-issue the same write to confirm it landed, and the old
    # result gave them no way to tell a first write from a repeat - so they
    # repeated it. Each repeat is a full model call *and* one approval gate, and
    # enough of them in a row trip WORKFLOW_MAX_GATES_PER_STAGE and fail the run.
    # Saying "unchanged" is the signal that lets the agent move on.
    # Under the same lock as `edit_approved_artifact`, so "is it already this
    # content?" and the write that follows cannot be split by a concurrent edit
    # to the same file.
    with _MUTATION_LOCK:
        unchanged = False
        if target.is_file():
            try:
                unchanged = target.read_text(encoding="utf-8") == content
            except (OSError, UnicodeDecodeError):
                unchanged = False

        if not unchanged:
            # `exist_ok=True` tolerates an existing *directory* and nothing else.
            # When a plain file already occupies the path - `todo-app` created by
            # a stray `touch` or a write with no extension - this raises
            # FileExistsError, and on one run that escaped as an unhandled
            # exception and killed the stage. Every other failure in this module
            # is a RepositoryToolError the agent can read and act on; this one
            # should be too, and it has to say what is actually in the way.
            blocker = _file_blocking_directory(artifact_root, target)
            if blocker is not None:
                raise RepositoryToolError(
                    f"Cannot write '{relative_path}': '{blocker}' already exists as a "
                    "file, so it cannot also be a directory. Delete or rename that file, "
                    "or write to a different path."
                )
            # A path that is already a directory. `write_text` raises
            # `IsADirectoryError`, which reached the model as
            # "[Errno 21] Is a directory: '/app/data/workspaces/...'" -
            # an errno and a host path, naming neither the problem nor the fix.
            # One run's `specialist_ui_ux_1` wrote to `docs/` and got
            # exactly that. Every other failure in this module is a sentence
            # the agent can act on; this one should be too.
            if target.is_dir():
                inside = sorted(
                    child.name for child in target.iterdir() if child.is_file()
                )[:6]
                examples = f" It already holds: {', '.join(inside)}." if inside else ""
                raise RepositoryToolError(
                    f"Cannot write '{relative_path}': that is a directory, not a "
                    f"file.{examples} Give the file name you want inside it - "
                    f"'{relative_path.rstrip('/')}/something.md' - or write "
                    "somewhere else."
                )
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            except OSError as exc:
                logger.error("Failed to write artifact to %s: %s", target, exc)
                raise RepositoryToolError(
                    f"Could not write artifact to {relative_path}: {exc}"
                ) from exc

        # The write landed, so this directory is real and is the project.
        if pin_after_writing is not None:
            _pin_project_directory(artifact_root, pin_after_writing)

    # What the stage has seen of this file is now what it wrote. Recorded for
    # writes and not only reads because the stale-edit case measured on one
    # run began with a write: the stage wrote package.json, npm rewrote
    # it, and the stage then edited against its own text. See
    # `app.tools.seen_content`.
    try:
        from app.tools.seen_content import record_state, remember

        remember(relative_path, content)
        record_state(relative_path, content)
    except Exception:  # noqa: BLE001 - a bookkeeping miss must not fail a write
        logger.debug("Could not record the written content of %s", relative_path, exc_info=True)

    result = {
        "path": str(target.relative_to(root)),
        "summary": content[:80] + ("..." if len(content) > 80 else ""),
        # The file's length, returned with every write because a brief with a
        # size limit makes it the number the stage needs after every edit, and
        # without it the only way to get it is another tool call.
        #
        # Measured live on 2026-09-21. `brief_low.md` says "Maximum 500 lines of
        # code"; `test_round_0` checked, found 611, and raised it as the run's
        # only defect - every one of the 48 unit and end-to-end tests passed.
        # `defect_fix_1_0` then spent twenty `wc -l` calls compressing the files,
        # one after each edit, because a write said nothing about how long the
        # result was. The work was real; the round trips were not.
        "lines": _line_count(content),
    }
    if unchanged:
        result["status"] = "unchanged"
        result["detail"] = (
            "This file already contained exactly this content, so nothing was "
            "rewritten. The artifact is saved. Do not write it again; continue "
            "with your response."
        )
    else:
        result["status"] = "written"
        _remember_who_wrote_it(root, str(target.relative_to(root)))
    notes = [
        # First, because it explains why what landed differs from what was
        # sent. A silent repair teaches the model nothing and it escapes the
        # next file the same way.
        escape_note,
        # A note by now: whatever is refused was refused before the write.
        _structural_note(relative_path, content, refuse=False),
        _discovery_note(relative_path, content, target),
        _import_note(root, target, content),
        _nearly_a_workflow_document(relative_parts),
        _unrunnable_script_note(relative_path),
        _the_module_type_this_declares_breaks_files_here(target, content),
        _the_module_type_here_rejects_this_file(target, content),
        _the_page_and_this_module_disagree_on_how_it_loads(root, target, content),
        dropped_note,
        _budget_note(root, str(target.relative_to(root))).strip(),
    ]
    joined = " ".join(n for n in notes if n)
    if joined:
        result["note"] = joined
    return result




def looks_like_a_test(relative_path: str) -> bool:
    """Whether a path is a test file, by the conventions test runners use.

    Kept beside the delete tool rather than imported from `app.analysis`, which
    sits above this layer. `test_the_two_definitions_of_a_test_agree` pins them
    together so they cannot drift.
    """
    from app.analysis.file_kinds import is_test

    return is_test(relative_path)


_ANOTHER_STAGE_S_TEST = (
    "'{shown}' is a test that {stage} wrote, and tests are part of what this run "
    "delivers - the reviewer reads them as the evidence the product works. It "
    "stays where the test runner finds it. If one of its assertions is wrong, "
    "correct that assertion in place; if the product is wrong, fix the product. "
    "Asking to delete it, or to move it to a name the runner does not collect, "
    "will be refused the same way."
)


def _this_stage_created(root: Path, shown: str) -> bool:
    """Whether the stage running now created this file, so may delete it outright.

    A test is delivered evidence once another stage can rely on it; a file
    this stage wrote and is replacing is its own work in progress. One run's
    fix stage wrote `tests/main.test.js`, rewrote the suite in another file,
    and asked eleven times to delete the first: refused as a delivered test,
    it moved it to `main.test.js.bak` - still a test's name - and was refused
    again until the repeat guard took the tool. False when either stage is
    unknown, so outside a run nothing changes.
    """
    try:
        from app.analysis import project_memory
        from app.observability.transcript import _stage_from_config

        created_by = project_memory.who_created(root, shown)
        running = _stage_from_config("")
    except Exception:  # noqa: BLE001 - unknown is not this stage
        return False
    return bool(created_by and running and created_by == running)


def _another_stage_s_test(root: Path, shown: str) -> str:
    """The stage that created this test, when it is not the stage running now.

    The delete refusal offers a way out - rename, then delete - for a probe a
    stage wrote for itself. One run's `specialist_testing_2` took it for a
    100-line suite `specialist_backend_1` had written: one assertion failed, so
    it wrote a replacement file and moved the original to
    `app.e2e.spec.js.bak`, leaving it in the product and out of the suite.

    "" when the file is not a test, when this stage created it, or when either
    stage is unknown - outside a run, or for a file no tool wrote - so those
    cases keep the behaviour they had.
    """
    if not looks_like_a_test(shown):
        return ""
    try:
        from app.analysis import project_memory
        from app.analysis.file_kinds import is_scratch
        from app.observability.transcript import _stage_from_config

        if is_scratch(shown):
            # Named to be thrown away, so nobody's suite: the sweep between
            # stages removes it without asking. One fix stage left a
            # `tmp_test.js`; the next stage asked to delete it four times, was
            # told each time it was another stage's test, and lost the tool.
            return ""

        created_by = project_memory.who_created(root, shown)
        running = _stage_from_config("")
        if running and _the_plan_gave_it_to(root, shown) == running:
            # The plan's word outranks who happened to create it. One run's
            # work order listed `tests/app.test.js`, a file an earlier stage
            # had left as a four-line placeholder; the stage the plan gave it
            # to was told twice that it was another stage's test.
            return ""
    except Exception:  # noqa: BLE001 - a guard that cannot decide lets the call through
        return ""
    if not created_by or not running or created_by == running:
        return ""
    return created_by


def _the_plan_gave_it_to(root: Path, shown: str) -> str:
    """The stage whose work order lists this file in the current milestone, or ""."""
    try:
        table = json.loads((root / WORK_ORDER_FILES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(table.get(shown) or "") if isinstance(table, dict) else ""


def _somewhere_this_rule_will_let_go_of(shown: str, root: Path | None = None) -> str:
    """A path for the same file that `looks_like_a_test` will not protect.

    The escape offered by the delete refusal has to actually work. It used to
    be built by taking `.test.` out of the filename, which is right for
    `debug.test.mjs` and useless for anything inside a `tests/` directory -
    `looks_like_a_test` matches the directory too, so the renamed file was
    protected exactly as before.

    One run walked straight into it: `specialist_ui_ux_0` wrote
    `simple-to-do-list-app/tests/ui_test.js` as a probe, was refused the
    delete, followed the instructions, moved it to
    `simple-to-do-list-app/tests/ui_test.js.probe` - and stopped there, leaving
    a renamed corpse in the project. Had it tried the second step it would have
    been refused again, by the same rule, for the same reason.

    So the destination is checked against the rule that will judge it, and
    climbs out of the test directory when the rename alone is not enough.
    """
    candidate = shown.replace(".test.", ".").replace(".spec.", ".")
    # Never a name something already has. Taking `.test.` out of `data.test.js`
    # gives `data.js` - the module it tests, in the commonest layout there is -
    # and one run's stage was told to move its test there and then delete
    # "that". It did not; the advice was to overwrite the product and remove it.
    taken = root is not None and (root / candidate).exists()
    if candidate == shown or taken:
        candidate = f"{shown}.probe"
    if not looks_like_a_test(candidate):
        return candidate
    # The directory is what protects it. Put the file beside that directory,
    # keeping it inside the project.
    parts = candidate.split("/")
    kept = [
        part
        for part in parts[:-1]
        if part.lower() not in {"test", "tests", "__tests__", "e2e", "spec", "cypress"}
    ]
    name = parts[-1] if parts[-1].endswith(".probe") else f"{parts[-1]}.probe"
    climbed = "/".join([*kept, name])
    if root is not None and (root / climbed).exists():
        climbed = f"{climbed}.probe"
    return climbed


#: A sentence that asks for a file to go.
_A_REMOVAL = re.compile(r"\b(?:delete|remove|drop)\b", re.I)


def _the_plan_says_to_delete(root: Path, shown: str) -> bool:
    """Whether this milestone's plan names this exact file for removal.

    The test guards stop a stage throwing away tests on its own judgement. They
    also stopped one carrying out the plan: a milestone plan delegated
    "Delete `simple-to-do-list-app/app.test.js` (root-level Jest unit test -
    duplicate of tests/app.test.js)", the delete was refused twice, `rm` and
    `node -e` were refused, and the stage wrote a script that removed the files
    anyway - four failed calls, and the guard bypassed regardless.

    Only the full workspace-relative path in a sentence that asks for removal
    counts: a basename is ambiguous (`tests/app.test.js` ends with `app.test.js`
    too), and a plan that merely mentions a file is not asking for it to go.
    """
    try:
        plan = (root / "docs" / "milestone_plan.md").read_text(encoding="utf-8")
    except OSError:
        return False
    path = shown.strip().lstrip("/")
    if "/" not in path:
        return False
    for sentence in re.split(r"(?<=[.;:])\s+|\n", plan):
        if path in sentence and _A_REMOVAL.search(sentence):
            index = sentence.find(path)
            before = sentence[index - 1] if index > 0 else " "
            if before not in "/._-" and not before.isalnum():
                return True
    return False


def _is_a_probe_with_a_test_s_name(target: Path) -> bool:
    """Whether a file named like a test holds no test at all, so is clutter.

    Reached only for a file this stage created or nobody recorded: another
    stage's is refused before this. See `test_discovery.holds_no_test`. A file
    that cannot be read is treated as a test - the safe side for a delete.
    """
    try:
        from app.analysis.test_discovery import holds_no_test

        return target.is_file() and holds_no_test(target.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - when in doubt it is a test, and stays
        return False


#: Directories a throwaway is never looked for in: installed or generated
#: content, and the places a project keeps scripts on purpose.
_NOT_SWEPT = frozenset({"tools", "scripts", "bin", "test-results", "playwright-report"})

#: The largest file read when checking whether a throwaway is still referred to.
_MOST_BYTES_READ_FOR_A_REFERENCE = 400_000


def clear_the_throwaways_left_behind(repo_root: str | Path) -> list[str]:
    """Delete the debugging scripts finished stages left in the project.

    A stage that cannot see why a test fails writes a small script, runs it and
    learns something. It is told to delete it and often does not: measured over
    one day, every run that reached a second fix stage carried them into its
    test rounds - `tmp_test.js`, `tmp_simulate.js`, `debug_run.js`, twenty in
    one project - where they count against the product's size, are read by the
    reviewer as part of it, and are picked up by a runner when the name fits.
    A finding that asks for them to be deleted costs a stage; this does not.

    Narrow, because it deletes. Only inside the pinned project; only a name
    that says throwaway (`file_kinds.is_scratch`); only a file a stage of this
    run created, so nothing a seeded codebase arrived with is touched; and
    only when no other file there mentions it by name - a script something
    still runs or imports is not finished with. Returns what was removed.
    Never raises.
    """
    removed: list[str] = []
    try:
        from app.analysis import project_memory
        from app.analysis.file_kinds import is_scratch

        root = _normalize_repo_root(repo_root)
        pinned = pinned_project_directory(root)
        if not pinned:
            return removed
        project = root / pinned
        everything = [
            path for path in project.rglob("*")
            if path.is_file()
            and not any(
                part in IGNORED_DIRECTORIES or part in _NOT_SWEPT or part == "node_modules"
                for part in path.relative_to(project).parts[:-1]
            )
        ]
        unrun = set(_tests_no_suite_runs(root, project, everything))
        candidates = [path for path in everything if is_scratch(path.name) or path in unrun]
        if not candidates:
            return removed
        kept_text: list[str] = []
        for path in everything:
            if path in candidates:
                continue
            try:
                if path.stat().st_size <= _MOST_BYTES_READ_FOR_A_REFERENCE:
                    kept_text.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
        for path in candidates:
            shown = path.relative_to(root).as_posix()
            if not project_memory.who_created(root, shown):
                continue
            if any(path.name in text for text in kept_text):
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed.append(shown)
    except Exception:  # noqa: BLE001 - tidying must never fail the stage after it
        return removed
    return removed


def _tests_no_suite_runs(root: Path, project: Path, files: list[Path]) -> list[Path]:
    """Test-named files outside every directory the project's suites run, in a pack-built project.

    A stack pack says where its suites look - `tests/` for the unit runner,
    `acceptance/` for the acceptance runner - so a `run_test.js` or
    `test_import.js` at the top of the project is run by neither: a probe
    named like a test. One run delivered three of them with the product.
    Without a pack nothing says where tests run, and nothing is listed.
    """
    try:
        from app.analysis.file_kinds import classify_file
        from app.stacks import contract

        found = contract.the_pack(root)
    except Exception:  # noqa: BLE001
        return []
    if found is None:
        return []
    pack = found[0]
    homes = tuple(f"{d.strip('/')}/" for d in (pack.unit_dir, pack.acceptance_dir) if d)
    unrun = []
    for path in files:
        relative = path.relative_to(project).as_posix()
        if classify_file(relative) != "test" or relative.startswith(homes):
            continue
        if contract.owned_by_the_harness(root, path.relative_to(root).as_posix()):
            continue
        unrun.append(path)
    return unrun


def _is_the_project_s_own_manifest(root: Path, target: Path) -> bool:
    """Whether `target` is a package manifest at the top of the pinned project.

    Only there. A second manifest left at the workspace root, or in a
    directory beside the project, is the duplicate a cleanup is right to
    remove.
    """
    if target.name not in PACKAGE_MANIFESTS or not target.is_file():
        return False
    pinned = pinned_project_directory(root)
    return bool(pinned) and target.parent == root / pinned


def delete_approved_artifact(repo_root: str | Path, relative_path: str) -> dict[str, str]:
    """Delete one file the agent created inside the workspace.

    Why this exists:
        Agents are told scratch files do not belong in the deliverable, and
        until now had no way to act on that. On one run the UI specialist
        needed to remove one temporary `.mjs` probe. With no delete tool it
        wrote a second `.mjs` that unlinked the first - which was itself a
        scratch file it then wanted gone. Fifty approval gates and nine
        generations of `_selfdestruct.mjs`, `_finalclean.mjs`,
        `_cleanup_selfdestruct2.mjs` later the stage ended with more litter
        than it started with, because a Node script cannot unlink itself while
        it is running. One tool call ends that regress.

    Safety model:
        The same envelope as `write_approved_artifact`: the path is resolved
        the way the model means it, confined to the workspace root, and the
        call stops at the same approval interrupt. Files only - a directory
        would delete work in bulk and no legitimate cleanup needs it. Secret
        paths are refused, matching the read side: an agent that cannot see
        `.env` must not be able to remove it either.

    Errors:
        RepositoryToolError if the repo root is invalid, the path escapes it,
        the target is missing, is a directory, or looks like credentials.
    """
    root = _normalize_repo_root(repo_root)
    candidate = _repo_relative_path(root, relative_path)
    if not str(candidate).strip():
        raise RepositoryToolError("Give the path of the file to delete.")

    target = _assert_within_repo(root, root / candidate)
    locked = _the_harness_s_own_or_the_locked_suite(root, target)
    if locked is not None:
        raise RepositoryToolError(locked)
    shown = target.relative_to(root).as_posix()

    if is_secret_path(target):
        raise RepositoryToolError(
            f"'{shown}' looks like credential material and cannot be deleted."
        )
    # The pin is the only thing every stage shares about where code lives, and
    # it looks exactly like the dotfile clutter an agent tidying the workspace
    # root would remove. Losing it does not fail loudly; it makes the next
    # stage build the application a second time in a second directory, which is
    # the failure the pin was added to prevent (one run, three copies).
    if target.name == PROJECT_MARKER:
        raise RepositoryToolError(
            f"'{shown}' records which directory this project lives in and is not "
            "clutter. Leave it alone; every later stage reads it."
        )
    # A test is evidence, not clutter. Measured on one run: the test round
    # wrote four suites, ran them - 27 assertions passing against the real
    # application - and then deleted three of them as "temporary helper
    # scripts", leaving only the one suite that tested a copy of the code.
    # The delete tool was added to end a cleanup loop; without this it also
    # hands an agent a way to throw away the only proof the product works.
    owned = _a_workflow_document(tuple(target.relative_to(root).parts))
    if owned is not None:
        raise RepositoryToolError(
            f"Refusing to delete '{shown}': the workflow writes this file and "
            "rewrites it whole every time the stage that produces it runs. "
            "Removing it only makes it missing until then, and every stage that "
            "reads it in between finds nothing."
        )
    not_its_own = _not_this_stage_s_to_take(root, target, done="deleted")
    if not_its_own is not None:
        raise RepositoryToolError(not_its_own)

    planned = _the_plan_says_to_delete(root, shown)
    if not planned and _is_the_project_s_own_manifest(root, target):
        # Deleting it is not a way to replace it. Measured on one run: a test
        # round had an edit of `package.json` refused as invalid JSON, deleted
        # the file, had two whole-file writes refused for a path in the test
        # script, and returned saying it could not finish - leaving a project
        # with no manifest, so the next `npm test` could resolve nothing.
        raise RepositoryToolError(
            f"Refusing to delete '{shown}': it is this project's manifest, and "
            "every command that installs, runs or tests the project reads it. "
            "Deleting it does not clear the way for a new one - a write that is "
            "refused afterwards leaves the project with none. Change it in place: "
            "read it, then `edit_artifact` the part that is wrong, or "
            "`write_artifact` the whole file once you have read it."
        )
    written_by = "" if planned else _another_stage_s_test(root, shown)
    if written_by:
        raise RepositoryToolError(_ANOTHER_STAGE_S_TEST.format(shown=shown, stage=written_by))
    if (
        looks_like_a_test(shown)
        and not planned
        and not _is_a_probe_with_a_test_s_name(target)
        and not _this_stage_created(root, shown)
    ):
        # The refusal has to name the way out, or an agent that genuinely wrote
        # a throwaway probe has nowhere to go. One run's
        # `specialist_testing_1` wrote `todo-app/debug.test.mjs`, ran it, then
        # asked to delete it five times in a row - refused every time - until
        # the repeat guard stopped the stage and FAILED THE RUN. The old text
        # said "give it a name that is not a test name", which reads as advice
        # for next time and not as something to do with the file in hand.
        #
        # The two steps below are verified: `move_artifact` accepts a test name
        # as its source, and `delete_artifact` accepts the renamed file.
        suggestion = _somewhere_this_rule_will_let_go_of(shown, root)
        raise RepositoryToolError(
            f"'{shown}' is a test, and tests are part of what this run delivers - "
            "the reviewer reads them as the evidence the product works. Leave it. "
            "If it is genuinely a throwaway probe and not a test, rename it out of "
            f"the way first: `move_artifact` from '{shown}' to '{suggestion}', then "
            "`delete_artifact` on that. Asking to delete this path again will be "
            "refused the same way."
        )
    if target.is_dir():
        raise RepositoryToolError(
            f"'{shown}' is a directory. This tool deletes one file at a time; "
            "name the file you want removed."
        )
    if not target.exists():
        # The same memo the read, the edit and the move consult. A stage
        # clearing up the debugging scripts it wrote loses track of which it
        # has already removed, and "run `ls`" sends it to look for an answer it
        # already has. Measured on one run: twelve failed deletes across
        # two stages, ten of them on a path that same stage had just deleted.
        if _this_stage_already_deleted(shown):
            raise RepositoryToolError(
                f"'{shown}' is not there because this stage already deleted it. "
                "That is done; nothing more is needed for this file."
            )
        raise RepositoryToolError(
            f"'{shown}' does not exist - there is nothing to delete. "
            "Run `ls` to see what is actually there."
        )

    target.unlink()
    try:
        from app.tools.seen_content import record_deletion

        record_deletion(shown)
    except Exception:  # noqa: BLE001 - never fail a delete over a memo
        logger.debug("Could not record the deletion of %s", shown, exc_info=True)
    return {"deleted": shown, "status": "deleted"}


def move_approved_artifact(
    repo_root: str | Path, relative_path: str, destination: str
) -> dict[str, str]:
    """Move or rename one file inside the workspace.

    Why this exists:
        The other four operations compose into every file task except this one.
        Without it, an agent that put a file in the wrong place must rewrite the
        whole thing at the new path and delete the old - two gated calls, and
        the rewrite is a fresh generation of content that was already correct,
        so a long document can come back shorter or subtly different. That is
        the same failure `_supersedes_existing` exists to catch, arrived at from
        the other direction.

    Safety model:
        Both ends are resolved the way the model means them and confined to the
        workspace, so this cannot be used to read a file out or write one in.
        The destination must not already exist - an overwrite here would be a
        silent delete of whatever was there, and `write_artifact` is the tool
        for replacing a file you mean to replace. Secrets and the project pin
        are refused at both ends for the reasons `delete_approved_artifact`
        gives.

    Errors:
        RepositoryToolError if either path escapes the workspace, the source is
        missing or a directory, the destination exists, or either end is
        credential material or the project pin.
    """
    root = _normalize_repo_root(repo_root)

    source = _assert_within_repo(root, root / _repo_relative_path(root, relative_path))
    target = _assert_within_repo(root, root / _repo_relative_path(root, destination))
    from_shown = source.relative_to(root).as_posix()
    to_shown = target.relative_to(root).as_posix()
    for end in (source, target):
        locked = _the_harness_s_own_or_the_locked_suite(root, end)
        if locked is not None:
            raise RepositoryToolError(locked)

    # A move is how an agent gets round the write refusal: one run moved
    # `docs/architecture_review.md` to `docs/old_architecture_review.md`, which
    # left the canonical path vacant, and then wrote
    # `docs/architecture_review_new.md` - which `_supersedes_existing` allowed,
    # because the file it would have superseded was no longer there. The
    # workflow's own document was simply gone, and every stage that read it in
    # between found nothing.
    for path, shown in ((source, from_shown), (target, to_shown)):
        owned = _a_workflow_document(tuple(path.relative_to(root).parts))
        if owned is not None:
            raise RepositoryToolError(
                f"Refusing to move '{from_shown}' to '{to_shown}': "
                f"'{shown}' is written by the workflow, from the structured "
                "response of the stage that produces it. Moving it leaves that "
                "document missing until the stage runs again, and a renamed copy "
                "beside it is read by nobody. If what it says is wrong, put that "
                "in `blockers`, `risks` or `decisions` - those reach the workflow."
            )

    for path, shown in ((source, from_shown), (target, to_shown)):
        if is_secret_path(path):
            raise RepositoryToolError(
                f"'{shown}' looks like credential material and cannot be moved."
            )
        if path.name == PROJECT_MARKER:
            raise RepositoryToolError(
                f"'{shown}' records which directory this project lives in. "
                "Moving it would point every later stage at the wrong place."
            )

    # A move is a delete and a write, and both of those are guarded for the
    # project's manifest. One run's stage was refused a `package.json` at the
    # workspace root four times, then moved the project's own manifest there:
    # the project had none, the root had a second project, and two stages
    # after it edited the wrong file.
    if (
        _is_the_project_s_own_manifest(root, source)
        and target.parent != source.parent
        and not _the_plan_says_to_delete(root, from_shown)
    ):
        raise RepositoryToolError(
            f"Refusing to move '{from_shown}': it is this project's manifest, and "
            "every command that installs, runs or tests the project reads it from "
            f"'{source.parent.relative_to(root).as_posix()}/'. Moved elsewhere, the "
            "project has none. Leave it where it is; if a command cannot find it, "
            "run that command with the project as its working directory."
        )
    to_parts = target.relative_to(root).parts
    if len(to_parts) == 1 and _is_project_manifest(to_parts[0]):
        pinned_here = pinned_project_directory(root)
        if pinned_here:
            raise RepositoryToolError(
                f"Refusing to move a file to '{to_shown}': that is a project manifest "
                f"at the workspace root, and this run's project is '{pinned_here}'. "
                "A manifest there creates a second project, and the two then "
                "disagree about which dependencies and test configuration apply. "
                f"It belongs at '{pinned_here}/{to_parts[0]}'."
            )
    if source == target:
        raise RepositoryToolError(
            f"'{from_shown}' is already where you are asking to put it."
        )
    # Moving another work order's file away takes it from its owner as surely
    # as deleting it; moving a file onto one of its paths writes it. Product
    # code is judged at the source only: renaming a testing stage's own probe
    # to a name no runner collects, so that it can be deleted, is the way out
    # `delete_approved_artifact` offers, and that name looks like code.
    for path, product_code in ((source, True), (target, False)):
        not_its_own = _not_this_stage_s_to_take(
            root, path, done="moved", product_code=product_code
        )
        if not_its_own is not None:
            raise RepositoryToolError(not_its_own)
    # A move to a name no test runner collects is a delete by another route.
    # See `_another_stage_s_test`. Judged by the name's suffixes, not by
    # `looks_like_a_test`: the run that did it moved the suite to
    # `test/app.e2e.spec.js.bak`, which is still inside a test directory and
    # which no runner loads.
    written_by = _another_stage_s_test(root, from_shown)
    if written_by and PurePosixPath(to_shown).suffixes != PurePosixPath(from_shown).suffixes:
        raise RepositoryToolError(_ANOTHER_STAGE_S_TEST.format(shown=from_shown, stage=written_by))
    if not source.exists():
        # The same memo the read and the edit consult. A stage renaming a set
        # of files one at a time loses track of which it has already done, and
        # "run `ls`" costs it a call to learn something it did itself.
        moved_to = _where_this_stage_put_it(from_shown)
        if moved_to is not None:
            if moved_to == to_shown:
                raise RepositoryToolError(
                    f"'{from_shown}' does not exist because this stage already "
                    f"moved it to '{to_shown}'. That move is done; nothing to do."
                )
            raise RepositoryToolError(
                f"'{from_shown}' does not exist because this stage moved it to "
                f"'{moved_to}'. Move that instead, if it still needs moving."
            )
        raise RepositoryToolError(
            f"'{from_shown}' does not exist. Run `ls` to see what is actually there."
        )
    if source.is_dir():
        raise RepositoryToolError(
            f"'{from_shown}' is a directory. This tool moves one file at a time."
        )
    if target.exists():
        raise RepositoryToolError(
            f"'{to_shown}' already exists. Moving onto it would delete it without "
            "showing anyone what was lost; use `write_artifact` if you mean to "
            "replace it, or choose another name."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    # So a later read or edit at the old name can be told where it went rather
    # than only that nothing is there - see `where_this_stage_moved_it`.
    try:
        from app.tools.seen_content import record_move

        record_move(from_shown, to_shown)
    except Exception:  # noqa: BLE001 - never fail a move over a memo
        pass
    try:
        from app.analysis import project_memory

        project_memory.record_move(root, from_shown, to_shown)
    except Exception:  # noqa: BLE001 - never fail a move over a memo
        pass
    return {"moved": from_shown, "to": to_shown, "status": "moved"}


def run_approved_validation(
    repo_root: str | Path, command: list[str], working_directory: str | None = None
) -> dict[str, object]:
    """Run one validation command inside the sandbox.

    Purpose:
        Let a specialist prove a change works, without granting a general shell.

    Safety model:
        This used to run the command directly on the host, allowlisting only
        `argv[0]`. That was not a boundary: `python -c "..."` and `pytest`
        (which executes any `conftest.py` in the tree the agent just wrote) are
        both arbitrary code execution. Validation now goes through the same
        contained executor as every other command, which rejects those argument
        forms and runs with no network, bounded resources and dropped
        capabilities.

    Errors:
        RepositoryToolError if the repo root is invalid or the command is empty.
        A rejected or failed command is returned as data so the agent can adjust.
    """
    from app.tools.sandbox import SandboxExecutor

    root = _normalize_repo_root(repo_root)
    if not command:
        raise RepositoryToolError("Validation command cannot be empty.")
    if isinstance(command, str):
        raise RepositoryToolError(
            'Validation commands must be a list, e.g. ["pytest", "-q"]. A string would need a shell.'
        )

    # Validation runs where the project is, not where the workspace starts.
    # The pin already decides where code is written; a test command that
    # ignored it ran the workspace root's manifest instead - on one run
    # that was npm's `npm init -y` default, whose test script is
    # `echo "Error: no test specified" && exit 1`. Every test round reported a
    # failure that had nothing to do with the tests.
    run_in = working_directory or pinned_project_directory(root)

    result = SandboxExecutor.execute(
        command=command,
        repo_root=str(root),
        role_name="testing_specialist",
        category="test",
        working_directory=run_in,
    )
    from app.tools.sandbox import _as_exit_code

    reply = {
        "command": list(command),
        "working_directory": run_in or ".",
        # `_as_exit_code` rather than `int(...)`: a refused command carries an
        # `error` and no exit code, and a non-numeric one would raise here
        # instead of being reported as data the agent can act on.
        "returncode": (
            -1 if result.get("returncode") is None else (_as_exit_code(result["returncode"]) or 0)
        ),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", "") or result.get("error", ""),
    }
    # `SandboxExecutor.execute` attaches the notices that stop a command being
    # re-run for nothing - "this exact command has already failed 3 times",
    # "already passed and nothing has been written since", the doubled working
    # directory correction. This function built a fresh dict and dropped them,
    # so every one of them reached `run_terminal_command` and none reached
    # `run_validation` - the tool the testing specialists are told to use.
    #
    # Measured on one run's `specialist_testing_1`: 53 model calls, `node
    # --test` run six times through this path and three through the other. Only
    # the three could be told anything.
    if result.get("note"):
        reply["note"] = result["note"]
    return reply


def _git_value(root: Path, args: list[str]) -> str | None:
    """Run one read-only `git` query, returning None if git cannot answer.

    A workflow run must not die because the workspace is not a git repository,
    git is not installed, or the repo has no commits yet. Those are all normal
    situations for a fresh project.

    None means "git could not answer", which is deliberately distinct from an
    empty string meaning "git answered, and the answer is empty". Collapsing
    the two would report an unknown repository as clean - precisely the false
    stability signal that `RepositoryContext.status` warns against.
    """
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def build_repository_context(repo_root: str | Path, allow_subdirectories: bool = True):
    """Describe the repository so a workflow run has grounded project context.

    Purpose:
        Produce the `RepositoryContext` every role agent receives: which
        repository they may inspect, which revision it is at, and which files
        define its dependency surface and entry points.

    Inputs:
        repo_root: repository root to describe.

    Returns:
        An `app.state.RepositoryContext`.

    Errors:
        RepositoryToolError if the repository root is invalid. Git failures are
        not errors; they degrade to "unknown" values (see `_git_value`).

    Safety model:
        Read-only. It runs only `git` queries that report state, never any
        command that mutates the working tree, index, or remotes.
    """
    # Imported here rather than at module scope to keep this tools module
    # importable by anything that only needs the raw file helpers.
    from app.state import RepositoryContext

    root = _normalize_repo_root(repo_root)

    branch = _git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    commit = _git_value(root, ["rev-parse", "HEAD"]) or "unknown"

    porcelain = _git_value(root, ["status", "--porcelain"])
    if porcelain is None:
        status = "unknown (not a git repository, or git is unavailable)"
    elif porcelain == "":
        status = "clean"
    else:
        status = f"dirty ({len(porcelain.splitlines())} changed path(s))"

    known_dependency_files = ["pyproject.toml", "package.json", "requirements.txt", "pom.xml", "go.mod"]
    dependency_files = [name for name in known_dependency_files if (root / name).is_file()]

    known_entry_points = ["src/app/main.py", "main.py", "app.py", "manage.py", "src/index.ts", "src/main.py"]
    entry_points = [name for name in known_entry_points if (root / name).is_file()]

    return RepositoryContext(
        root_path=str(root),
        branch=branch,
        commit=commit,
        status=status,
        dependency_files=dependency_files,
        entry_points=entry_points,
        allow_subdirectories=allow_subdirectories,
    )


__all__ = [
    "RepositoryToolError",
    "build_repository_context",
    "list_repository_files",
    "read_text_file",
    "read_text_lines",
    "search_text",
    "read_dependency_metadata",
    "write_approved_artifact",
    "edit_approved_artifact",
    "delete_approved_artifact",
    "looks_like_a_test",
    "move_approved_artifact",
    "run_approved_validation",
]
