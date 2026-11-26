"""Before a reading stage opens on a product past its memory's room, one short call chooses the lines it needs (plan
PF.4, behind `RANGES_CHOSEN_BEFORE_A_READING_STAGE`).

The suite's author, the test round and the technical lead read more than any other stage and re-read most: of their
input, 48%, 35% and 52% was waste on the medium runs measured (`reports/research/2026-11-26-graphify-and-performance-
features.md`). On a product larger than the memory's room, their memory held whole files in rank order until the
room ran out and named the rest; the stage read what it needed of the rest, a summary dropped it, and it read it again.
A fixer whose failure names no file asks one cheap call where to look (`graph.localisation.asked`); this is the same
for these stages.

With the switch on, before such a stage's first call, when the project's files are past the memory's room
(`project_memory.budget_for`): one call with reasoning off (`thinking.without_reasoning`, at most `MOST_OUTPUT_TOKENS`)
is given the stage's request and an outline of the code - each definition and test with its first and last line
(`analysis.outline`) - and names at most `MOST_RANGES` ranges as `file: lines a-b`. Each is kept when its file exists
and its lines are in the file (at most `MOST_LINES` of one). The memory then holds those lines, numbered as in the
file, under `SAID`; the other code files only in the outline, to be read by range; the documents as before. Asked
once per stage visit (`chosen` remembers its answer); a call that names nothing leaves the memory as it was.

A transcript record (`RECORD_KIND`) keeps the ranges, for `loop.sh effects` (`effects_lines`): reads in those stages,
repeat reads, and the files read that no range named. Nothing here names a language or a framework. Never raises.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

NAME = "RANGES_CHOSEN_BEFORE_A_READING_STAGE"
#: `RANGES_CHOSEN_BEFORE_A_READING_STAGE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The stages a range is chosen for: the suite's author, the test round, the technical lead (and their re-runs).
STAGES = ("acceptance_author", "test_round", "technical_lead")
MOST_RANGES = 8
#: Lines of one range held, at most.
MOST_LINES = 160
MOST_OUTPUT_TOKENS = 600
#: Characters of the stage's request and of the outline the call is given, at most.
MOST_ASK_CHARACTERS = 6_000
MOST_OUTLINE_CHARACTERS = 16_000
#: How the memory heads the lines chosen; the switch's firing signal.
SAID = "lines chosen for this work before it opened"
RECORD_KIND = "ranges_chosen"
#: A range as the answer writes it: `path: lines 12-40`, `path:12-40`, `path lines 12 - 40`.
_A_RANGE = re.compile(r"([\w./@+\-]+\.[A-Za-z0-9]+)\s*:?\s*(?:lines?\s*)?(\d+)\s*[-–]\s*(\d+)")
_SYSTEM = "You choose which lines of a codebase a piece of work needs to read. You answer with one JSON object."
#: (workspace, stage, the request's digest) -> the ranges chosen, so one visit asks once.
_CHOSEN: "OrderedDict[tuple[str, str, str], dict[str, list[tuple[int, int]]]]" = OrderedDict()
_MOST_REMEMBERED = 64


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


def applies(stage: str) -> bool:
    return str(stage or "").startswith(STAGES)


def past_its_room(files: dict[str, str], budget: int) -> bool:
    return budget > 0 and sum(map(len, files.values())) > budget


def _code(files: dict[str, str]) -> dict[str, str]:
    """The project's code and test files, by what their names say (`file_kinds.classify_file`)."""
    from app.analysis.file_kinds import classify_file

    return {path: text for path, text in files.items()
            if not path.startswith(("docs/", ".")) and classify_file(path) in ("application", "test")}


def ranges_in(text: str, files: dict[str, str]) -> dict[str, list[tuple[int, int]]]:
    """The ranges an answer names that the project holds: each file exists, each range within it, at most
    `MOST_LINES` lines of one and `MOST_RANGES` in all, in the answer's order; overlapping ranges of a file merged."""
    found: dict[str, list[tuple[int, int]]] = {}
    count = 0
    for path, first, last in _A_RANGE.findall(str(text or "")):
        relative = path.strip().removeprefix("./").lstrip("/")
        if relative not in files:
            continue
        total = len(files[relative].splitlines())
        start, end = sorted((int(first), int(last)))
        start, end = max(1, start), min(total, end, max(1, start) + MOST_LINES - 1)
        if start > end:
            continue
        found.setdefault(relative, []).append((start, end))
        count += 1
        if count >= MOST_RANGES:
            break
    for relative, spans in found.items():
        merged: list[tuple[int, int]] = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        found[relative] = merged
    return found


def _prompt(opening: str, outline_text: str) -> str:
    return (
        "A stage of the build is about to start on the request below. The project is too large to hold whole, so its "
        "memory will hold only the lines you name.\n\n"
        f"The request:\n{str(opening)[:MOST_ASK_CHARACTERS]}\n\n"
        f"An outline of the project's code, each definition and test with its first and last line:\n{outline_text}\n\n"
        f"Name at most {MOST_RANGES} ranges of lines this work needs to read, most needed first, each as "
        "`file: lines a-b` with the file's path as the outline writes it. Answer with one JSON object with the field "
        "`ranges`, a list of those strings, nothing else."
    )


def _ask(model: Any, opening: str, code: dict[str, str]) -> str:
    """The one call's reply text; "" when it cannot be asked."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.thinking import without_reasoning
    from app.analysis import outline
    from app.models.reply_text import reply_text
    from app.observability.direct_calls import config_for_this_run

    reply = without_reasoning(model).invoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=_prompt(opening, outline.rendered(code, MOST_OUTLINE_CHARACTERS))),
    ], max_tokens=MOST_OUTPUT_TOKENS, **config_for_this_run("ranges_chosen"))
    return reply_text(reply)


def chosen(repo_root: str | Path, model: Any, opening: str, stage: str, files: dict[str, str], budget: int, *,
           ask: bool = True) -> dict[str, list[tuple[int, int]]]:
    """The ranges the stage's memory holds, {file: [(first, last)]}; {} when the switch is off, the stage is not one
    of `STAGES`, the project fits its room, or nothing was chosen. Asked once per (workspace, stage, request); with
    `ask` False only what was asked before is answered. Never raises."""
    if not enabled() or not applies(stage) or model is None or not past_its_room(files, budget):
        return {}
    key = (str(Path(repo_root).resolve()), str(stage), hashlib.sha256(str(opening).encode("utf-8", "replace")).hexdigest()[:16])
    if key in _CHOSEN:
        return _CHOSEN[key]
    if not ask:
        return {}
    code = _code(files)
    try:
        answer = ranges_in(_ask(model, opening, code), code) if code else {}
    except Exception as error:  # noqa: BLE001 - the memory as before
        from app.models.call_gate import raise_if_the_run_stopped

        raise_if_the_run_stopped(error)
        logger.debug("Could not choose the ranges for %s", stage, exc_info=True)
        answer = {}
    _CHOSEN[key] = answer
    while len(_CHOSEN) > _MOST_REMEMBERED:
        _CHOSEN.popitem(last=False)
    _note(stage, answer)
    return answer


def blocks(files: dict[str, str], ranges: dict[str, list[tuple[int, int]]]) -> dict[str, str]:
    """{file: its memory block}: the chosen lines, numbered as in the file, under `SAID`."""
    found: dict[str, str] = {}
    for path, spans in ranges.items():
        lines = files.get(path, "").splitlines()
        shown = "\n\n".join(f"[lines {a}-{b}]\n" + "\n".join(f"{n}: {lines[n - 1]}" for n in range(a, b + 1))
                            for a, b in spans)
        found[path] = (f"=== {path} ({len(lines)} lines; the {SAID}, numbered as in the file - read others by "
                       f"line) ===\n{shown}\n")
    return found


def _note(stage: str, answer: dict[str, list[tuple[int, int]]]) -> None:
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(_run_id_from_config(), stage, RECORD_KIND, message=SAID if answer else "",
               ranges=[f"{path}: lines {a}-{b}" for path, spans in answer.items() for a, b in spans])
    except Exception:  # noqa: BLE001 - the stage goes on unrecorded
        logger.debug("Could not record the ranges chosen", exc_info=True)


def forget() -> None:
    """Every range remembered dropped."""
    _CHOSEN.clear()


def effects_lines(records: Iterable[Any]) -> list[str]:
    """`loop.sh effects` (PF.4): reading stages given chosen ranges against the others - reads and repeat reads, each a
    median - and the files read there that no range named."""
    from app.analysis import graph_lookups

    records = [r for r in records if isinstance(r, dict)]
    given = {str(r.get("stage")): [str(x).split(":", 1)[0] for x in r.get("ranges") or []]
             for r in records if r.get("kind") == RECORD_KIND and r.get("ranges")}
    head = "PF.4 reading stages whose memory held the lines chosen for them"
    if not given:
        return [f"     -  {head}: not reached"]
    stages = {s: v for s, v in graph_lookups.per_stage(records).items() if applies(s)}

    def described(group: dict[str, dict[str, int]]) -> str:
        return (f"reads {graph_lookups.median_of([s['reads'] for s in group.values()])}, repeat reads "
                f"{graph_lookups.median_of([s['reads'] - s['distinct'] for s in group.values()])}")

    missed = 0
    for record in records:
        if record.get("kind") == "tool_call" and str(record.get("stage")) in given and \
                str(record.get("tool")) in graph_lookups.READ_TOOLS:
            if not any(path in str(record.get("args") or "") for path in given[str(record.get("stage"))]):
                missed += 1
    on = {s: v for s, v in stages.items() if s in given}
    off = {s: v for s, v in stages.items() if s not in given}
    return [f"  {len(given):>4}  {head} (medians: {described(on)}; other reading stages {described(off)}; "
            f"{missed} reads of files no range named)"]


__all__ = ["MOST_LINES", "MOST_RANGES", "NAME", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "STAGES", "applies", "blocks",
           "chosen", "effects_lines", "enabled", "forget", "past_its_room", "ranges_in"]
