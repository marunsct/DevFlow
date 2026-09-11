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
    if not candidate.is_absolute():
        return candidate
    try:
        return candidate.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return candidate.relative_to(candidate.anchor)


IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".next", ".nuxt",
    "dist", "build", ".terraform", ".gradle", "target", ".langchain", "site-packages",
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
            raise RepositoryToolError(
                f"Could not find that text in '{relative_path}'. It must match exactly, "
                "including whitespace and punctuation. Read the section first and copy "
                "the passage from what you read."
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
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_text(content, encoding="utf-8")
            except OSError as exc:
                logger.error("Failed to write artifact to %s: %s", target, exc)
                raise RepositoryToolError(
                    f"Could not write artifact to {relative_path}: {exc}"
                ) from exc

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


def run_approved_validation(repo_root: str | Path, command: list[str]) -> dict[str, object]:
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

    result = SandboxExecutor.execute(
        command=command,
        repo_root=str(root),
        role_name="testing_specialist",
        category="test",
    )
    return {
        "command": list(command),
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
    "run_approved_validation",
]
