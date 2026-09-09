"""Safe repository-access helpers for workflow agents.

A beginner-friendly explanation: these tools intentionally do not expose a full
shell. Instead, the workflow gives agents a few narrow, auditable operations:
list files, read a selected file, search text, inspect dependency metadata, write
only within the approved artifact directory, and run a small allowlist of safe
validation commands. That reduces accidental secrets exposure and prevents a role
agent from wandering outside the project boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import logging
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
    target = (root / relative_path).resolve()
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
    cleaned_path = Path(relative_path).expanduser()
    if cleaned_path.is_absolute():
        cleaned_path = cleaned_path.relative_to(cleaned_path.anchor)
    target = (artifact_root / cleaned_path).resolve()
    if artifact_root not in target.parents and target != artifact_root:
        raise RepositoryToolError(
            f"Artifact path is outside the repository root: {relative_path}"
        )

    if is_secret_path(target):
        raise RepositoryToolError(
            f"Refusing to write '{relative_path}': the path matches a credential file pattern."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write artifact to %s: %s", target, exc)
        raise RepositoryToolError(f"Could not write artifact to {relative_path}: {exc}") from exc
    return {
        "path": str(target.relative_to(root)),
        "summary": content[:80] + ("..." if len(content) > 80 else ""),
    }


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
    "search_text",
    "read_dependency_metadata",
    "write_approved_artifact",
    "run_approved_validation",
]
