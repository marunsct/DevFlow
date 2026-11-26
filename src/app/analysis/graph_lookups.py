"""Lookups on the code graph shared by what reads it at a request, a tool's answer, a write and a review (KG.5-KG.8).

The graph (`analysis.project_graph`, KG.2-KG.4) keeps per file its definitions as `[kind, name, first, last,
enclosing]`, which definitions each one calls (`calls`), which call it (`called_by`) and which files use each name
(`used_by`), by name and only where one file is the one it can be (KG.3). These read it: a definition by its key, the
innermost one holding a line, its signature and its numbered body, and where another file uses a name. Nothing here
names a language: the rows are the grammar's, the text the file's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

#: The most characters of a signature shown.
MOST_SIGNATURE_CHARACTERS = 140

Graph = dict[str, dict[str, Any]]


def key(row: list[Any]) -> str:
    """A definition row's key in `calls` and `called_by`: `Type.name` inside another definition, else its name."""
    return f"{row[4]}.{row[1]}" if row[4] else str(row[1])


def graph_key(graph: Graph, root: str | Path, path: str) -> str | None:
    """The graph's key for `path` as a tool or a request wrote it - workspace-relative, with a leading `/`, absolute
    under `root`, or relative to the project's directory; None when the graph has no such file."""
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return None
    try:
        absolute = Path(text)
        if absolute.is_absolute() and absolute.resolve().is_relative_to(Path(root).resolve()):
            text = absolute.resolve().relative_to(Path(root).resolve()).as_posix()
    except (OSError, ValueError):
        pass
    text = text.lstrip("/").removeprefix("./")
    if text in graph:
        return text
    ending = [name for name in graph if name.endswith("/" + text)]
    return ending[0] if len(ending) == 1 else None


def rows(graph: Graph, file: str) -> list[list[Any]]:
    """The definitions the grammar read in `file`; [] for a file it did not read."""
    return list((graph.get(file) or {}).get("definitions") or [])


def by_key(graph: Graph, file: str, wanted: str) -> list[Any] | None:
    """The definition of `file` whose key (`key`) or name is `wanted`: the key first, then a name only one row has."""
    found = rows(graph, file)
    exact = [row for row in found if key(row) == wanted]
    if exact:
        return exact[0]
    named = [row for row in found if row[1] == wanted]
    return named[0] if len(named) == 1 else None


def innermost(found: Iterable[list[Any]], line: int) -> list[Any] | None:
    """The innermost of `found` holding `line`; None outside every one."""
    best = None
    for row in found:
        if row[2] <= line <= row[3] and (best is None or row[3] - row[2] < best[3] - best[2]):
            best = row
    return best


def callers(graph: Graph, file: str, wanted: str) -> list[tuple[str, str]]:
    """(file, the definition there that calls it, "" at a file's top) for each use of `file`'s definition `wanted`."""
    return [(str(pair[0]), str(pair[1])) for pair in ((graph.get(file) or {}).get("called_by") or {}).get(wanted, [])]


def callees(graph: Graph, file: str, wanted: str) -> list[tuple[str, str]]:
    """(name, the file defining it) for each name `file`'s definition `wanted` calls of a known definition."""
    return [(str(pair[0]), str(pair[1])) for pair in ((graph.get(file) or {}).get("calls") or {}).get(wanted, [])]


def signature(lines: list[str], row: list[Any]) -> str:
    """The definition's first line that names it (a marker or comment above it may open its span), shortened."""
    first, last = int(row[2]), int(row[3])
    span = lines[max(0, first - 1):max(first, min(last, first + 4))]
    chosen = next((line for line in span if str(row[1]) in line), span[0] if span else "")
    said = " ".join(chosen.strip().split())
    return said if len(said) <= MOST_SIGNATURE_CHARACTERS else said[:MOST_SIGNATURE_CHARACTERS - 3] + "..."


def numbered(lines: list[str], first: int, last: int) -> str:
    """Lines `first`-`last` of a file, each after its number as a read shows it."""
    return "\n".join(f"{number}: {lines[number - 1]}" for number in range(max(1, first), min(len(lines), last) + 1))


def lines_using(root: str | Path, file: str, name: str) -> list[int]:
    """The lines of `file` (workspace-relative) that use `name`, from its syntax tree as it is now; [] when no grammar
    reads it or it cannot be read."""
    from app.analysis.parsed_definitions import read

    path = Path(root) / file
    try:
        parsed = read(path, path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []
    if parsed is None:
        return []
    return sorted({line for _form, used, line in parsed.references if used == name})


def text_lines(root: str | Path, file: str) -> list[str]:
    """`file`'s lines as it is now; [] when it cannot be read."""
    try:
        return (Path(root) / file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def stages_carrying(records: Iterable[Any], needle: str, kinds: tuple[str, ...] = ("model_request",)) -> set[str]:
    """The stages one of whose records of `kinds` carries `needle` (a request's messages, a tool result's content)."""
    import json

    found: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or record.get("kind") not in kinds:
            continue
        value = record.get("messages") if record.get("kind") == "model_request" else (
            record.get("content") or record.get("result") or record.get("output"))
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        if needle in text:
            found.add(str(record.get("stage")))
    return found


#: The tools that read a file of the workspace.
READ_TOOLS = frozenset({"read_file", "read_repository_file"})


def per_stage(records: Iterable[Any]) -> dict[str, dict[str, int]]:
    """For `loop.sh effects`: per stage, its tool calls, file reads, distinct files read, and the input tokens its
    first reply reported (`opening`, 0 when none did)."""
    import ast

    found: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        stage = str(record.get("stage"))
        kind = record.get("kind")
        if kind == "tool_call":
            seen = found.setdefault(stage, {"calls": 0, "reads": 0, "paths": set(), "opening": 0})
            seen["calls"] += 1
            if str(record.get("tool")) in READ_TOOLS:
                args = record.get("args")
                if isinstance(args, str):
                    try:
                        args = ast.literal_eval(args)
                    except (ValueError, SyntaxError):
                        args = {}
                args = args if isinstance(args, dict) else {}
                seen["reads"] += 1
                seen["paths"].add(str(args.get("file_path") or args.get("relative_path") or args.get("path") or ""))
        elif kind == "model_response":
            seen = found.setdefault(stage, {"calls": 0, "reads": 0, "paths": set(), "opening": 0})
            usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
            if not seen["opening"]:
                seen["opening"] = int(usage.get("input_tokens") or 0)
    return {stage: {"calls": s["calls"], "reads": s["reads"], "distinct": len(s["paths"]), "opening": s["opening"]}
            for stage, s in found.items()}


def median_of(values: list[int]) -> str:
    """The median of `values` as the effects report prints it; "-" for none."""
    from statistics import median

    return f"{median(values):g}" if values else "-"


__all__ = ["MOST_SIGNATURE_CHARACTERS", "READ_TOOLS", "by_key", "callees", "callers", "graph_key", "innermost", "key",
           "lines_using", "median_of", "numbered", "per_stage", "rows", "signature", "stages_carrying", "text_lines"]
