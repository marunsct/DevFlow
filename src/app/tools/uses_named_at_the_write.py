"""What a change breaks, said at the write (plan KG.7).

Behind `USES_NAMED_AT_THE_WRITE`, off in code until measured.

A builder that renames a function or changes its parameters learns that another file still calls the old form only
when the build, the compiler or a test fails, rounds later; the next work order hears of it from the harness's
interface notes (`agents.interface_changes`), the author never. The code graph knows who uses each definition (KG.3).

With the switch on, a write that removes or renames a definition, or changes its parameters, while other files use it
by the graph is answered, after its own reply, with each of those files and the lines that use it - once per
definition a stage. Only the graph's unambiguous uses are named (a name several files may define never is), and only
files that still use the name as they are now.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

from app.analysis import graph_lookups
from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "USES_NAMED_AT_THE_WRITE"
#: `USES_NAMED_AT_THE_WRITE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: How the note begins; the switch-firing check reads it in the write's result.
SAID = "Other files use what this write changed"
#: What the admin page says this switch does.
explanation = ("A write that removes or renames a definition, or changes its parameters, while other files use it is "
               "answered with those files and their lines, once, from the harness's code graph. Only uses the graph "
               "is sure of are named.")
#: The tools whose success changes a file.
WRITES = frozenset({"write_artifact", "edit_artifact", "write_file", "edit_file", "replace_lines"})
#: Files named for one definition, and lines for one file, at most.
MOST_FILES = 6
MOST_LINES = 5
#: The transcript record of a note shown; `effects_lines` reads it.
RECORD_KIND = "uses_named_at_the_write"


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def _parameters(lines: list[str], row: list[Any]) -> str | None:
    """The definition's parameter list as written, spaces folded; None for a definition with none (a type)."""
    text = "\n".join(lines[row[2] - 1:min(row[3], row[2] + 8)])
    at = text.find(str(row[1]))
    opening = text.find("(", at if at >= 0 else 0)
    if opening < 0 or "{" in text[at:opening] or "\n\n" in text[at:opening]:
        return None
    depth = 0
    for index in range(opening, len(text)):
        depth += {"(": 1, ")": -1}.get(text[index], 0)
        if depth == 0:
            return " ".join(text[opening:index + 1].split())
    return None


def changes(path: str, before: str, after: str) -> list[tuple[str, str, str]]:
    """(the definition's key, its name, `removed` or `parameters`) for each definition of `before` that `after` no
    longer has (by key), or has with other parameters; [] when no grammar reads the file."""
    from app.analysis.parsed_definitions import read

    old, new = read(path, before), read(path, after)
    if old is None or new is None:
        return []
    old_lines, new_lines = before.splitlines(), after.splitlines()
    kept = {graph_lookups.key(d.as_row()): d.as_row() for d in new.definitions}
    found: list[tuple[str, str, str]] = []
    for definition in old.definitions:
        row = definition.as_row()
        name = graph_lookups.key(row)
        if name not in kept:
            found.append((name, row[1], "removed"))
            continue
        was, now = _parameters(old_lines, row), _parameters(new_lines, kept[name])
        if was is not None and now is not None and was != now:
            found.append((name, row[1], "parameters"))
    return list(dict.fromkeys(found))


def note(root: str | Path, file: str, before: str, after: str, graph: dict[str, Any], said: set[str]) -> str:
    """The note for a write of `file` (graph key) from `before` to `after`, against the graph as it was before the
    write; "" when nothing other files use changed. Adds each definition named to `said`, and names none in it."""
    parts: list[str] = []
    named_files: list[str] = []
    for key, name, how in changes(file, before, after):
        if f"{file}:{key}" in said:
            continue
        users = [user for user in ((graph.get(file) or {}).get("used_by") or {}).get(name, []) if user != file]
        places = []
        for user in users[:MOST_FILES]:
            lines = graph_lookups.lines_using(root, user, name)
            if lines:
                places.append(f"`{user}` line{'s' if len(lines) > 1 else ''} "
                              + ", ".join(str(n) for n in lines[:MOST_LINES]))
                named_files.append(user)
        if not places:
            continue
        said.add(f"{file}:{key}")
        what = "no longer defines" if how == "removed" else "changed the parameters of"
        parts.append(f"- it {what} `{key}`, which " + "; ".join(places) + " still use"
                     + ("s" if len(places) == 1 else ""))
    if not parts:
        return ""
    return (f"{SAID} (the harness's code graph):\n" + "\n".join(parts)
            + "\nChange those uses to match, or keep the old form, before you answer.")


def _path_of(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    return str(arguments.get("relative_path") or arguments.get("file_path") or arguments.get("path") or "")


def _recorded(files: list[str], text: str) -> None:
    try:
        from app.observability.transcript import _run_id_from_config, _stage_from_config, record

        record(_run_id_from_config(), _stage_from_config(""), RECORD_KIND, message=text, files=files)
    except Exception:  # noqa: BLE001 - a record never fails a write
        logger.debug("Could not record a write's uses", exc_info=True)


def after_a_write(root: str | Path, call: dict[str, Any], run: Any, said: set[str]) -> Any:
    """Run the write `run` (the next handler) and, with the switch on, add the note to its result. Never raises
    more than the write itself does."""
    if not enabled() or str(call.get("name") or "") not in WRITES:
        return run()
    before = graph = file = None
    try:
        from app.analysis.parsed_definitions import row_for
        from app.analysis.project_graph import build

        wanted = _path_of(call.get("args"))
        if wanted and row_for(wanted) is not None:
            graph = build(root)
            file = graph_lookups.graph_key(graph, root, wanted)
            if file is not None and graph_lookups.rows(graph, file):
                before = (Path(root) / file).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - the write as it is
        logger.debug("Could not read the file before a write", exc_info=True)
    result = run()
    if before is None or graph is None or file is None:
        return result
    try:
        after = (Path(root) / file).read_text(encoding="utf-8", errors="replace")
        content = getattr(result, "content", None)
        if after == before or not isinstance(content, str):
            return result
        text = note(root, file, before, after, graph, said)
        if not text:
            return result
        _recorded([file], text)
        return result.model_copy(update={"content": content.rstrip() + "\n\n" + text})
    except Exception:  # noqa: BLE001 - the write's own reply
        logger.debug("Could not name a write's uses", exc_info=True)
        return result


def build_middleware(repo_root: str) -> Any:
    """The middleware that names, after a write, the files that still use what it changed; a pass-through when off."""
    from langchain.agents.middleware import AgentMiddleware

    class UsesNamedAtTheWriteMiddleware(AgentMiddleware):
        name = "UsesNamedAtTheWriteMiddleware"

        def __init__(self) -> None:
            super().__init__()
            self.said: set[str] = set()

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            call = getattr(request, "tool_call", None) or {}
            return after_a_write(repo_root, call, lambda: handler(request), self.said)

    return UsesNamedAtTheWriteMiddleware()


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (KG.7): notes shown at a write, and how many were followed in the same stage by a write to a
    file they named."""
    records = [r for r in records if isinstance(r, dict)]
    shown = [(index, r) for index, r in enumerate(records) if r.get("kind") == RECORD_KIND]
    head = "KG.7 writes told which files still use what they changed"
    if not shown:
        return [f"     -  {head}: not reached"]
    followed = 0
    for index, r in shown:
        named = set(re.findall(r"`([^`]+)` line", str(r.get("message") or "")))
        stage = r.get("stage")
        for later in records[index + 1:]:
            if later.get("kind") == "tool_call" and later.get("stage") == stage and str(later.get("tool")) in WRITES:
                args = later.get("args")
                if any(path and str(args).find(path.rsplit("/", 1)[-1]) >= 0 for path in named):
                    followed += 1
                    break
    return [f"  {len(shown):>4}  {head}; {followed} followed by a write to a file named"]


__all__ = ["NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "WRITES", "after_a_write", "build_middleware", "changes",
           "effects_lines", "enabled", "explanation", "note"]
