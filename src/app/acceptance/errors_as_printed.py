"""A defect a model raises carries the error as its stage's own commands printed it (plan FX.8, LF.1412).

Measured on a medium run: the first test round's command results held, word for word,
`AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'`, and the round raised the defect as
"SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures" - the error paraphrased away. No fixer was shown
the line, and the lookup that runs for a stuck defect (`app.graph.stuck_lookup`) needs an error line to search: over
the run it never built a query.

When a test round or a code review raises a defect whose own text states no error, the harness reads the commands that
stage ran (the run's transcript), takes the lines that state an error (`what_went_wrong`), and attaches those the
defect's own words match - at least two of its distinctive words in the line - to its actual behaviour, as printed.
Nothing is attached when no line matches: a guess would mislead the fixer more than no line. Never raises.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

#: How the attached lines are introduced in a defect's actual behaviour.
HEADING = "The error as the stage's own commands printed it:"
#: Lines attached to one defect, at most, and their characters.
MOST_LINES = 3
MOST_CHARACTERS = 600
#: Distinctive words of the defect a line must hold to be its error.
LEAST_WORDS_MATCHED = 2
#: A word of a defect: four or more letters, digits or underscores, starting with a letter.
_A_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,}")
#: Words too common in a defect's account to tell one error from another.
_COMMON = frozenset("""
about above after again against also because been before being below between both cannot could does doing down during
each error errors fail failed failing fails file files from further have having here into itself just line lines more
most must need needs once only other same should since some still such than that their them then there these they
this those through under until very were what when where which while will with within without would test tests
returns return value values instead make makes made given expected actual behaviour behavior every case cases using
used uses
""".split())
#: A runner's own marker before a stated error, e.g. pytest's `E   ` gutter.
_A_GUTTER = re.compile(r"^[A-Z]\s{2,}")
#: What differs between two printings of one error: addresses and numbers.
_VARYING = re.compile(r"0x[0-9a-fA-F]+|\d+")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _A_WORD.findall(str(text or "")) if w.lower() not in _COMMON}


def _states_an_error(text: str) -> bool:
    """Whether `text` already states an error a person could search for."""
    from app.acceptance.what_went_wrong import the_errors_stated

    return bool(the_errors_stated(text))


def error_lines(outputs: Iterable[str]) -> list[str]:
    """Each line stating an error in `outputs`, frames left out, each once and in order."""
    from app.acceptance.what_went_wrong import _A_FRAME, _AN_ERROR

    found: dict[str, str] = {}
    for output in outputs:
        for line in str(output or "").splitlines():
            if not line.strip() or _A_FRAME.search(line) or not _AN_ERROR.search(line):
                continue
            said = " ".join(_A_GUTTER.sub("", line.strip()).split())[:300]
            found.setdefault(_VARYING.sub("#", said), said)
    return list(found.values())


def matching(defect: Any, lines: Sequence[str]) -> list[str]:
    """The lines of `lines` the defect's description and actual behaviour match, most words matched first."""
    words = _words(f"{getattr(defect, 'description', '') or ''} {getattr(defect, 'actual_behavior', '') or ''}")
    if not words:
        return []
    scored = []
    for at, line in enumerate(lines):
        lowered = line.lower()
        hits = sum(1 for word in words if word in lowered)
        if hits >= LEAST_WORDS_MATCHED:
            scored.append((-hits, at, line))
    kept: list[str] = []
    total = 0
    for _, _, line in sorted(scored):
        if len(kept) >= MOST_LINES or total + len(line) > MOST_CHARACTERS:
            break
        kept.append(line)
        total += len(line) + 1
    return kept


def with_the_error(defect: Any, lines: Sequence[str]) -> Any:
    """`defect` with the error lines of `lines` its words match added to its actual behaviour; the defect itself when
    its text already states an error, or no line matches."""
    text = f"{getattr(defect, 'description', '') or ''}\n{getattr(defect, 'actual_behavior', '') or ''}"
    if HEADING in text or _states_an_error(text):
        return defect
    found = matching(defect, lines)
    if not found:
        return defect
    actual = str(getattr(defect, "actual_behavior", "") or "").rstrip()
    added = HEADING + "\n" + "\n".join(found)
    try:
        return defect.model_copy(update={"actual_behavior": f"{actual}\n{added}" if actual else added})
    except Exception:  # noqa: BLE001 - not a model: kept as it is
        return defect


def the_error_it_carries(defect: Any) -> str:
    """The first line attached under `HEADING`, or ""."""
    _, marked, after = str(getattr(defect, "actual_behavior", "") or "").partition(HEADING + "\n")
    return after.splitlines()[0] if marked and after else ""


def _the_output_of(content: Any) -> str:
    """What a command's result printed: its standard output, error output and error, or the result's text."""
    text = str(content or "")
    try:
        result = json.loads(text)
    except ValueError:
        # A result the transcript cut short is no longer JSON: its escaped text, read as lines.
        return text.replace("\\n", "\n").replace('\\"', '"')
    if not isinstance(result, dict):
        return text
    return "\n".join(str(result.get(key) or "") for key in ("stdout", "stderr", "error", "output") if result.get(key))


def the_stage_s_outputs(run_id: str | None, stage: str) -> list[str]:
    """What the commands of `stage`'s latest visit printed, from the run's transcript, oldest first."""
    if not run_id or not stage:
        return []
    from app.observability.transcript import read_live

    entries = read_live(run_id, {"tool_call", "tool_result", "model_request"})
    # Its latest visit: what follows the last record of another stage before its own last record (a sprint planned
    # again runs a round of the same name again, and that round's results are another product's).
    own = [at for at, entry in enumerate(entries) if entry.get("stage") == stage]
    if not own:
        return []
    before = [at for at, entry in enumerate(entries[:own[-1]]) if entry.get("stage") != stage]
    start = before[-1] + 1 if before else 0
    return [_the_output_of(entry.get("content")) for entry in entries[start:]
            if entry.get("stage") == stage and entry.get("kind") == "tool_result"]


def attached(defects: Sequence[Any], run_id: str | None, stage: str, *, source: str) -> list[Any]:
    """`defects`, each raised by `source` given the error its words match in `stage`'s own command results. Never
    raises: the defects as they were."""
    try:
        if not any(str(getattr(d, "source", "") or "") == source for d in defects):
            return list(defects)
        lines = error_lines(the_stage_s_outputs(run_id, stage))
        if not lines:
            return list(defects)
        return [with_the_error(d, lines) if str(getattr(d, "source", "") or "") == source else d for d in defects]
    except Exception:  # noqa: BLE001 - the defects as raised
        logger.debug("Could not attach the printed errors to the raised defects", exc_info=True)
        return list(defects)


__all__ = ["HEADING", "attached", "error_lines", "matching", "the_error_it_carries", "the_stage_s_outputs",
           "with_the_error"]
