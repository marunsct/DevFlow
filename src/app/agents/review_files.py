"""The files a review judges, held by the harness in the project memory, not explored by tool (LF.1284).

Measured on one medium run (19-21 files): the code review read 19 files six to eight times each over twenty minutes,
the security review made 155 reads of 21 files and was summarised 11 times in 31 calls, the security-and-reliability
advice review made 112 reads with 6 summaries in 19 calls. Each review was pointed at the whole sprint and told to
open what its request did not show; the reads went into the conversation, the one place a summary deletes, and the
set was larger than the room the conversation has. Each summary dropped two or three batches of reads and the next
call read them again, until the call cap ended the stage.

So the harness hands the files over itself, where a summary cannot reach them: ranked first in the project memory,
numbered so a finding can cite a line without a read, with the plans after them as digests
(`project_memory.render_for_a_review`); the request names them as held instead of repeating them or ordering a read
of each. A product whose files today's request and memory already show (`fits_as_today`) is sent exactly as today:
nothing else in this module is used for it.

`under_review` also decides which changed files a review is shown at all, from the language table
(`app.stacks.languages`) and the file kinds (`app.analysis.file_kinds`), not from a fixed list of suffixes: the
security review's own list knew JavaScript, Python, HTML and JSON only, so a Go, Rust or Java product's request said
"None of the changed files could be read" on every size of product.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

#: The stages whose memory may hold the files under review first.
REVIEW_STAGES = ("security_review", "advice_review", "code_review", "milestone_review", "acceptance_review")
#: The other stages that read the workspace to do their work and hold what they read the same way (LF.1286), each
#: measured re-reading on one medium run: the technical lead the product's code and the sprint's locked tests (12
#: reads a file, 21 summaries), a test round the milestone's changed files (3.5-7 a file, 5-12 summaries a round).
READING_STAGES = ("technical_lead", "test_round")
#: The stages that write the files they work on and hold them as they are now from their first summary (LF.1288).
#: Measured on one medium run: the suite's author read its own file 3-8 times a visit (up to 24): its memory held the
#: file as the visit began, "read for the current text", and every summary deleted the copy it had read.
#: And the builders (`specialist_` stages): measured on the next medium run, a sprint's backend builder spent 24 minutes
#: reading about six files a call with a summary every two or three calls and one write.
WRITING_STAGES = ("acceptance_author", "specialist_")

#: How the memory heads a file it holds numbered, after `=== path `: a review's, and another reading stage's.
NUMBERED_MARK = "(numbered lines, under review) ==="
NUMBERED_TO_READ = "(numbered lines) ==="
#: What both headings begin with, after `=== path `.
NUMBERED_START = "(numbered lines"

#: The line of a review's request that names the files its memory holds; the memory is rendered from it.
HELD_MARK = "--- Held whole in the project memory for this review, with their line numbers: "
#: The same line in the request of another reading stage (`READING_STAGES`).
HELD_TO_READ_MARK = "--- Held whole in the project memory for this work, with their line numbers: "
_HELD_END = " ---"
#: The request's sentence on the files its memory outlines rather than holds (LF.1287).
OUTLINED = ("The project's other files are outlined in the project memory, each definition and test with its first "
            "and last line: read only the lines you need, by range (`offset` and `limit`), not the whole file.\n")
_NAME = re.compile(r"`([^`]+)`")

#: Any other data file a review was shown before (the security review's own list had it).
_DATA_SUFFIXES = (".json",)


def is_a_review_stage(stage: str) -> bool:
    return str(stage or "").startswith(REVIEW_STAGES)


def holds_what_it_reads(stage: str) -> bool:
    """Whether a stage's memory may hold the files it reads first, numbered: a review, or another reading stage; a
    fix stage with `FIXERS_HOLD_WHAT_THEY_READ` on (LF.1406)."""
    from app.agents import fixers_hold_what_they_read

    if fixers_hold_what_they_read.is_a_fixer(stage):
        return fixers_hold_what_they_read.enabled()
    return str(stage or "").startswith(REVIEW_STAGES + READING_STAGES + WRITING_STAGES)


def numbered_heading(stage: str) -> str:
    """How the memory heads a file it holds numbered for `stage`, after `=== path `."""
    return NUMBERED_MARK if is_a_review_stage(stage) else NUMBERED_TO_READ


def numbered(text: str) -> str:
    """`text` with each line's number, as a read of the file shows it, so a finding cites a line without a read."""
    return "\n".join(f"{number:>6}\t{line}" for number, line in enumerate(str(text).splitlines(), start=1))


def _code_suffixes() -> frozenset[str]:
    from app.analysis.file_kinds import BEHAVIOUR_SUFFIXES, SCRIPTED_MARKUP_SUFFIXES
    from app.stacks.languages import LANGUAGES

    return frozenset({s for row in LANGUAGES for s in row.suffixes} | BEHAVIOUR_SUFFIXES | SCRIPTED_MARKUP_SUFFIXES
                     | set(_DATA_SUFFIXES))


def _rank(path: str) -> int | None:
    """0 the product's code, 1 its configuration, 2 its tests; None for what no review judges."""
    from app.analysis.file_kinds import classify_file

    kind = classify_file(path)
    if kind in ("vendored", "document"):
        return None
    if kind == "config":
        return 1
    if Path(path).suffix.lower() not in _code_suffixes():
        return None
    return 2 if kind == "test" else 0


def _generated(root: Path, relative: str) -> bool:
    """Whether a folder on the path is a tool's, an installer's or a build's, not the product's."""
    from app.stacks.languages import NOT_THE_PRODUCT, is_generated

    parts = Path(relative).parts[:-1]
    for depth, name in enumerate(parts):
        if name in NOT_THE_PRODUCT or name == ".harness" or name.endswith((".egg-info", ".dist-info")):
            return True
        try:
            siblings = os.listdir(root.joinpath(*parts[:depth]))
        except OSError:
            siblings = []
        if is_generated(name, siblings):
            return True
    return False


def under_review(repo_root: str | Path, changed_files: Iterable[str]) -> list[tuple[str, str]]:
    """The changed files a review judges, each with its text: the product's code, then its configuration, then its
    tests, each group in the order given. Generated folders, lock files, documents and the files the harness writes
    and keeps for its pack are left out. Never raises."""
    root = Path(repo_root)
    try:
        from app.agents.project_memory import kept_by_the_harness

        kept = set(kept_by_the_harness(root))
    except Exception:  # noqa: BLE001 - none left out for being the harness's
        kept = set()
    ranked: list[tuple[int, int, str, str]] = []
    seen: set[str] = set()
    for order, name in enumerate(changed_files or ()):
        name = str(name or "").strip().lstrip("/")
        if not name or name in seen or name in kept:
            continue
        seen.add(name)
        rank = _rank(name)
        if rank is None:
            continue
        path = (root / name).resolve()
        try:
            resolved_root = root.resolve()
            if not path.is_file() or (resolved_root not in path.parents and path.parent != resolved_root):
                continue
            if _generated(root, name):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ranked.append((rank, order, name, text))
    return [(name, text) for _, _, name, text in sorted(ranked)]


def _as_the_agent_sees_it(model: Any) -> Any:
    """The chat model a role agent is built on (`role_agent.a_chat_model`), whose window the memory is sized from."""
    try:
        from app.agents.role_agent import a_chat_model

        return a_chat_model(model)
    except Exception:  # noqa: BLE001
        return model


def opening_of(request: dict[str, Any]) -> str:
    """The text of a request's last message, as the project memory reads it."""
    try:
        content = request["messages"][-1]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    return content if isinstance(content, str) else str(content)


def _in_the_request(text: str, opening: str) -> bool:
    """Whether `opening` carries the whole of `text`: as it is, or as a new file's diff (`+` before every line)."""
    body = str(text).rstrip()
    if body in opening:
        return True
    lines = body.splitlines()
    return bool(lines) and "\n".join("+" + line for line in lines) in opening


def fits_as_today(files: Sequence[tuple[str, str]], repo_root: str | Path, model: Any, stage: str,
                  opening: str, told_to_open: Sequence[str] = ()) -> bool:
    """Whether today's request and memory already show every file under review whole: the size gate. True means
    the review is sent exactly as today. A file today's request tells the reviewer to open (`told_to_open`) is not
    shown by the memory: the reviewer reads it into the conversation all the same. Never raises: True."""
    if not files:
        return True
    try:
        from app.agents import project_memory

        if not project_memory.enabled():
            return True
        _, held = project_memory.as_the_stage_opens(repo_root, _as_the_agent_sees_it(model), opening, stage)
        return all((path in held and path not in told_to_open) or _in_the_request(text, opening)
                   for path, text in files)
    except Exception:  # noqa: BLE001 - as today
        logger.debug("Could not tell whether a review's files fit", exc_info=True)
        return True


def held_for_review(files: Sequence[tuple[str, str]], repo_root: str | Path, model: Any, stage: str,
                    opening: str, told_to_open: Sequence[str] = ()) -> list[str] | None:
    """The files under review the memory holds for this review, in its order; None when they fit as today (or the
    memory would hold none of them), and the review is sent as today. Never raises: None."""
    if not files or not holds_what_it_reads(stage) or fits_as_today(files, repo_root, model, stage, opening,
                                                                   told_to_open):
        return None
    try:
        from app.agents import project_memory

        names = [path for path, _ in files]
        _, held = project_memory.render_for_a_review(repo_root, _as_the_agent_sees_it(model), "", stage, names)
        chosen = [path for path in names if path in held]
        if chosen:
            logger.info("%s: %d of %d files under review held in its memory, numbered", stage, len(chosen), len(names))
        return chosen or None
    except Exception:  # noqa: BLE001 - as today
        logger.debug("Could not hold a review's files", exc_info=True)
        return None


def held_section(held: Sequence[str], stage: str = "") -> str:
    """The request's lines naming the files its memory holds, and how to use them; "" for none. A review (the
    default) is told to judge them there; another reading stage (`READING_STAGES`) to work from them there."""
    if not held:
        return ""
    review = not stage or is_a_review_stage(stage)
    return (
        (HELD_MARK if review else HELD_TO_READ_MARK) + ", ".join(f"`{name}`" for name in held) + _HELD_END + "\n"
        "Each of these is in the project memory at the start of this message, whole and current, every line "
        + ("numbered: judge it there and cite its lines." if review else "numbered: work from it there.")
        + " Reading one of them again returns nothing new.\n" + OUTLINED
    )


def chosen_again(named: Sequence[str], written: Sequence[str], reads: Sequence[Sequence[Any]],
                 repo_root: str | Path) -> list[str]:
    """The files a stage's memory holds whole after a summary, most wanted first (LF.1288): those it wrote, the
    latest first; then those it read, most reads first, then the latest; then those its opening named, in its order.
    Only files `under_review` accepts: the product's code, configuration and tests, not documents, generated folders
    or the files the harness keeps; and not a throwaway the stage wrote for itself (`file_kinds.is_scratch`, LF.1400).
    Never raises: [].

    Measured on one medium run: a lead summarised 21 times re-read 20 files 12 times each - its memory held what the
    visit began with, and a summary deleted every file it had read since. And a test round that wrote a repro script
    held it first after its next summary, ahead of the route, schemas and tests it was reading."""
    try:
        from app.analysis.file_kinds import is_scratch

        order = list(reversed(list(dict.fromkeys(str(p) for p in written or ()))))
        counted = [(str(item[0]), int(item[1]), index) for index, item in enumerate(reads or ()) if len(item) >= 2]
        order += [path for path, _, _ in sorted(counted, key=lambda r: (-r[1], -r[2]))]
        order += [str(p) for p in named or ()]
        order = [p for p in dict.fromkeys(p.strip().lstrip("/") for p in order if p) if not is_scratch(p)]
        accepted = {path for path, _ in under_review(repo_root, order)}
        return [path for path in order if path in accepted]
    except Exception:  # noqa: BLE001 - the memory as it is
        logger.debug("Could not choose the files to hold again", exc_info=True)
        return []


def with_the_held_line(text: str, held: Sequence[str]) -> str:
    """`text` with the line of its request naming the files held (`held_section`) naming `held` instead; as it is
    when it has no such line."""
    for mark in (HELD_MARK, HELD_TO_READ_MARK):
        start = str(text).find(mark)
        if start < 0:
            continue
        start += len(mark)
        end = text.find(_HELD_END, start)
        if end < 0:
            return text
        return text[:start] + ", ".join(f"`{name}`" for name in held) + text[end:]
    return text


def held_named_in(opening: str) -> tuple[str, ...]:
    """The files a request says its memory holds (`held_section`), or () for a request as today."""
    text = str(opening or "")
    for mark in (HELD_MARK, HELD_TO_READ_MARK):
        start = text.find(mark)
        if start >= 0:
            start += len(mark)
            end = text.find(_HELD_END, start)
            return tuple(dict.fromkeys(_NAME.findall(text[start:end if end >= 0 else len(text)])))
    return ()


def with_the_files_held(request: dict[str, Any], held: Sequence[str] | None, stage: str = "") -> dict[str, Any]:
    """`request` with `held_section` added to its last message; as it is for none."""
    if held:
        last = request["messages"][-1]
        if isinstance(last.get("content"), str):
            last["content"] += "\n\n" + held_section(held, stage)
    return request


__all__ = [
    "HELD_MARK", "HELD_TO_READ_MARK", "NUMBERED_MARK", "NUMBERED_START", "NUMBERED_TO_READ", "READING_STAGES",
    "REVIEW_STAGES", "WRITING_STAGES", "chosen_again",
    "fits_as_today", "held_for_review", "held_named_in", "held_section", "holds_what_it_reads",
    "is_a_review_stage", "numbered", "numbered_heading", "opening_of", "under_review", "with_the_files_held",
    "with_the_held_line",
]
