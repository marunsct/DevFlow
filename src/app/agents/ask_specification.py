"""A bounded `ask_specification` tool for builders and fixers (plan CM.4, behind `ASK_SPECIFICATION`).

A builder that met a question its request did not answer guessed, or read
the whole specification to find the one paragraph that did. With the switch
on, it can ask. The answer comes by retrieval first - the answers already
given this run, the specification, the locked suite's criteria - and only
when none of them holds the question's words does one call put it to the
model as the architect, whose answer is kept (`ANSWERS_FILE`) so the next
asker retrieves it. Bounded, because a small model over-asks: at most
`MOST_PER_WORK_ORDER` per builder's stage, `MOST_PER_FIX` per fix stage and
`MOST_PER_RUN` in all.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `ASK_SPECIFICATION` set to on or off overrides this.
ON_BY_DEFAULT = False
MOST_PER_WORK_ORDER = 2
MOST_PER_FIX = 1
MOST_PER_RUN = 12
#: The architect's answers, kept in the workspace for the askers after.
ANSWERS_FILE = ".harness/answers.json"
SPECIFICATION = "docs/technical_specification.md"
_MOST_PASSAGES = 3
_MOST_PASSAGE_CHARS = 600
_MOST_SPEC_CHARS = 12_000
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_COMMON = frozenset("""what which where when there their this that with from have does should would could must into
about these those than then them they your will also each every other only such some more most like just make made
used uses using need needs""".split())

_lock = threading.Lock()
_asked: dict[str, dict[str, int]] = {}


def enabled() -> bool:
    return is_on("ASK_SPECIFICATION", ON_BY_DEFAULT)


def _answers(root: Path) -> list[dict[str, str]]:
    try:
        kept = json.loads((root / ANSWERS_FILE).read_text(encoding="utf-8"))
        return [a for a in kept if isinstance(a, dict)] if isinstance(kept, list) else []
    except (OSError, ValueError):
        return []


def _passages(root: Path) -> list[tuple[str, str]]:
    found = [("an answer given earlier", f"Q: {a.get('question')}\nA: {a.get('answer')}") for a in _answers(root)]
    try:
        text = (root / SPECIFICATION).read_text(encoding="utf-8", errors="replace")
        found += [("the specification", block.strip()) for block in re.split(r"\n\s*\n", text) if block.strip()]
    except OSError:
        pass
    try:
        from app.acceptance import suite

        found += [("the locked suite", f"{c.id}: {c.text}") for c in suite.criteria(root)]
    except Exception:  # noqa: BLE001
        pass
    return found


def retrieved(root: str | Path, question: str) -> list[str]:
    """The passages holding enough of the question's words, best first; [] on a miss."""
    words = {w.lower() for w in _WORD.findall(question)} - _COMMON
    if not words:
        return []
    needed = max(2, math.ceil(len(words) * 0.4))
    scored = []
    for source, passage in _passages(Path(root)):
        lower = passage.lower()
        score = sum(1 for w in words if w in lower)
        if score >= needed:
            scored.append((score, f"From {source}: {passage[:_MOST_PASSAGE_CHARS]}"))
    return [p for _, p in sorted(scored, key=lambda s: -s[0])[:_MOST_PASSAGES]]


def _refused(run_id: str | None, stage: str) -> str:
    """Why this ask is refused, or "" - and counts it when it is not."""
    most = MOST_PER_FIX if stage.startswith("defect_fix") else MOST_PER_WORK_ORDER
    with _lock:
        counts = _asked.setdefault(str(run_id or ""), {})
        if sum(counts.values()) >= MOST_PER_RUN:
            return f"This run has asked {MOST_PER_RUN} questions already; decide from the specification you were given."
        if counts.get(stage, 0) >= most:
            return f"This stage has asked its {most} question(s); decide from what the answers and the specification say."
        counts[stage] = counts.get(stage, 0) + 1
    return ""


def _the_architect_s_answer(root: Path, model: Any, question: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.observability.direct_calls import config_for_this_run

    try:
        specification = (root / SPECIFICATION).read_text(encoding="utf-8", errors="replace")[:_MOST_SPEC_CHARS]
    except OSError:
        specification = ""
    from app.agents.thinking import without_reasoning

    # Without reasoning: on a server that reasons by default an 800-token
    # reply was reasoning to its end, and the builder got no answer.
    reply = without_reasoning(model).invoke([
        SystemMessage(content="You are the principal architect of this product. You answer a builder's question "
                              "from the specification; where it does not say, you decide, keep the decision "
                              "consistent with it, and say that it is a decision."),
        HumanMessage(content=f"The specification:\n{specification}\n\nThe question: {question}\n\n"
                             "Answer in at most five sentences."),
    ], max_tokens=800, **config_for_this_run("ask_specification"))
    content = getattr(reply, "content", "")
    from app.agents.model_output import strip_reasoning

    return strip_reasoning(content if isinstance(content, str) else str(content)).strip()


def build_tool(repo_root: str | Path, model: Any = None) -> Any:
    """The `ask_specification` tool for one specialist agent."""
    from langchain_core.tools import tool

    from app.observability import transcript

    root = Path(repo_root)

    @tool
    def ask_specification(question: str) -> dict[str, Any]:
        """Ask a question your request and the specification you were given do not answer.

        Use it rarely: for an interface, a rule or a behaviour you would otherwise have to guess.
        Answered from the specification, the locked suite and earlier answers first, and by the
        architect only when none of them says. A stage may ask once or twice; the run, a dozen times.

        Args:
            question: one question, naming what it is about.
        """
        refused = _refused(transcript._run_id_from_config(), transcript._stage_from_config(""))
        if refused:
            return {"error": refused}
        found = retrieved(root, question)
        if found:
            return {"answer_from": "what is written already", "passages": found}
        if model is None or not hasattr(model, "invoke"):
            return {"answer_from": "nothing", "answer": "Nothing written answers it; decide, and name the decision in your report."}
        try:
            answer = _the_architect_s_answer(root, model, question)
        except Exception:  # noqa: BLE001
            logger.warning("The architect could not be asked", exc_info=True)
            answer = ""
        if not answer:
            return {"answer_from": "nothing", "answer": "Nothing written answers it; decide, and name the decision in your report."}
        try:
            # Under the lock and through a temporary file: six builders asking at
            # once lost answers and left the file unreadable.
            import os as _os

            target = root / ANSWERS_FILE
            with _lock:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_text(json.dumps([*_answers(root), {"question": question, "answer": answer}], indent=1),
                                     encoding="utf-8")
                _os.replace(temporary, target)
        except OSError:
            pass
        return {"answer_from": "the architect", "answer": answer}

    return ask_specification


__all__ = ["ANSWERS_FILE", "MOST_PER_FIX", "MOST_PER_RUN", "MOST_PER_WORK_ORDER", "ON_BY_DEFAULT", "build_tool",
           "enabled", "retrieved"]
