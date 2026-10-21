"""A harness-owned code graph of the project (plan CG.1), and the slices of it requests carry (CG.2, CG.3).

Fixers and builders found a file's neighbours by reading: who imports it, what
it imports, which tests reach it. The harness reads all of that already -
imports per language family (`analysis.reachability`), definitions by the same
patterns, the acceptance suite's tests and the criteria their names carry.
This puts it in one index, `.project-graph.json` beside `.project-memory.json`,
computed from the files as they are - never model-written - and gives a request
the one-hop neighbourhood of its files at most `MOST_CHARACTERS`.

Two switches, because they are two measurements: `PROJECT_GRAPH_FIXES` (a fix
request gets its defect's files' neighbourhood, CG.2) and
`PROJECT_GRAPH_BUILDERS` (a work order gets its files' slice, CG.3).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Characters of a neighbourhood a request carries, at most.
MOST_CHARACTERS = 1_500
GRAPH_FILE = ".project-graph.json"
_SKIPPED = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", "test-results", ".git"}


def fixes_enabled() -> bool:
    return is_on("PROJECT_GRAPH_FIXES", False)


def builders_enabled() -> bool:
    return is_on("PROJECT_GRAPH_BUILDERS", False)


def build(root: str | Path) -> dict[str, dict[str, list[str]]]:
    """{file: {imports, imported_by, defines, criteria}} for the project's source files, workspace-relative. Never raises."""
    from app.analysis.reachability import FAMILIES, _defined, family_of

    root = Path(root).resolve()
    graph: dict[str, dict[str, list[str]]] = {}
    try:
        from app.tools.repository import pinned_project_directory

        project = root / (pinned_project_directory(root) or "")
        for directory, subdirectories, files in os.walk(project):
            subdirectories[:] = [d for d in subdirectories if d not in _SKIPPED and not d.startswith(".")]
            for name in files:
                path = Path(directory) / name
                family = FAMILIES.get(family_of(name))
                if family is None:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                relative = path.relative_to(root).as_posix()
                imports = sorted(p.resolve().relative_to(root).as_posix() for p in family.imports(path, text, project, {})
                                 if p.resolve().is_relative_to(root))
                graph[relative] = {"imports": imports, "imported_by": [], "defines": sorted(_defined(text, family)),
                                   "criteria": []}
        for relative, node in graph.items():
            for target in node["imports"]:
                if target in graph:
                    graph[target]["imported_by"].append(relative)
        _criteria_of_the_tests(root, graph)
        try:
            (root / GRAPH_FILE).write_text(json.dumps(graph, indent=1), encoding="utf-8")
        except OSError:
            pass
    except Exception:  # noqa: BLE001 - no graph is no neighbourhood
        logger.debug("Could not build the project graph", exc_info=True)
    return graph


def _criteria_of_the_tests(root: Path, graph: dict[str, dict[str, list[str]]]) -> None:
    """Each acceptance test file's criteria, from the ids its tests' names carry; and the files it imports."""
    try:
        from app.acceptance import suite
        from app.acceptance.junit import tags_in

        for where, name in suite.declared_tests(root):
            if where in graph:
                graph[where]["criteria"] = sorted({*graph[where]["criteria"], *(t for t in tags_in(name) if t.startswith("AC-"))})
    except Exception:  # noqa: BLE001
        pass


def neighbourhood(root: str | Path, files: Iterable[str], heading: str) -> str:
    """The one-hop neighbourhood of `files`: what each defines and imports, what imports it and which tests reach it; "" when none."""
    graph = build(root)
    lines: list[str] = []
    for relative in dict.fromkeys(str(f).strip().lstrip("./") for f in files if str(f).strip()):
        node = graph.get(relative)
        if node is None:
            continue
        tests = [other for other, n in graph.items() if relative in n["imports"] and n["criteria"]]
        parts = []
        if node["defines"]:
            parts.append("defines " + ", ".join(node["defines"][:8]))
        if node["imports"]:
            parts.append("imports " + ", ".join(f"`{p}`" for p in node["imports"][:6]))
        if node["imported_by"]:
            parts.append("imported by " + ", ".join(f"`{p}`" for p in node["imported_by"][:6]))
        if tests:
            criteria = sorted({c for t in tests for c in graph[t]["criteria"]})
            parts.append("tested by " + ", ".join(f"`{t}`" for t in tests[:3]) + (f" ({', '.join(criteria[:8])})" if criteria else ""))
        if parts:
            lines.append(f"- `{relative}`: " + "; ".join(parts))
    if not lines:
        return ""
    text = heading + "\n" + "\n".join(lines)
    return text[:MOST_CHARACTERS].rstrip() + "\n"


FIX_HEADING = "--- The files this defect touches, and their neighbours (from the harness's code graph) ---"
BUILD_HEADING = "--- Your files and their neighbours (from the harness's code graph) ---"


def _appended(request: dict[str, Any], text: str) -> dict[str, Any]:
    if text and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
        request["messages"][-1]["content"] += "\n\n" + text
    return request


def with_the_neighbourhood(request: dict[str, Any], root: str | Path, files: Iterable[str]) -> dict[str, Any]:
    """A fix request with its defect's files' neighbourhood (CG.2); as it was when off. Never raises."""
    if not fixes_enabled():
        return request
    try:
        return _appended(request, neighbourhood(root, files, FIX_HEADING))
    except Exception:  # noqa: BLE001
        return request


def with_the_slice(request: dict[str, Any], root: str | Path, files: Iterable[str]) -> dict[str, Any]:
    """A work order's request with its files' slice (CG.3); as it was when off. Never raises."""
    if not builders_enabled():
        return request
    try:
        return _appended(request, neighbourhood(root, files, BUILD_HEADING))
    except Exception:  # noqa: BLE001
        return request


class _Switch:
    """One switch of this module, for `provenance.SWITCHES`."""

    def __init__(self, enabled: Any) -> None:
        self.enabled = enabled
        self.ON_BY_DEFAULT = False


fixes_switch = _Switch(fixes_enabled)
builders_switch = _Switch(builders_enabled)

__all__ = ["BUILD_HEADING", "FIX_HEADING", "GRAPH_FILE", "build", "builders_enabled", "fixes_enabled",
           "neighbourhood", "with_the_neighbourhood", "with_the_slice"]
