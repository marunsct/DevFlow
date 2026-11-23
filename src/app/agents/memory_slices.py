"""What of a large file, and which files, a request's project memory holds (deep review 2026-11-18, item C3).

Measured over 30 runs: a fixer's request averaged 164k characters and a builder's 269k, most of it project memory,
and one fixer was handed a 28.7k test file whole that its defect (a manifest that would not install) never named.

Two parts:

- A fixer's file longer than `MOST_CHARACTERS_WHOLE` is held as windows around the lines its failure names
  (`path:line`, as compilers, runners and stack traces print them), with the rest to be read by line; one its
  request names with no line is held whole as before; one it does not name at all is named with what it defines,
  like any file the memory leaves out. The failing lines are always in front of the fixer: a quality fix, always on.
- Behind `SLICED_MEMORY`: a fixer's or a builder's memory holds whole only the product files its own request names,
  and the files those import where the harness's code graph knows it; the rest are named with what they define.
  The whole memory as before when the request names none. An efficiency change, so a switch, off in code.
  A builder on code earlier stages wrote has the slice first and the rest of the code after it, none left out
  (`project_memory.builds_on_code`): a file it is to write does not exist yet to import what it builds on.

"Its own request" leaves out the sections every request of the sprint shares and that list every file the sprint
wrote - where things stand, and the project's setup - so a file is named only by what this request is about.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The longest file a fixer's memory holds whole when its failure names lines in it, in characters.
MOST_CHARACTERS_WHOLE = 12_000
#: Lines shown on each side of a line the failure names.
LINES_AROUND = 30
#: The most windows of one file shown.
MOST_WINDOWS = 6

#: What a sliced memory says of itself; the audit's switch-firing check reads it.
SAID = "Held whole: the files this request names and the files they import; the rest are named below."

#: Sections every request of a sprint shares, which name every file the sprint wrote.
_SHARED_HEADINGS = ("--- Where things stand", "--- Project setup")
_A_HEADING = re.compile(r"^--- .+ ---\s*$", re.M)


class _SlicedMemory:
    """`SLICED_MEMORY` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("A fixer's or a builder's project memory holds whole only the product files its request names and "
                   "the files they import (from the harness's code graph); the rest are named with what they define, "
                   "to be read when needed. The whole memory as before when the request names no file.")

    @staticmethod
    def enabled() -> bool:
        return is_on("SLICED_MEMORY", _SlicedMemory.ON_BY_DEFAULT)


sliced_memory_switch = _SlicedMemory()


def enabled() -> bool:
    return sliced_memory_switch.enabled()


def the_ask(request: str) -> str:
    """`request` less the sections every request of the sprint shares (`_SHARED_HEADINGS`)."""
    text = request or ""
    kept: list[str] = []
    position = 0
    skipping = False
    for match in _A_HEADING.finditer(text):
        if not skipping:
            kept.append(text[position:match.start()])
        skipping = match.group(0).startswith(_SHARED_HEADINGS)
        position = match.start()
    if not skipping:
        kept.append(text[position:])
    return "".join(kept)


def _forms(path: str, others: Iterable[str]) -> list[str]:
    """How a request may write `path`: the whole path, then each shorter ending with a folder, then its name when no
    other file has that name."""
    parts = path.split("/")
    forms = ["/".join(parts[n:]) for n in range(len(parts) - 1)]
    name = parts[-1]
    if not any(other != path and other.rsplit("/", 1)[-1] == name for other in others):
        forms.append(name)
    return forms


def _written(form: str) -> str:
    return rf"(?<![\w.-]){re.escape(form)}(?![\w-])"


def named(ask: str, path: str, others: Iterable[str] = ()) -> bool:
    """Whether `ask` names `path`, by any form of it (`_forms`)."""
    return any(re.search(_written(form), ask or "") for form in _forms(path, list(others)))


def lines_named(ask: str, path: str, others: Iterable[str] = ()) -> list[int]:
    """The line numbers `ask` names in `path`, as `path:line` (a compiler's, a runner's or a stack trace's form)."""
    found: set[int] = set()
    for form in _forms(path, list(others)):
        found.update(int(n) for n in re.findall(_written(form) + r":(\d+)", ask or ""))
    return sorted(n for n in found if n > 0)


def windows(text: str, lines: list[int], budget: int = MOST_CHARACTERS_WHOLE) -> str:
    """`text`'s lines around each of `lines`, numbered as the file numbers them, within `budget`; "" for none."""
    all_lines = text.splitlines()
    spans: list[list[int]] = []
    for line in lines[:MOST_WINDOWS * 4]:
        start, end = max(1, line - LINES_AROUND), min(len(all_lines), line + LINES_AROUND)
        if start > end:
            continue
        if spans and start <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    shown: list[str] = []
    used = 0
    for start, end in spans[:MOST_WINDOWS]:
        body = "\n".join(f"{n}: {all_lines[n - 1]}" for n in range(start, end + 1))
        if used + len(body) > budget:
            body = body[:max(0, budget - used)].rsplit("\n", 1)[0]
            if not body:
                break
        shown.append(f"[lines {start}-{end}]\n{body}")
        used += len(body)
    return "\n\n".join(shown)


def windowed_block(path: str, text: str, lines: list[int]) -> str:
    """A fixer's memory block for a long file: the windows around `lines`, the rest to be read by line; "" for none."""
    shown = windows(text, lines)
    if not shown:
        return ""
    total = text.count("\n") + 1
    return (f"=== {path} ({total} lines; only the lines around those the failure names, numbered as in the file - "
            f"read others by line) ===\n{shown}\n")


def imports_of(repo_root: str | Path, paths: Iterable[str]) -> set[str]:
    """The files `paths` import, where the harness's code graph knows them; empty when it does not."""
    try:
        from app.analysis.project_graph import build

        graph = build(repo_root)
    except Exception:  # noqa: BLE001 - no graph, no imports
        return set()
    return {target for path in paths for target in (graph.get(path) or {}).get("imports", [])}


def the_slice(repo_root: str | Path, ask: str, files: dict[str, str]) -> set[str] | None:
    """The product files a sliced memory holds whole: those `ask` names and what they import; None to hold all."""
    product = [path for path in files if not path.startswith(("docs/", "."))]
    chosen = {path for path in product if named(ask, path, product)}
    if not chosen:
        return None
    return chosen | (imports_of(repo_root, chosen) & set(product))


__all__ = ["LINES_AROUND", "MOST_CHARACTERS_WHOLE", "ON_BY_DEFAULT", "SAID", "enabled", "imports_of", "lines_named",
           "named", "sliced_memory_switch", "the_ask", "the_slice", "windowed_block", "windows"]
