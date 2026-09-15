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
        raise RepositoryToolError(f"File does not exist within the repository: {relative_path}")
    if not target.is_file():
        raise RepositoryToolError(f"Requested path is not a file: {relative_path}")
    return target.read_text(encoding="utf-8")


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


_READ_LINE_NUMBER = re.compile(r"^\s*\d+\s{1,}")
"""The `NNN  ` prefix `read_file` puts in front of every line it returns."""


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

    first = next((line for line in wanted.splitlines() if line.strip()), "")
    if not first:
        return None

    lines = content.splitlines()
    if not lines:
        return None

    scores = [
        (difflib.SequenceMatcher(None, first.strip(), line.strip()).ratio(), index)
        for index, line in enumerate(lines)
    ]
    ratio, best = max(scores)
    # Below this the "closest" line shares a keyword and nothing else, and
    # quoting it would send the agent somewhere unrelated.
    if ratio < 0.6:
        return None

    start = max(0, best - _NEAR_MATCH_LINES)
    end = min(len(lines), best + _NEAR_MATCH_LINES + 1)
    quoted = []
    for index in range(start, end):
        marker = ">" if index == best else " "
        quoted.append(f"{marker} {index + 1:>4} | {lines[index]}")
    return "\n".join(quoted)


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
    root = _normalize_repo_root(repo_root)
    target = (root / _repo_relative_path(root, relative_path)).resolve()
    _assert_within_repo(root, target)

    if is_secret_path(target):
        raise RepositoryToolError(
            f"Refusing to edit '{relative_path}': the path matches a credential file pattern."
        )
    if not target.is_file():
        # When the missing file is a forked version of one that does exist, say
        # so here. The generic "use write_artifact to create it" sends the agent
        # to a write that `_supersedes_existing` then refuses, costing a model
        # call to learn something this message already knows.
        canonical = _supersedes_existing(target)
        if canonical is not None:
            raise RepositoryToolError(
                f"Cannot edit '{relative_path}': it does not exist. "
                f"Edit '{canonical.name}' instead - it is the current version of "
                "this document. Do not recreate the file you just tried to edit."
            )
        raise RepositoryToolError(
            f"Cannot edit '{relative_path}': it does not exist yet. "
            "Use write_artifact to create it."
        )
    if not find:
        raise RepositoryToolError(
            "The `find` text is empty. Give the exact passage to replace, or use "
            "write_artifact to replace the whole file."
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
            unescaped = _without_double_escaping(find)
            if unescaped is not None:
                attempts.append((
                    unescaped,
                    "Matched after collapsing doubled backslashes in your text. A "
                    "backslash needs escaping once in JSON, not twice.",
                ))
            unjsoned = _without_json_escaping(find)
            if unjsoned is not None:
                attempts.append((
                    unjsoned,
                    "Matched after reading your text as JSON escapes - your `find` "
                    "carried \\n and \\\" where the file has a real newline and a plain "
                    "quote. The tool call is already JSON; put the literal text in "
                    "`find`, not an escaped copy of it.",
                ))
            renumbered = _without_read_line_numbers(find)
            if renumbered is not None:
                attempts.append((
                    renumbered,
                    "Matched after removing the line numbers from your text. Those come "
                    "from `read_file`'s output and are not in the file - strip them before "
                    "editing.",
                ))
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
                    continue
                start, end = span
                target.write_text(original[:start] + replace + original[end:], encoding="utf-8")
                summary = replace[:80] + ("..." if len(replace) > 80 else "")
                return {
                    "path": str(target.relative_to(root)),
                    "status": "edited",
                    "summary": summary or "(passage removed)",
                    "detail": explanation,
                }

            if len(find.strip()) < 10:
                raise RepositoryToolError(
                    f"Could not find that text in '{relative_path}'. The text you gave is "
                    f"only {len(find)} characters, which rarely identifies one passage. "
                    "Give the whole line you want changed, copied from a read, and put the "
                    "change in `replace`."
                )

            nearest = _closest_passage(original, find)
            detail = (
                f"\n\nThe closest text in the file is (> marks the nearest line):\n{nearest}\n\n"
                "Copy the passage from there exactly, including its indentation."
                if nearest
                else " Read the section first and copy the passage from what you read."
            )
            raise RepositoryToolError(
                f"Could not find that text in '{relative_path}'. It must match exactly, "
                f"including whitespace and punctuation.{detail}"
            )
        if occurrences > 1:
            raise RepositoryToolError(
                f"That text appears {occurrences} times in '{relative_path}', so it is "
                "ambiguous which one to change. Include more surrounding text to make "
                "the passage unique."
            )

        target.write_text(original.replace(find, replace, 1), encoding="utf-8")
    summary = replace[:80] + ("..." if len(replace) > 80 else "")
    return {
        "path": str(target.relative_to(root)),
        "status": "edited",
        "summary": summary or "(passage removed)",
    }


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


def _code_in_the_documents_directory(relative_parts: tuple[str, ...]) -> str | None:
    """Why this file does not belong in `docs/`, or None if it does.

    `docs/` is what every reviewer reads as documentation, and what the
    workflow's own generated documents share. Code there is read as prose by
    one stage and imported by none.

    Measured on run-304add54: the testing specialist wrote `/docs/test_suite.js`
    and then edited it five times running, fighting JSDOM scope problems in a
    file that no test runner would ever collect - the project's runner looks in
    the project directory. The repeat guard stopped the stage; the file was in
    the wrong place from the first write.
    """
    if len(relative_parts) < 2 or relative_parts[0] != "docs":
        return None
    suffix = Path(relative_parts[-1]).suffix.lower()
    if suffix not in _CODE_SUFFIXES:
        return None
    return (
        f"Refusing to write '{'/'.join(relative_parts)}': `docs/` is for documents "
        "a person reads, and a reviewer reads everything there as documentation. "
        f"A {suffix} file belongs in the project directory, where the test runner "
        "and the build will actually find it."
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


def write_approved_artifact(repo_root: str | Path, relative_path: str, content: str) -> dict[str, str]:
    """Write a generated artifact only inside the repository root or its subfolders.

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
    misplaced = _code_in_the_documents_directory(relative_parts)
    if misplaced is not None:
        raise RepositoryToolError(misplaced)
    stranded = _tests_outside_the_project(artifact_root, relative_parts)
    if stranded is not None:
        raise RepositoryToolError(stranded)
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
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_text(content, encoding="utf-8")
            except OSError as exc:
                logger.error("Failed to write artifact to %s: %s", target, exc)
                raise RepositoryToolError(
                    f"Could not write artifact to {relative_path}: {exc}"
                ) from exc

        # The write landed, so this directory is real and is the project.
        if pin_after_writing is not None:
            _pin_project_directory(artifact_root, pin_after_writing)

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
    return result


_LOOKS_LIKE_A_TEST = re.compile(
    r"(^|/)(__tests__|tests?|e2e)/"
    r"|\.(test|spec)\.([cm]?[jt]s|[jt]sx)$"
    r"|(^|/)test[-_][^/]*\.([cm]?[jt]s|[jt]sx)$"
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.py$"
)


def looks_like_a_test(relative_path: str) -> bool:
    """Whether a path is a test file, by the conventions test runners use.

    Kept beside the delete tool rather than imported from `app.analysis`, which
    sits above this layer. `test_the_two_definitions_of_a_test_agree` pins them
    together so they cannot drift.
    """
    return bool(_LOOKS_LIKE_A_TEST.search(relative_path))


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
    if looks_like_a_test(shown):
        raise RepositoryToolError(
            f"'{shown}' is a test, and tests are part of what this run delivers - "
            "the reviewer reads them as the evidence the product works. Leave it. "
            "If it is genuinely a throwaway probe rather than a test, give it a "
            "name that is not a test name, so nothing later mistakes it for one."
        )
    if target.is_dir():
        raise RepositoryToolError(
            f"'{shown}' is a directory. This tool deletes one file at a time; "
            "name the file you want removed."
        )
    if not target.exists():
        raise RepositoryToolError(
            f"'{shown}' does not exist - there is nothing to delete. "
            "Run `ls` to see what is actually there."
        )

    target.unlink()
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
    return {
        "command": list(command),
        "working_directory": run_in or ".",
        "returncode": int(result["returncode"]) if "returncode" in result else -1,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", "") or result.get("error", ""),
    }


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
