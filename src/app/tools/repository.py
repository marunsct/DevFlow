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
from pathlib import Path

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
    # nested inside the workspace it describes. Measured on run-2f252e4e, where
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
    # product: on run-61c5a5b6 one `npm install` left 26 `_cacache` blobs with
    # sha512 filenames, and a listing of the workspace was mostly those rather
    # than the application.
    ".agent-home",
})
"""Directories never descended into."""

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
            if path.is_file() and not is_secret_path(path):
                files.append(path)
        return files

    for dirpath, dirnames, filenames in os.walk(repo_root):
        # Pruning in place is what stops os.walk descending further.
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRECTORIES and not d.startswith(".cache"))
        current = Path(dirpath)
        for filename in sorted(filenames):
            candidate = current / filename
            if is_secret_path(candidate):
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
            + _where_that_name_actually_is(root, relative_path)
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

    `read_file` has had this since run-3f8e387d, where 56 of 72 failed reads
    named a file that was in the workspace under a different path. This is the
    other read tool, and it had none of it - the third piece of machinery
    `read_repository_file` turned out to be missing, after the repeat notice
    and the span tracking.

    Measured across run-499c771a, run-454adf22 and run-04576307: each one
    failed a `read_repository_file` of `README.md` at the workspace root while
    the project's README sat one directory down.
    """
    name = wanted.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if not name:
        return ""
    try:
        found = [
            candidate.relative_to(root).as_posix()
            for candidate in root.rglob(name)
            if candidate.is_file()
            and not any(part in IGNORED_DIRECTORIES for part in candidate.parts)
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

    Observed on run-0b55ad49 in three of four consecutive failed edits, against
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


def _without_double_escaping(wanted: str) -> str | None:
    """`wanted` with doubled backslashes collapsed, or None if there are none.

    A model writing a tool call in JSON has to escape a backslash, and one that
    is already thinking about escaping tends to escape it twice. The result is a
    `find` of `\\\\n` against a file holding `\\n` - three characters searched
    for where two exist.

    Observed on run-0b55ad49 fixing the very corruption this describes: a test
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
    # late. Measured on run-eb48de7a: `specialist_ui_ux_0` sent an 85-line
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

    Observed on run-95ca3f72 at 10:28: the agent read `todo-app/package.json`,
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
    run-0b55ad49 a stage was stopped as a loop for re-issuing the same edit; the
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

    Measured on run-499c771a's `specialist_testing_3`, four failed edits of
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
        # as easy to misremember as blank lines inside it: run-499c771a sent
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
    only move is to read again and guess again - measured on run-0b55ad49,
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
    # Measured on run-36eb1260: `specialist_backend_2` edited a five-line
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

    The third is what this is for. Run 1ae7671d's `test_round_1` was told five
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
    run-0deeb8bf's `defect_fix_2_0`, it does not. The model sent

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
    # every line after it look different. Measured on run d6297b2f,
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
                # and teaches nothing. Measured on run-519a9d8a's
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


def _already_applied(original: str, find: str, replace: str) -> str:
    """The message for an edit that has already been made, or "".

    Measured on run-0deeb8bf's `defect_fix_2_0`. At 14:15:33 it edited
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
    """
    if len(replace.strip()) < _REPLACE_LONG_ENOUGH_TO_RECOGNISE:
        # A short `replace` proves nothing by being present, and a deletion
        # (empty `replace`) has nothing to look for at all.
        return ""
    if replace not in original:
        return ""
    line = original[: original.index(replace)].count("\n") + 1
    return (
        f" The file already contains the text you asked to put there, at line "
        f"{line} - this edit has already been applied, which is why the text it "
        "replaced is gone. Nothing was changed just now and nothing needs to be. "
        "Read the file if you want to confirm it, then move on."
    )


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


def replace_approved_lines(
    repo_root: str | Path,
    relative_path: str,
    start_line: int,
    end_line: int,
    content: str,
    expect_start: str = "",
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
    """
    root, target = _guard_a_targeted_change(repo_root, relative_path, content)

    with _MUTATION_LOCK:
        original = target.read_text(encoding="utf-8")
        lines = original.splitlines(keepends=True)
        total = len(lines)

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

        if expect_start:
            actual_first = lines[start_line - 1]
            if expect_start.strip() != actual_first.strip():
                raise RepositoryToolError(
                    f"Line {start_line} of '{relative_path}' is not what you "
                    f"expected, so the numbering has moved since you read it.\n"
                    f"  you expected: {_clip(expect_start.strip())}\n"
                    f"  line {start_line} is:  {_clip(actual_first.strip())}\n"
                    "Read the file again and use the new line numbers. Nothing "
                    "was changed."
                )

        replaced = "".join(lines[start_line - 1:last])
        # Keep the file's own line ending on the replacement, so replacing the
        # last line of a file that ends with a newline does not silently drop it.
        body = content
        if body and not body.endswith("\n") and replaced.endswith("\n"):
            body += "\n"
        updated = "".join(lines[:start_line - 1]) + body + "".join(lines[last:])

        # Only when the edit is what breaks it. A file that arrived broken is
        # being repaired, and refusing every step that has not yet finished
        # the repair is the trap measured on run-eb48de7a - four consecutive
        # refusals at lines 22, 59, 83 and 72 of one file, the moving line
        # number showing the model was getting closer each time. See the same
        # rule in `_write_unless_it_changes_nothing`.
        if _what_is_structurally_wrong(target, relative_path, original) is None:
            _refuse_if_broken(relative_path, updated)
        _write_unless_it_changes_nothing(target, original, updated, relative_path)
        note = (
            f"Replaced lines {start_line}-{last} of {total}. "
            f"The file now has {len(updated.splitlines())} lines."
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
            # Measured on run-519a9d8a's `test_round_1`, which sent
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
                _write_unless_it_changes_nothing(
                    target,
                    original,
                    original[:start] + replace + original[end:],
                    relative_path,
                )
                return _edited(target, root, relative_path, replace, explanation, find)

            # Before anything else: the model may be re-sending an edit it
            # already made, in which case every other message here is a
            # distraction from the one fact that matters.
            done = _already_applied(original, find, replace)
            if done:
                raise RepositoryToolError(
                    f"Could not find that text in '{relative_path}'.{done}"
                )

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
                    "changed after you last read it - a command you ran (an installer, "
                    "a formatter, a generator) rewrote it. The passage you sent was "
                    "correct for the version you had. Read the file again and copy the "
                    "passage from what you read."
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
    it now says. Measured on run-a7150a6c's `specialist_testing_1`: five full
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

    That cost run-3ddd443f. At 12:52:03 `test_round_0` removed a passage
    through the forgiving path and got no structural note; the edit left a
    brace unclosed, and `node --test` then failed four times with
    "Unexpected end of input" before the next edit - through the exact path -
    finally reported it.

    Two success returns and a check on one of them is the "reached twelve of
    thirteen" mistake this codebase names in its own tests, and building the
    result in one place is what stops a third path from reopening it.
    """
    summary = replace[:80] + ("..." if len(replace) > 80 else "")
    result: dict[str, str] = {
        "path": str(target.relative_to(root)),
        "status": "edited",
        "summary": summary or "(passage removed)",
    }
    if detail:
        result["detail"] = detail
    written = target.read_text(encoding="utf-8")
    # So the next call is not a read of the whole file. See `_where_it_landed`.
    landed = _where_it_landed(written, replace)
    if landed:
        result["context"] = landed
    notes = [
        _what_is_still_wrong_after_a_repair(target, relative_path, written),
        _discovery_note(relative_path, written, target),
        _import_note(root, target, written),
        # From the path, not from a caller's variable: this is the edit path,
        # and it has no `relative_parts` of its own.
        _nearly_a_workflow_document(_repo_relative_path(root, relative_path).parts),
        _unrunnable_script_note(relative_path),
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


def _what_sits_around_each_match(text: str, find: str) -> str:
    """The line before and after each copy, so the agent can tell them apart.

    "Include a line from above or below one of them" is advice the agent cannot
    act on: it does not have the file in front of it, and the two copies are
    near-identical or it would not have collided with both. So show the lines
    that differ.

    Measured on run-d3965815, where the model wrote `app.test.mjs` with the
    same three-line block at lines 52 and 73, tried to edit it, and sent the
    byte-identical failing call again rather than guess. Six of that run's
    thirteen edit failures were this.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    start = 0
    while len(blocks) < _MAX_AMBIGUOUS_MATCHES_SHOWN:
        at = text.find(find, start)
        if at < 0:
            break
        first = text.count("\n", 0, at)
        last = first + find.rstrip("\n").count("\n")
        before = f"{first:>5} | {_clip(lines[first - 1])}" if first > 0 else "      | (start of file)"
        after = (
            f"{last + 2:>5} | {_clip(lines[last + 1])}"
            if last + 1 < len(lines)
            else "      | (end of file)"
        )
        blocks.append(
            f"  the copy at line {first + 1}:\n"
            f"  {before}\n"
            f"  {'':>5} | ... your passage ...\n"
            f"  {after}"
        )
        start = at + 1
    if not blocks:
        return ""
    return "\n\n" + "\n\n".join(blocks)


def _where_each_match_starts(text: str, find: str) -> str:
    """"line 7 and line 10", or "lines 7, 10 and 14".

    The old message said only "include more surrounding text to make the
    passage unique", which is advice rather than information: the agent cannot
    see where the copies are, so it guesses at more context and often collides
    with the other copy again.

    Measured on run-e37a2bd8: 7 of 24 `edit_artifact` failures were this, on a
    test file whose blocks the model had duplicated - exactly the case where
    knowing which lines differ is the whole problem.
    """
    lines: list[int] = []
    start = 0
    while True:
        at = text.find(find, start)
        if at < 0:
            break
        lines.append(text.count("\n", 0, at) + 1)
        start = at + 1
    if not lines:
        return "several places"
    if len(lines) == 1:
        return f"line {lines[0]}"
    listed = ", ".join(str(n) for n in lines[:-1])
    return f"lines {listed} and {lines[-1]}"


def _content_a_model_escaped_twice(relative_path: str, content: str) -> tuple[str, str] | None:
    """Content that only fails because its escapes were written twice, repaired.

    Measured live on run-eb48de7a at 03:37. `test_round_0` sent

        {"relative_path": "todo-app/package.json",
         "content": "{\\n  \"name\": \"todo-app\", ... }"}

    where every newline is the two characters backslash-n rather than a
    newline. The content is therefore `{\\n  "name": ...`, `json.loads` stops
    at column 2, and the write is refused - correctly, because a broken
    `package.json` breaks every module in its directory. The model sent the
    identical bytes three times and the stage made no progress.

    The repairs that fix this have existed since run-95ca3f72 and run-0b55ad49.
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


def _structural_note(relative_path: str, content: str, *, editing: bool = False) -> str:
    """Warn about a file that was just written broken, or refuse it.

    Python is parsed with `ast` and JSON with `json.loads`, which are the real
    grammars, so a failure is certain and worth refusing over. Brace-counting
    for the C family is a structure check rather than a parse - it cannot see a
    missing semicolon - so it warns and lets the write stand.

    Either way the agent hears it while it is still looking at the edit it just
    made. run-e37a2bd8 heard it two stages later, as "Syntax error in app.mjs
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
    if _refuses_a_broken_file(relative_path):
        raise RepositoryToolError(_refusal_for(relative_path, problem, editing=editing))
    return problem


def _refuses_a_broken_file(relative_path: str) -> bool:
    """Whether a failure for this file is certain enough to refuse over.

    Python and JSON have real grammars, so `ast.parse` and `json.loads` are
    proof. Brace counting for the C family is a structure check and warns
    instead - but `node --check` is a parse, so JavaScript is refused on that
    and warned on the rest. See `_javascript_parse_error`.
    """
    return relative_path.lower().endswith((".py", ".json"))


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

    run-454adf22 wrote `app.js` with a stray `try` and spent the whole of
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


def _refusal_for(relative_path: str, problem: str, *, editing: bool = False) -> str:
    """The refusal text for `problem`, in terms of the call that was made.

    Two things went wrong here, both measured on run 8d28ee3f.

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

    Measured on run-130deeef, where `simple-to-do-list-app/build.sh` was the
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
WORKFLOW_DOCUMENTS = frozenset({
    "architecture_review.md",
    "milestone_plan.md",
    "milestone_review.md",
    "product_intake.md",
    "security_review.md",
    "sprint_plan.md",
    "technical_specification.md",
    "technology_stack.md",
    "tools_and_models.md",
})


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

        d6297b2f  docs/structured_response.md    32 writes
        1ae7671d  todo-list/structured_response.json   8
        a7150a6c  docs/structured_response.json        4
        0deeb8bf  final_response.json                  6   - fell through
        01f03ed9  docs/summary.json                    5   - fell through

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

    Run d6297b2f died of exactly this: `defect_fix_1_0` requested
    `docs/structured_response.md` five times in a row, carrying
    `{"role":"Testing and Quality Engineering Specialist","output":{...}}` as
    its content, and the loop guard stopped the run. Twenty model calls in that
    run went into writing that file; run a7150a6c spent eight more on
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

    run-84e05d4b's `specialist_documentation_2` spent six consecutive calls
    and ninety seconds failing to edit `docs/tools_and_models.md` - a document
    rendered from the `tools_models` stage's structured response. Succeeding
    would have been no better than failing.

    The workflow's own `_record_document` passes `by_the_workflow=True` and is
    unaffected; that is the only writer of these paths that should exist.

    The message names the channel that does work, because the first version did
    not and the model found the worst way round it: refused the specification,
    `specialist_ui_ux_0` wrote `docs/specification_update.md` instead - in
    run-04576307 and again in run-01f03ed9, written once each and never read by
    anything. A specialist's `decisions`, `risks` and `blockers` are read by the
    workflow; a sibling document is read by nobody.

    Measured on run-84e05d4b: a specialist wrote
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
    run-454adf22 produced: `docs/tech_specification.md`, 470 bytes, beside the
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
    file, and that is the right first response. It is not enough. Run
    9bd3a091 delivered that note 27 times across ten stages and still ended
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
        # file it would have matched as stranded (run 5f4cdd55).
        if any(character in command for character in "*?["):
            return
        # Only positional arguments name suites. `--config=jest.config.js`
        # names a configuration file, and jest with no pattern searches the
        # project (run fff9bf89).
        named = {
            token
            for token in shlex.split(command)
            if not token.startswith("-") and _NAMES_A_SCRIPT_FILE.fullmatch(token)
        }
        if not named:
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

    Run 1ae7671d is what that costs. Its script ran three named files while the
    project held six, `npm test` passed on the curated subset, the real
    failures survived every green run, and the sprint exhausted all three
    remediation attempts. Said at the write, the fix is one edit to the
    manifest.
    """
    if target is None:
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


def _discovery_note(relative_path: str, content: str, target: Path | None = None) -> str:
    """Warn about a test file the project's runner will not collect, or "".

    A note rather than a refusal: the name is legal and the content is fine.
    What is wrong is invisible - an uncollected test does not error, it is
    simply absent, and every later stage reads a green run that never
    executed it. See `app.analysis.test_discovery`.
    """
    from app.analysis.test_discovery import (
        a_call_the_signature_does_not_accept,
        a_dom_built_by_hand,
        a_name_this_test_defines_instead_of_importing,
        a_suite_calling_a_global_node_does_not_define,
        a_suite_that_only_checks_things_exist,
        a_test_that_asserts_nothing,
        a_test_that_needs_a_dom,
        assertions_called_on_the_test_module,
        tests_nothing_of_the_project,
        tests_the_runner_will_never_call,
        undiscoverable_test,
    )

    try:
        notes = [
            undiscoverable_test(relative_path, content),
            tests_nothing_of_the_project(relative_path, content),
            assertions_called_on_the_test_module(relative_path, content),
            a_test_that_asserts_nothing(relative_path, content),
            tests_the_runner_will_never_call(relative_path, content),
            a_suite_that_only_checks_things_exist(relative_path, content),
            a_dom_built_by_hand(relative_path, content),
            a_test_that_needs_a_dom(relative_path, content, target.parent if target else None),
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

    Measured live on run-eb48de7a. `specialist_testing_5` wrote
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
    and the stage that writes it is rarely the stage that wrote them. Run
    9bd3a091's `specialist_testing_3`, reaching for jest to get away from a
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

    Measured on run-130deeef's `specialist_backend_8`: it wrote `docs/blocker.md`
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
    through literally, which lands `\n` in the file and breaks it. Run
    8d28ee3f, `specialist_ui_ux_0`, sent this twice:

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


def _write_unless_it_changes_nothing(
    target: Path, original: str, updated: str, relative_path: str
) -> None:
    """Write the edit, or refuse an edit that would leave the file as it is.

    An edit whose `replace` is byte-identical to the text it replaces is a
    no-op, and reporting "edited" for it is a lie the agent cannot see through:
    it reads the file back, finds its change absent, concludes the edit failed,
    and sends the identical call again.

    That is what killed run-b61df271. Its `specialist_backend_3` made three
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
    if updated != original:
        _refuse_an_edit_that_goes_backwards_again(relative_path, updated)
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
            # Measured live on run-eb48de7a. `todo-app/main.js` had a
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

run-0b55ad49 built the same to-do application three times over - in
`simple-todo-list-app`, `simple_todo_list_app`, and `thehub` - because each
stage picked a name and nothing carried the first choice forward. None of the
three was ever finished.
"""

#: Files that define a Node/Python project. At the workspace root, once a
#: project directory is pinned, each of these creates a *second* project that
#: competes with it.
#:
#: run-0b55ad49 ended with two: `package.json` at the root declaring jest 30 and
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
    until now nothing enforced it. Measured on run-7b11cb67: the UI specialist
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
        # the same mistake: on run-7b11cb67 `index.html` sat at the workspace
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

    Measured on run-2b5def74, which completed with two test directories -
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

    Measured on run-304add54: the testing specialist wrote `/docs/test_suite.js`
    and then edited it five times running, fighting JSDOM scope problems in a
    file that no test runner would ever collect - the project's runner looks in
    the project directory. The repeat guard stopped the stage; the file was in
    the wrong place from the first write.

    Names the destination, not just the rule. A refusal that says only "not
    here" leaves an agent that has read the rule and cannot apply it: on
    run-2bfa5e6e the testing specialist was refused `docs/tests/playwright.config.js`,
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
    # itself. Measured on run-7b11cb67: the UI specialist wrote
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
    run-0b55ad49 built `simple-todo-list-app`; sprint 2 derived
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

    Measured on run-454adf22: `simple-to-do-list-app/app.js` (4,887 bytes) and
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

Measured on run-44653bd2, on North-Mini-Code-1.0. `Task.test.mjs` was written
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

    if is_secret_path(target):
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': the path matches a credential file pattern."
        )

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
        # Observed on run-64df2b20: the technical lead wrote a 1-byte file named
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
    # Before refusing the shape: content that is broken only because its
    # escapes were written twice is a transcription fault, and the repairs for
    # it already exist on the edit path. See
    # `_content_a_model_escaped_twice` - the repair is applied only when the
    # content is invalid as sent and valid after, so nothing legitimate moves.
    repaired = _content_a_model_escaped_twice(relative_path, content)
    escape_note = ""
    if repaired is not None:
        content, escape_note = repaired
    _refuse_if_broken(relative_path, content)
    _refuse_if_node_cannot_parse(target, relative_path, content)

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
            # FileExistsError, and on run-95ca3f72 that escaped as an unhandled
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
            # run-08acb1ee's `specialist_ui_ux_1` wrote to `docs/` and got
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
    # writes and not only reads because the stale-edit case measured on run
    # 8d28ee3f began with a write: the stage wrote package.json, npm rewrote
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
    notes = [
        # First, because it explains why what landed differs from what was
        # sent. A silent repair teaches the model nothing and it escapes the
        # next file the same way.
        escape_note,
        _structural_note(relative_path, content),
        _discovery_note(relative_path, content, target),
        _import_note(root, target, content),
        _nearly_a_workflow_document(relative_parts),
        _unrunnable_script_note(relative_path),
        _the_module_type_this_declares_breaks_files_here(target, content),
        _the_module_type_here_rejects_this_file(target, content),
        _the_page_and_this_module_disagree_on_how_it_loads(root, target, content),
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


def _somewhere_this_rule_will_let_go_of(shown: str) -> str:
    """A path for the same file that `looks_like_a_test` will not protect.

    The escape offered by the delete refusal has to actually work. It used to
    be built by taking `.test.` out of the filename, which is right for
    `debug.test.mjs` and useless for anything inside a `tests/` directory -
    `looks_like_a_test` matches the directory too, so the renamed file was
    protected exactly as before.

    run-84e05d4b walked straight into it: `specialist_ui_ux_0` wrote
    `simple-to-do-list-app/tests/ui_test.js` as a probe, was refused the
    delete, followed the instructions, moved it to
    `simple-to-do-list-app/tests/ui_test.js.probe` - and stopped there, leaving
    a renamed corpse in the project. Had it tried the second step it would have
    been refused again, by the same rule, for the same reason.

    So the destination is checked against the rule that will judge it, and
    climbs out of the test directory when the rename alone is not enough.
    """
    candidate = shown.replace(".test.", ".").replace(".spec.", ".")
    if candidate == shown:
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
    return "/".join([*kept, name])


def delete_approved_artifact(repo_root: str | Path, relative_path: str) -> dict[str, str]:
    """Delete one file the agent created inside the workspace.

    Why this exists:
        Agents are told scratch files do not belong in the deliverable, and
        until now had no way to act on that. On run-61c5a5b6 the UI specialist
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
    shown = target.relative_to(root).as_posix()

    if is_secret_path(target):
        raise RepositoryToolError(
            f"'{shown}' looks like credential material and cannot be deleted."
        )
    # The pin is the only thing every stage shares about where code lives, and
    # it looks exactly like the dotfile clutter an agent tidying the workspace
    # root would remove. Losing it does not fail loudly; it makes the next
    # stage build the application a second time in a second directory, which is
    # the failure the pin was added to prevent (run-0b55ad49, three copies).
    if target.name == PROJECT_MARKER:
        raise RepositoryToolError(
            f"'{shown}' records which directory this project lives in and is not "
            "clutter. Leave it alone; every later stage reads it."
        )
    # A test is evidence, not clutter. Measured on run-2b5def74: the test round
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

    if looks_like_a_test(shown):
        # The refusal has to name the way out, or an agent that genuinely wrote
        # a throwaway probe has nowhere to go. run-9ff00d5b's
        # `specialist_testing_1` wrote `todo-app/debug.test.mjs`, ran it, then
        # asked to delete it five times in a row - refused every time - until
        # the repeat guard stopped the stage and FAILED THE RUN. The old text
        # said "give it a name that is not a test name", which reads as advice
        # for next time and not as something to do with the file in hand.
        #
        # The two steps below are verified: `move_artifact` accepts a test name
        # as its source, and `delete_artifact` accepts the renamed file.
        suggestion = _somewhere_this_rule_will_let_go_of(shown)
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
        # already has. Measured on run 551640d3: twelve failed deletes across
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

    # A move is how an agent gets round the write refusal: run-01f03ed9 moved
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

    if source == target:
        raise RepositoryToolError(
            f"'{from_shown}' is already where you are asking to put it."
        )
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
    # ignored it ran the workspace root's manifest instead - on run-95ca3f72
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
    # Measured on run-84e05d4b's `specialist_testing_1`: 53 model calls, `node
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
