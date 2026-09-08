"""Shared, safe tool wrappers for role agents.

Role agents should never receive raw filesystem or shell access, and they
should never choose their own repository root. This module wraps the narrow
functions in `app.tools.repository` as LangChain tools with the repository
root bound by closure, so a model cannot pass an arbitrary path and explore
directories outside the intended project. Every future role agent should
build its tools from here instead of redefining its own wrappers.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool

from app.tools.repository import (
    RepositoryToolError,
    list_repository_files,
    read_dependency_metadata,
    read_text_file,
    run_approved_validation,
    search_text,
    write_approved_artifact,
)


def build_repository_read_tools(repo_root: str, allow_subdirectories: bool = True) -> list[BaseTool]:
    """Return read-only repository tools bound to a fixed repository root.

    Binding `repo_root` in a closure (instead of accepting it as a tool
    argument) keeps every role agent scoped to one repository even if the
    model tries to request a different root.
    """

    @tool
    def inspect_repository() -> dict[str, Any]:
        """Return repository files, dependency metadata, and workflow-relevant matches.

        Use this to understand project structure and dependencies before
        drafting product or architecture conclusions.
        """
        return {
            "files": list_repository_files(repo_root, allow_subdirectories=allow_subdirectories),
            "dependency_metadata": read_dependency_metadata(repo_root),
            "relevant_matches": search_text(
                repo_root,
                "Product Manager|LangGraph|Deep Agents|workflow|product",
                max_matches=10,
            ),
        }

    @tool
    def read_repository_file(relative_path: str) -> str | dict[str, str]:
        """Read one text file from the repository by its path relative to the repo root.

        Returns `{"error": "..."}` instead of raising when the path escapes the
        repository or does not exist, so a wrong guess from the model becomes a
        recoverable tool result instead of crashing the whole agent run.
        """
        try:
            return read_text_file(repo_root, relative_path)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return [inspect_repository, read_repository_file]


def build_artifact_write_tool(repo_root: str) -> BaseTool:
    """Return the single controlled artifact-write tool bound to a repository root.

    This is the only mutation path role agents get: writes are restricted to
    the repository root and its subfolders by `write_approved_artifact`
    itself, regardless of what path the model requests.
    """

    @tool
    def write_artifact(relative_path: str, content: str) -> dict[str, str]:
        """Write a generated artifact inside the repository root or its subfolders.

        Returns `{"error": "..."}` instead of raising when the target path
        escapes the repository root, so the model can retry with a valid
        path instead of crashing the whole agent run.
        """
        try:
            return write_approved_artifact(repo_root, relative_path, content)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return write_artifact


def build_validation_tool(repo_root: str) -> BaseTool:
    """Return a tool that runs one allowlisted validation command bound to a repo root.

    This is deliberately narrow: `run_approved_validation` already restricts
    the executable to a small allowlist (python, pytest, compileall), so a
    specialist can prove their change works without a general-purpose shell.
    """

    @tool
    def run_validation(command: list[str]) -> dict[str, object]:
        """Run one allowlisted validation command, e.g. ["pytest", "tests/", "-q"].

        Returns `{"error": "..."}` instead of raising when the command is not
        on the allowlist, so the specialist can pick an approved command
        instead of crashing the whole agent run.
        """
        try:
            return run_approved_validation(repo_root, command)
        except RepositoryToolError as exc:
            return {"error": str(exc)}

    return run_validation


def build_terminal_command_tool(repo_root: str) -> BaseTool:
    """Return a tool that runs arbitrary shell commands in the repository root.
    
    This is necessary for agents to scaffold projects, install dependencies,
    and perform other project-level initialization tasks.
    """

    @tool
    def run_terminal_command(command: str) -> dict[str, str]:
        """Execute a shell command in the repository root directory.
        
        Use this tool to initialize projects (e.g. npx create-react-app, npx @nestjs/cli new),
        install dependencies, or run build scripts.
        """
        import subprocess
        import re

        # Strict allowlist for terminal commands
        allowed_patterns = [
            r"^npx\s+.*",
            r"^npm\s+(install|run|test|init).*",
            r"^yarn\s+(add|install|run|test|init|create).*",
            r"^pnpm\s+(add|install|run|test|init|create).*",
            r"^python3?\s+-m\s+(venv|pip|pytest).*",
            r"^pip\s+install.*",
            r"^pytest\s+.*",
            r"^django-admin\s+startproject.*",
            r"^git\s+(init|add|commit|status).*",
            r"^ls\s+.*",
            r"^echo\s+.*",
        ]

        is_allowed = any(re.match(pattern, command.strip()) for pattern in allowed_patterns)
        
        if not is_allowed:
            return {"error": f"Command '{command}' is not allowed for security reasons. Allowed commands must match specific patterns (e.g., npm/npx, python -m, pytest)."}

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=120
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": str(result.returncode)
            }
        except Exception as exc:
            return {"error": str(exc)}

    return run_terminal_command


__all__ = ["build_artifact_write_tool", "build_repository_read_tools", "build_validation_tool", "build_terminal_command_tool"]
