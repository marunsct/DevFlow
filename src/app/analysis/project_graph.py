"""A harness-owned code graph of the project (plan CG.1), and the slices of it requests carry (CG.2, CG.3).

Fixers and builders found a file's neighbours by reading: who imports it, what
it imports, which tests reach it. The harness reads all of that already -
imports per language family (`analysis.reachability`), definitions by the same
patterns, the acceptance suite's tests and the criteria their names carry.
This puts it in one index, `.harness/project-graph.json`,
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
#: Under `.harness/`, which no commit, digest or review diff carries: at the
#: workspace's top it was committed and led the code reviewer's capped diff.
GRAPH_FILE = ".harness/project-graph.json"
_SKIPPED = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", "test-results", ".git",
            "vendor", "target", "coverage", "playwright-report", "htmlcov"}


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
            (root / GRAPH_FILE).parent.mkdir(parents=True, exist_ok=True)
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
    for relative in dict.fromkeys(str(f).strip().removeprefix("./").lstrip("/") for f in files if str(f).strip()):
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


def tool_enabled() -> bool:
    """CG.4: the `code_graph` tool is offered to builders and fixers (`CODE_GRAPH_TOOL`)."""
    return is_on("CODE_GRAPH_TOOL", False)


def where_is(root: str | Path, name: str) -> list[str]:
    """The files that define `name` - exactly, else by a part of the name - at most 8."""
    graph, wanted = build(root), str(name).strip()
    if not wanted:
        return []
    exact = [f for f, n in graph.items() if wanted in n["defines"]]
    return (exact or [f for f, n in graph.items() if any(wanted.lower() in d.lower() for d in n["defines"])])[:8]


def who_uses(root: str | Path, path: str) -> dict[str, list[str]]:
    """What imports `path`, which acceptance tests reach it and their criteria; {} for a file the graph does not hold."""
    graph, relative = build(root), str(path).strip().removeprefix("./").lstrip("/")
    node = graph.get(relative)
    if node is None:
        return {}
    tests = [other for other, n in graph.items() if relative in n["imports"] and n["criteria"]]
    return {"imported_by": node["imported_by"][:12], "tests": tests[:6],
            "criteria": sorted({c for t in tests for c in graph[t]["criteria"]})[:12], "defines": node["defines"][:20]}


def build_tool(repo_root: str | Path) -> Any:
    """The read-only `code_graph` tool (plan CG.4), answered from the harness's graph of the project."""
    from langchain_core.tools import tool

    @tool
    def code_graph(where_is_name: str = "", who_uses_path: str = "") -> dict[str, Any]:
        """Ask the harness's code graph instead of searching: where a name is defined, or what uses a file.

        Args:
            where_is_name: a function, class or type; answers the files that define it.
            who_uses_path: a workspace-relative file; answers what imports it, what it defines, and the
                acceptance tests and criteria that reach it.

        Give one of the two. Returns `{"defined_in": [...]}` or `{"imported_by", "defines", "tests", "criteria"}`.
        """
        if where_is_name.strip():
            found = where_is(repo_root, where_is_name)
            if not found:
                # Not "defined nowhere": the graph reads only some languages, and
                # an empty answer read as absent invited a second definition.
                return {"defined_in": [], "note": f"The code graph does not show `{where_is_name}`: it reads "
                        "only some languages and kinds of definition. Search the files before you define it."}
            return {"defined_in": found}
        if who_uses_path.strip():
            return who_uses(repo_root, who_uses_path) or {"error": f"The code graph holds no file `{who_uses_path}`."}
        return {"error": "Give `where_is_name` or `who_uses_path`."}

    return code_graph


class _Switch:
    """One switch of this module, for `provenance.SWITCHES`."""

    def __init__(self, enabled: Any) -> None:
        self.enabled = enabled
        self.ON_BY_DEFAULT = False


fixes_switch = _Switch(fixes_enabled)
builders_switch = _Switch(builders_enabled)
tool_switch = _Switch(tool_enabled)

__all__ = ["BUILD_HEADING", "FIX_HEADING", "GRAPH_FILE", "build", "build_tool", "builders_enabled", "fixes_enabled",
           "neighbourhood", "tool_enabled", "where_is", "who_uses", "with_the_neighbourhood", "with_the_slice"]
