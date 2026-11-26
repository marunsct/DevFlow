"""The code graph answers inside the tools the model already calls (plan KG.6).

Behind `GRAPH_IN_SEARCH_ANSWERS`, off in code until measured.

The model never asks the graph: the `code_graph` tool was called 0 times in about 3,500 offers. It searches and reads
instead, and learns where a name is defined and who calls it by searching again. So the graph's answer goes where the
model already looks, never as a new tool:

- a `grep` whose pattern is a name the graph defines is answered first with where it is defined (file and lines) and
  which files use it, then the matches;
- a range read that opens on a definition adds one line: what calls it, by file and definition;
- a whole read past the room, answered by the file's outline (`READS_SIZED_TO_THE_ROOM`), gains what uses each
  definition from other files.

Only the graph's facts are said: a use is named only where one file is the one it can be (KG.3).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

from app.analysis import graph_lookups
from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "GRAPH_IN_SEARCH_ANSWERS"
#: `GRAPH_IN_SEARCH_ANSWERS` set to on or off overrides this.
ON_BY_DEFAULT = False
#: How each answer the graph adds begins; the switch-firing check reads it in the tool's result.
SAID = "The harness's code graph:"
#: What the admin page says this switch does.
explanation = ("A search for a name the project defines is answered first with where it is defined and which files "
               "use it; a range read that opens on a definition adds what calls it; a whole read answered by an "
               "outline adds what uses each definition. From the harness's code graph, no new tool.")
#: Files and callers named in one line, at most.
MOST_NAMED = 6
#: Definitions the outline's addition names, at most.
MOST_OUTLINED = 20
#: Lines past a range's first line a definition may open on and still be the one the range reads.
OPENS_WITHIN = 3

_A_NAME = re.compile(r"[A-Za-z_$][\w$]*")


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def _graph(root: str | Path) -> dict[str, Any]:
    from app.analysis.project_graph import build

    return build(root)


def _listed(items: list[str]) -> str:
    shown = ", ".join(items[:MOST_NAMED])
    return shown + (f" and {len(items) - MOST_NAMED} more" if len(items) > MOST_NAMED else "")


def for_a_search(root: str | Path, pattern: Any) -> str:
    """The line a search for `pattern` is answered with first: where the name is defined and which files use it; ""
    when it is not one name the project defines. Never raises."""
    if not isinstance(pattern, str) or not _A_NAME.fullmatch(pattern.strip()):
        return ""
    try:
        name = pattern.strip()
        graph = _graph(root)
        defined: list[str] = []
        users: list[str] = []
        for file, node in sorted(graph.items()):
            for row in node.get("definitions") or []:
                if row[1] == name:
                    defined.append(f"`{file}` lines {row[2]}-{row[3]}")
            users += [user for user in (node.get("used_by") or {}).get(name, []) if user != file]
        if not defined:
            return ""
        used = sorted(dict.fromkeys(users))
        return (f"{SAID} `{name}` is defined in {_listed(defined)}"
                + (f"; used in {_listed([f'`{u}`' for u in used])}" if used else "") + ". The matches:")
    except Exception:  # noqa: BLE001 - the search as it was
        logger.debug("Could not answer a search from the code graph", exc_info=True)
        return ""


def _callers_said(graph: dict[str, Any], file: str, row: list[Any]) -> list[str]:
    return [f"`{caller}` in `{where}`" if caller else f"the top of `{where}`"
            for where, caller in graph_lookups.callers(graph, file, graph_lookups.key(row))
            if not (where == file and caller == graph_lookups.key(row))]


def for_a_range_read(root: str | Path, path: Any, offset: Any, limit: Any) -> str:
    """The line a read of `path` from `offset` (lines from 0) adds when the range opens on a definition something
    calls; "" otherwise. Never raises."""
    try:
        start = int(offset or 0) + 1
        graph = _graph(root)
        file = graph_lookups.graph_key(graph, root, str(path or ""))
        if file is None:
            return ""
        end = start + int(limit) - 1 if str(limit or "").strip() else 10 ** 9
        found = graph_lookups.rows(graph, file)
        opening = [row for row in found if start <= row[2] <= min(end, start + OPENS_WITHIN)]
        row = (min(opening, key=lambda r: (r[2], -(r[3] - r[2]))) if opening
               else graph_lookups.innermost(found, start))
        if row is None:
            return ""
        said = _callers_said(graph, file, row)
        if not said:
            return ""
        return f"{SAID} `{graph_lookups.key(row)}` (lines {row[2]}-{row[3]}) is called by {_listed(said)}."
    except Exception:  # noqa: BLE001 - the read as it was
        logger.debug("Could not answer a read from the code graph", exc_info=True)
        return ""


def for_an_outline(root: str | Path | None, path: str) -> str:
    """What an outline answer adds: per definition of `path` that other files use, who uses it; "" for none or with
    the switch off. Never raises."""
    if root is None or not enabled():
        return ""
    try:
        graph = _graph(root)
        file = graph_lookups.graph_key(graph, root, path)
        if file is None:
            return ""
        lines = []
        for row in graph_lookups.rows(graph, file):
            said = [s for s in _callers_said(graph, file, row) if not s.endswith(f"`{file}`")]
            if said:
                lines.append(f"  {row[2]}-{row[3]}  `{graph_lookups.key(row)}`: {_listed(said)}")
        if not lines:
            return ""
        more = len(lines) - MOST_OUTLINED
        return (f"\n\n{SAID} what uses each definition from other files:\n" + "\n".join(lines[:MOST_OUTLINED])
                + (f"\n  ... and {more} more" if more > 0 else ""))
    except Exception:  # noqa: BLE001 - the outline as it was
        logger.debug("Could not add the uses to an outline", exc_info=True)
        return ""


def answered(tool: str, arguments: Any, result: Any, root: str | Path) -> Any:
    """`result` of a `grep` or a range `read_file` with the graph's line ahead of it; as it was with the switch off,
    for any other call or where the graph has nothing to say. `arguments` as the model wrote them."""
    if not enabled() or not isinstance(arguments, dict):
        return result
    content = getattr(result, "content", None)
    if not isinstance(content, str) or content.lstrip().startswith(("Error", '{"error"')):
        return result
    if tool == "grep":
        line = for_a_search(root, arguments.get("pattern"))
    elif tool == "read_file" and (arguments.get("offset") not in (None, "", 0, "0")
                                  or arguments.get("limit") not in (None, "")):
        line = for_a_range_read(root, arguments.get("file_path") or arguments.get("path"), arguments.get("offset"),
                                arguments.get("limit"))
    else:
        return result
    if not line:
        return result
    try:
        return result.model_copy(update={"content": line + "\n" + content})
    except Exception:  # noqa: BLE001 - a Command, or some other shape
        return result


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (KG.6): the tool results the graph answered in, and per stage the calls between its first
    search and its first write, in stages it answered in against the others (medians)."""
    from app.graph.surrender_evidence import WRITING_TOOLS

    records = [r for r in records if isinstance(r, dict)]
    answered_in = [r for r in records if r.get("kind") == "tool_result"
                   and SAID in str(r.get("content") or r.get("result") or r.get("output") or "")]
    head = "KG.6 searches and reads answered from the code graph"
    if not answered_in:
        return [f"     -  {head}: not reached"]
    stages = {str(r.get("stage")) for r in answered_in}
    between: dict[str, int] = {}
    searching: set[str] = set()
    done: set[str] = set()
    for r in records:
        stage = str(r.get("stage"))
        if r.get("kind") != "tool_call" or stage in done:
            continue
        tool = str(r.get("tool"))
        if tool in WRITING_TOOLS and stage in searching:
            done.add(stage)
        elif stage in searching:
            between[stage] = between.get(stage, 0) + 1
        elif tool == "grep":
            searching.add(stage)
            between[stage] = 0
    on = [n for s, n in between.items() if s in stages and s in done]
    off = [n for s, n in between.items() if s not in stages and s in done]
    return [f"  {len(answered_in):>4}  {head}, in {len(stages)} stages; calls from a stage's first search to its "
            f"first write, median {graph_lookups.median_of(on)} (other stages {graph_lookups.median_of(off)})"]


__all__ = ["NAME", "ON_BY_DEFAULT", "SAID", "answered", "effects_lines", "enabled", "explanation",
           "for_a_range_read", "for_a_search", "for_an_outline"]
