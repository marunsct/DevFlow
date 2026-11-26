"""While reading is withheld and decided file by file, a file's lines run once in a stage visit (LF.1577).

Reads decided file by file (TR.2, LF.1517; thinking off, LF.1527; a command that only reads, LF.1525) refused only
what the conversation the call sends still holds. A summary, or a request fitted to the model's context, takes old
results out, so after each one the same lines counted as never read and ran again, without bound. Measured on a
medium run in parallel mode: a backend builder with thinking off made 150 reads in one stage, 134 of them run while
reading was withheld - `routes.py` 76 times, `schemas.py` 27, `conftest.py` 12 - cycling the same windows across 14
fitted requests, until the stage reached its step limit and the run failed. Before LF.1527 those reads were refused
and the stage answered.

So the reads run while reading is withheld are remembered for the stage visit, in its stage memory (keyed by the
visit's own conversation, kept across an approval pause and across a summary; a restart on a fresh conversation is a
new visit):

- a read whose lines were all run already in this visit while withheld is refused by name, saying so, until the
  stage writes that file;
- one file is read at most `MOST_READS_OF_ONE_FILE` times while withheld in a visit;
- the visit runs at most `MOST_READS` reads while withheld, after which the read tool is withheld whole
  (`settled_answer`), as before LF.1527.

A read made before reading was withheld is not remembered here: TR.2's measured case - a test file read once,
summarised away, and read once more after the withholding - still runs.
"""
from __future__ import annotations

from typing import Any

#: Stage memory: the reads run while reading was withheld in this visit.
PURPOSE = "reads run while withheld"

#: Reads of one file run while reading is withheld, in one visit: a file of up to about 1,600 lines in the read tool's
#: default windows. The measured builder ran 76 reads of one file.
MOST_READS_OF_ONE_FILE = 4

#: Reads run while reading is withheld, in one visit, before the read tool is withheld whole. The measured builder's
#: visit with thinking off from its first call read eleven distinct windows of seven files before it first repeated
#: one; it went on to 134.
MOST_READS = 16



def _path(path: Any) -> str:
    cleaned = str(path or "").strip().replace("\\", "/")
    while cleaned.startswith(("./", "/")):
        cleaned = cleaned[2:] if cleaned.startswith("./") else cleaned[1:]
    return cleaned


def _span(offset: int, limit: int) -> tuple[int, int] | None:
    """The lines a read asks for, [first, last); None for a read of a file's end (`tail`), known by its key alone."""
    from app.agents.workspace_paths import DEFAULT_READ_LINES

    if offset < 0:
        return None
    return offset, offset + (limit or DEFAULT_READ_LINES)


def _covered(span: tuple[int, int], spans: list[list[int]]) -> bool:
    """Whether every line of `span` lies in one of `spans`."""
    first, last = span
    for start, end in sorted((int(a), int(b)) for a, b in spans):
        if start > first:
            return False
        if end > first:
            first = end
        if first >= last:
            return True
    return first >= last


def _memory() -> dict:
    from app.agents.stage_memory import store

    return store(PURPOSE, {})


def spent() -> bool:
    """Whether this visit has run its most reads while reading was withheld: the read tool goes whole from here."""
    try:
        return int(_memory().get("ran") or 0) >= MOST_READS
    except Exception:  # noqa: BLE001 - then reads are decided as they come
        return False


def _already_read(path: str) -> str:
    from app.agents.workspace_backend import READ_REFUSED_MARKER

    return (f"{READ_REFUSED_MARKER} '{path}' again: these lines were already read in this stage while reading was "
            "withheld, and the file has not been written since. A summary may have taken their text out of this "
            "conversation; they are not given again. Use what you took from them: make the change, run the check, "
            "or say in `blockers` what is missing. A file not yet read in this stage can still be read.")


def _read_its_most(path: str, times: int) -> str:
    from app.agents.workspace_backend import READ_REFUSED_MARKER

    return (f"{READ_REFUSED_MARKER} '{path}' again: it was already read {times} times in this stage while reading was "
            "withheld, the most one file is given. Use what you took from it: make the change, run the check, or say "
            "in `blockers` what is missing.")


def _reading_spent(path: str, times: int) -> str:
    from app.agents.workspace_backend import READ_REFUSED_MARKER

    return (f"{READ_REFUSED_MARKER} '{path}': {times} reads have run in this stage while reading was withheld, the "
            "most a stage is given, so reading is withheld for the rest of it. Make the change, run the check, or "
            "return your structured response, and say in `blockers` what is missing.")


def refusal(path: str, offset: int = 0, limit: int = 0) -> tuple[str, str] | None:
    """(refusal, how it was decided) for a read decided file by file that may not run; None when it runs, and it is
    then remembered as run. `limit` 0 is the read tool's default window; a negative `offset`, the file's last lines."""
    from app.agents.withheld_records import ALREADY_READ, WITHHELD_WHOLE

    try:
        memory = _memory()
        name = _path(path)
        files = memory.setdefault("files", {})
        record = files.setdefault(name, {"times": 0, "spans": [], "keys": []})
        ran = int(memory.get("ran") or 0)
        if ran >= MOST_READS:
            return _reading_spent(name, ran), WITHHELD_WHOLE
        span = _span(int(offset or 0), int(limit or 0))
        key = [int(offset or 0), int(limit or 0)]
        if (span is not None and _covered(span, record["spans"])) or key in record["keys"]:
            return _already_read(name), ALREADY_READ
        if record["times"] >= MOST_READS_OF_ONE_FILE:
            return _read_its_most(name, record["times"]), ALREADY_READ
        record["times"] += 1
        if span is not None:
            record["spans"].append(list(span))
        record["keys"].append(key)
        memory["ran"] = ran + 1
        return None
    except Exception:  # noqa: BLE001 - then the read runs, as before
        return None


def written(path: str) -> None:
    """The stage wrote `path`: its lines are new, so a read of them runs again (still counted against the bounds)."""
    try:
        record = (_memory().get("files") or {}).get(_path(path))
        if record is not None:
            record["spans"], record["keys"] = [], []
    except Exception:  # noqa: BLE001 - a memo never fails a write
        pass


__all__ = ["MOST_READS", "MOST_READS_OF_ONE_FILE", "PURPOSE", "refusal", "spent", "written"]
