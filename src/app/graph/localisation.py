"""Where a defect is, asked once and cheaply before any rewrite (plan AY step 1, behind `LOCALISE_FIRST`).

The rewrite takes its files from the defect and its failure text
(`rewritten_fixes.files_to_fix`). When that names no file the defect went to
the 40-call agent loop to find them by reading; when it names many, each was
rewritten. Separating where from what is how the strongest open repair
harnesses work (Agentless, test-selected rollouts). With the switch on, one
call without reasoning, at most `MOST_OUTPUT_TOKENS`, is given the failure
and the project's map of definitions and answers `{files, symbols,
hypothesis}`; a file is kept only if it exists, may be written, and - when
symbols are named - holds one of them. The hypothesis is logged as the
defect's diagnosis.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `LOCALISE_FIRST` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Files a rewrite takes without asking where the defect is.
MOST_FILES_UNASKED = 2
#: Files kept from the answer, at most.
MOST_FILES = 3
MOST_OUTPUT_TOKENS = 1_500
_MOST_FAILURE_CHARS = 6_000
_MOST_MAP_CHARS = 8_000


class Localisation(BaseModel):
    files: list[str] = Field(default_factory=list, description="Workspace-relative paths of the files to change, most likely first.")
    symbols: list[str] = Field(default_factory=list, description="Functions, classes or settings the cause is in.")
    hypothesis: str = Field(default="", description="One sentence: what is wrong, and where.")


def enabled() -> bool:
    return is_on("LOCALISE_FIRST", ON_BY_DEFAULT)


def _the_map(root: Path, focus: str = "") -> str:
    """What each file defines, within `_MOST_MAP_CHARS`, the files the failure points at first when not all fit.

    It was cut at the budget in path order, so on a large project the
    localiser saw the first folders alphabetically and none of the rest.
    """
    try:
        from app.agents.project_memory import current, importance_of, map_of

        files = {p: t for p, t in current(root).items() if not p.startswith(("docs/", ".harness/"))}
        return map_of(files, focus=focus, most_characters=_MOST_MAP_CHARS,
                      importance=importance_of(root) if sum(map(len, files.values())) > _MOST_MAP_CHARS else None,
                      root=root)
    except Exception:  # noqa: BLE001
        return ""


def _confirmed(root: Path, answer: Localisation, may_write: Callable[[str], bool]) -> list[str]:
    kept = []
    symbols = [s.strip() for s in answer.symbols if s.strip()]
    for name in answer.files:
        relative = str(name).strip().removeprefix("./").lstrip("/")
        path = root / relative
        if not relative or not path.is_file() or not may_write(relative):
            continue
        if symbols:
            text = path.read_text(encoding="utf-8", errors="replace")
            if not any(symbol in text for symbol in symbols):
                continue
        kept.append(relative)
    return list(dict.fromkeys(kept))[:MOST_FILES]


def localised(defect: Any, failure: str, root: str | Path, model: Any, found: list[str],
              may_write: Callable[[str], bool]) -> list[str]:
    """The files to rewrite: `found` when off or few enough, else the ones the localisation confirms. Never raises."""
    if not enabled() or model is None or 1 <= len(found) <= MOST_FILES_UNASKED:
        return found
    return asked(defect, failure, root, model, may_write, found) or found


def asked(defect: Any, failure: str, root: str | Path, model: Any, may_write: Callable[[str], bool],
          found: list[str] = ()) -> list[str]:
    """The files the one localisation call names and the workspace confirms - each exists, may be written and holds
    a symbol it names; [] when it names none or cannot be asked. Whatever `LOCALISE_FIRST` says: a fixer whose
    failure no route and no stack frame places asks it (FX.2, `app.graph.localised_fix`). Never raises."""
    if model is None:
        return []
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.agents.answered_in_parts import _read
        from app.agents.thinking import without_reasoning
        from app.observability.direct_calls import config_for_this_run

        base = Path(root)
        focus = "\n".join([*found, str(getattr(defect, "description", "")), str(failure)])
        prompt = (
            f"A defect: {getattr(defect, 'description', '')}\nExpected: {getattr(defect, 'expected_behavior', '')}\n"
            f"Actual: {getattr(defect, 'actual_behavior', '')}\n\nWhat failed:\n{str(failure)[:_MOST_FAILURE_CHARS]}\n\n"
            f"What each file of the project defines:\n{_the_map(base, focus)}\n\n"
            + (f"The failure text names these files: {', '.join(found)}.\n" if found else "")
            + f"Name at most {MOST_FILES} files whose change fixes this, the symbols in them the cause is in, and "
            "one sentence saying what is wrong. Answer with one JSON object with the fields `files`, `symbols` "
            "and `hypothesis`, nothing else."
        )
        reply = without_reasoning(model).invoke([
            SystemMessage(content="You find where in a codebase a failure is caused. You answer with one JSON object."),
            HumanMessage(content=prompt),
        ], max_tokens=MOST_OUTPUT_TOKENS, **config_for_this_run("defect_fix"))
        from app.models.reply_text import reply_text

        answer = _read(reply_text(reply), Localisation)
        if answer is None:
            return []
        kept = _confirmed(base, answer, may_write)
        if kept:
            logger.info("Localised %s to %s: %s", str(getattr(defect, "description", ""))[:80], ", ".join(kept),
                        " ".join(answer.hypothesis.split())[:200])
        return kept
    except Exception:  # noqa: BLE001 - nothing confirmed
        logger.debug("Could not localise the defect", exc_info=True)
        return []


#: A diagnosis may reason at length; its answer is one short object.
MOST_DIAGNOSIS_TOKENS = 6_000
#: What a diagnosis call is told it is: the audit's switch-firing check reads it in the request.
DIAGNOSIS_ROLE = ("You diagnose why earlier attempts to fix a failure did not work. You change nothing; you answer "
                  "with one JSON object.")


def diagnosis(defect: Any, failure: str, root: str | Path, model: Any, tried: str) -> str:
    """One diagnosis-only call for a cause earlier attempts did not fix (deep review 2026-11-18, item 1.4): no tools,
    reasoning allowed, the failure, what was tried and the project's map; its hypothesis and the files it names, or "".

    The localisation's question and answer, asked of a cause that has already failed twice: where it is, and why
    what was tried did not reach it. Never raises.
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.agents.answered_in_parts import _read
        from app.observability.direct_calls import config_for_this_run

        base = Path(root)
        focus = "\n".join([str(getattr(defect, "description", "")), str(failure)])
        prompt = (
            f"A defect: {getattr(defect, 'description', '')}\nExpected: {getattr(defect, 'expected_behavior', '')}\n"
            f"Actual: {getattr(defect, 'actual_behavior', '')}\n\nWhat failed:\n{str(failure)[:_MOST_FAILURE_CHARS]}\n\n"
            f"What was tried on it before, and how each ended:\n{str(tried).strip()[:_MOST_FAILURE_CHARS]}\n\n"
            f"What each file of the project defines:\n{_the_map(base, focus)}\n\n"
            "Those attempts did not fix it. Say why: what they changed that could not reach the cause, and where the "
            f"cause really is. Name at most {MOST_FILES} files and the symbols in them, and in `hypothesis` two or three "
            "sentences a fixer can act on. Answer with one JSON object with the fields `files`, `symbols` and "
            "`hypothesis`, nothing else."
        )
        reply = model.invoke([SystemMessage(content=DIAGNOSIS_ROLE), HumanMessage(content=prompt)],
                             max_tokens=MOST_DIAGNOSIS_TOKENS, **config_for_this_run("defect_fix"))
        from app.models.reply_text import reply_text

        text = reply_text(reply)
        answer = _read(text, Localisation)
        if answer is None:
            return " ".join(text.split())[:600]
        where = [f for f in answer.files if (base / str(f).strip().lstrip("/")).is_file()][:MOST_FILES]
        said = " ".join(answer.hypothesis.split())
        return (said + (f" Files: {', '.join(where)}." if where else ""))[:600]
    except Exception:  # noqa: BLE001 - no diagnosis, the fixer goes on as before
        logger.debug("Could not diagnose the defect", exc_info=True)
        return ""


__all__ = ["Localisation", "MOST_FILES", "MOST_FILES_UNASKED", "ON_BY_DEFAULT", "asked", "diagnosis", "enabled",
           "localised"]
