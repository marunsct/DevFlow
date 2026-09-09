"""Server-owned workspace allocation.

A run needs a directory the agents may read and write. That directory must never
come from the request: it is used as the repository root for every tool and as
the bind-mount source for the sandbox, so a caller who chooses it chooses what
the agents can reach. The previous ``artifact_directory`` field accepted any
existing path, including ``/``.

Workspaces are therefore allocated here, under one operator-configured root, and
the request may only choose a label within it.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

_LABEL_SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


class WorkspaceError(ValueError):
    """The requested workspace could not be allocated."""


def workspace_root() -> Path:
    """The single directory under which every run workspace is created."""
    configured = os.environ.get("WORKFLOW_WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(os.environ.get("DATA_DIR", ".")) / "workspaces").expanduser().resolve()


def safe_label(label: str | None) -> str:
    """Reduce a caller-supplied label to a single safe path segment."""
    if not label:
        return "workspace"
    cleaned = _LABEL_SAFE.sub("-", Path(label).name).strip("-")
    return cleaned[:48] or "workspace"


def allocate_workspace(run_id: str, label: str | None = None) -> Path:
    """Create and return this run's workspace directory.

    The path is derived from the server-side run id, so two runs can never share
    a workspace and no caller can steer one at an existing directory.
    """
    root = workspace_root()
    root.mkdir(parents=True, exist_ok=True)

    directory = root / f"{safe_label(label)}-{run_id}"
    resolved = directory.resolve()

    # Belt and braces: even though every component is server-derived, confirm the
    # result is genuinely inside the root before creating anything.
    if root != resolved and root not in resolved.parents:
        raise WorkspaceError(f"Refusing to allocate a workspace outside {root}")

    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_within_workspace(workspace: str | Path, relative_path: str) -> Path:
    """Resolve a caller-supplied relative path inside a workspace, or refuse.

    This is the containment check the artifact download endpoint was missing.
    Absolute paths and ``..`` traversal are both rejected after resolution, so
    symlinks cannot be used to step outside either.
    """
    root = Path(workspace).expanduser().resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise WorkspaceError("Absolute paths are not accepted.")
    resolved = (root / candidate).resolve()
    if root != resolved and root not in resolved.parents:
        raise WorkspaceError(f"Path escapes the workspace: {relative_path}")
    return resolved


def delete_workspace(workspace: str | Path) -> None:
    """Remove a run's workspace, refusing anything outside the configured root."""
    root = workspace_root()
    target = Path(workspace).expanduser().resolve()
    if root not in target.parents:
        raise WorkspaceError(f"Refusing to delete {target}: outside {root}")
    shutil.rmtree(target, ignore_errors=True)


__all__ = [
    "WorkspaceError",
    "allocate_workspace",
    "delete_workspace",
    "resolve_within_workspace",
    "safe_label",
    "workspace_root",
]
