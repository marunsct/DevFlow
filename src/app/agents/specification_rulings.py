"""A contradiction the design review leaves open is settled once, before anything is built on it (behind `SETTLE_SPEC_CONTRADICTIONS`).

Measured on one run: the review said the specification contradicted itself about one route's reply, the revision limit
passed, and the finding was recorded as a known risk. A unit test then took one side and a locked acceptance test the
other, at least six fixes were reverted, and the run took about 2.5 times as long. Each later stage had read the same
two statements and chosen for itself.

So one call, when a design review ends with findings open, is given those findings, the specification and the brief.
For each contradiction it quotes both statements and says which stands. The harness keeps a ruling only if both
quotes are in the specification word for word, records each as a decision, and every later stage reads the rulings
with the shared facts. The specification document is left as written: a decision record says what was settled and why,
and the document stays what the review read. Any failure leaves the run as it would have been without this.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `SETTLE_SPEC_CONTRADICTIONS` set to on or off overrides this; off until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = (
    "When the design review ends with findings open, one model call settles any contradiction inside the specification: "
    "both statements quoted word for word, which stands and why. Each ruling is a decision record, and later stages "
    "read it with the shared facts."
)

MOST_RULINGS = 5
MOST_OUTPUT_TOKENS = 2_000
#: Kept beside the decision log: a fact for later stages, and the proof the one call was made.
RULINGS_FILE = ".harness/specification_rulings.json"
_MOST_SPECIFICATION_CHARS = 80_000
_MOST_BRIEF_CHARS = 8_000
_MOST_FINDING_CHARS = 1_000
#: A quote shorter than this could be found by chance anywhere in a specification.
_LEAST_QUOTE_CHARS = 8
#: A longer one is no single statement, and every later request carries it.
_MOST_QUOTE_CHARS = 500
_MOST_WHY_CHARS = 400

HEADING = "--- What the specification left contradictory, and which side stands ---"


class Ruling(BaseModel):
    finding: int = Field(default=0, description="The number of the open finding this settles.")
    first_statement: str = Field(default="", description="One of the two conflicting statements, copied word for word from the specification.")
    second_statement: str = Field(default="", description="The other statement, copied word for word from the specification.")
    stands: str = Field(default="", description="`first` or `second`: the statement that holds.")
    why: str = Field(default="", description="One sentence: why that one holds.")


class Rulings(BaseModel):
    rulings: list[Ruling] = Field(default_factory=list)


def enabled() -> bool:
    return is_on("SETTLE_SPEC_CONTRADICTIONS", ON_BY_DEFAULT)


def _plain(text: str) -> str:
    """`text` with each run of white space one space: a quote keeps its words, not the document's line breaks."""
    return " ".join(str(text or "").split())


def _flattened(value: Any) -> list[str]:
    """Every piece of text in a specification's fields, without the escaping its JSON form would put in a quote."""
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            inner = _flattened(item)
            if inner:
                lines += [f"[{key}]", *inner]
        return lines
    if isinstance(value, (list, tuple)):
        return [line for item in value for line in _flattened(item)]
    return [str(value)] if value not in (None, "") else []


def _the_specification(specification: Any, root: str | Path) -> str:
    """The specification as text, its fields if it has them and else the document; "" when neither is there."""
    if hasattr(specification, "model_dump"):
        text = "\n".join(_flattened(specification.model_dump()))
    elif isinstance(specification, dict):
        text = "\n".join(_flattened(specification))
    else:
        path = Path(root) / "docs" / "technical_specification.md"
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    return text[:_MOST_SPECIFICATION_CHARS]


def the_request(findings: list[str], specification: str, brief: str, setup: Sequence[str] = ()) -> str:
    """What the one call is asked."""
    numbered = "\n".join(f"{n}. {finding[:_MOST_FINDING_CHARS]}" for n, finding in enumerate(findings, start=1))
    # Measured on one run: the review called the setup's own start command impossible, and the call, told nothing of
    # the setup, ruled for another tool. Only its quotes, taken from the finding, stopped the ruling.
    the_setup = (
        "--- What the setup decides (the harness's; what the setup decides is not open) ---\n"
        + "\n".join(setup)
        + "\nNo ruling goes against these lines: a statement that disagrees with them does not stand, whatever a "
        "finding says of them.\n\n"
    ) if setup else ""
    return (
        f"The design review of this specification ended with these findings open:\n{numbered}\n\n"
        f"--- The brief the specification was written from ---\n{brief[:_MOST_BRIEF_CHARS]}\n\n"
        f"{the_setup}"
        f"--- The specification ---\n{specification}\n\n"
        "Some open findings may say that two parts of the specification contradict each other: following one makes "
        "following the other impossible. Settle only those; say nothing of any other finding. For each one, copy the "
        "two conflicting statements exactly as the specification writes them, from the specification and not from the "
        "findings, each a short single statement, and say "
        "which stands: the one the brief's own words support, and where the brief does not decide it, the one that "
        f"allows more. At most {MOST_RULINGS} rulings.\n"
        "Answer with one JSON object and nothing else: {\"rulings\": [{\"finding\": <the finding's number>, "
        "\"first_statement\": \"...\", \"second_statement\": \"...\", \"stands\": \"first\" or \"second\", "
        "\"why\": \"one sentence\"}]}. With no contradiction among them, answer {\"rulings\": []}."
    )


#: What a model puts before a statement it quotes: its section's name, then a "...".
_A_LABEL_BEFORE_A_QUOTE = re.compile(r"^(?:[^:.]{1,60}:\s*)?(?:\.\.\.|…)?\s*")


def _as_quoted(statement: str, text: str) -> str:
    """`statement` in plain form, without the section's name or "..." before or after it when only that keeps it out of `text`.

    Measured on one run: a real contradiction, both statements real, each with its section's name before it, and the
    ruling was rejected. What is left must still be in the specification word for word.
    """
    plain = _plain(statement)
    if plain in text:
        return plain
    bare = _A_LABEL_BEFORE_A_QUOTE.sub("", plain, count=1).removesuffix("...").removesuffix("…").strip()
    return bare if bare in text else plain


def _in_the_specification(quote: str, text: str, specification: str) -> bool:
    """Whether a quote is the specification's, word for word or by the sentence matcher the suite dispute uses.

    Measured on one run: a right ruling quoted a function's signature without the specification's backticks, the
    word-for-word check rejected it, and the contradiction stayed open; the same fault was fixed for the dispute (LF.543).
    """
    if quote in text:
        return True
    from app.agents.suite_dispute import _the_standard_holds

    return _the_standard_holds(quote, specification)


def verified(answer: Rulings, specification: str, findings: list[str]) -> list[Ruling]:
    """The rulings whose both quotes are in the specification word for word and that settle an open finding, at most `MOST_RULINGS`."""
    text = _plain(specification)
    kept: list[Ruling] = []
    seen: set[frozenset[str]] = set()
    for ruling in answer.rulings[:MOST_RULINGS]:
        first, second = _as_quoted(ruling.first_statement, text), _as_quoted(ruling.second_statement, text)
        ruling = ruling.model_copy(update={"first_statement": first, "second_statement": second})
        problem = (
            "it names no open finding" if not 1 <= ruling.finding <= len(findings)
            else "it does not say which statement stands" if ruling.stands.strip().lower() not in ("first", "second")
            else "it gives no reason" if not ruling.why.strip()
            else "a quote is too short or too long to be one statement"
            if not all(_LEAST_QUOTE_CHARS <= len(q) <= _MOST_QUOTE_CHARS for q in (first, second))
            else "one quote is inside the other" if first in second or second in first
            else "a quote is not in the specification word for word"
            if not (_in_the_specification(first, text, specification) and _in_the_specification(second, text, specification))
            else "it repeats a ruling" if frozenset((first, second)) in seen
            else ""
        )
        if problem:
            logger.warning("A ruling on the specification was rejected: %s", problem)
            continue
        seen.add(frozenset((first, second)))
        kept.append(ruling)
    return kept


def _asked(root: str | Path) -> bool:
    return (Path(root) / RULINGS_FILE).is_file()


def _save(root: str | Path, rulings: list[dict[str, Any]]) -> None:
    path = Path(root) / RULINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rulings": rulings}, indent=2), encoding="utf-8")


def _the_call(model: Any, request: str) -> Rulings | None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.answered_in_parts import _read
    from app.agents.thinking import without_reasoning
    from app.observability.direct_calls import config_for_this_run

    reply = without_reasoning(model).invoke([
        SystemMessage(content="You settle contradictions inside a software specification. You answer with one JSON object."),
        HumanMessage(content=request),
    ], max_tokens=MOST_OUTPUT_TOKENS, **config_for_this_run("escalation"))
    content = getattr(reply, "content", "")
    return _read(content if isinstance(content, str) else str(content), Rulings)


def settle(state: Any, update: dict[str, Any], model: Any, findings: list[str]) -> list[dict[str, Any]]:
    """Rule on the contradictions among the open `findings`, once in a run, recording each ruling; what was kept. Never raises."""
    if not enabled() or model is None or not findings:
        return []
    try:
        from app.decisions import record_decision

        root = state["repository"].root_path
        if _asked(root):
            return []
        specification = _the_specification(state.get("technical_specification"), root)
        if not specification.strip():
            return []
        # Written before the call, so a restart in the middle of it cannot make it a second call.
        _save(root, [])
        brief = str(getattr(state.get("document"), "text", "") or "")
        from app.graph.workflow import _the_scaffold_s_facts

        answer = _the_call(model, the_request(findings, specification, brief, _the_scaffold_s_facts(state)))
        kept: list[dict[str, Any]] = []
        for ruling in verified(answer, specification, findings) if answer is not None else []:
            first_stands = ruling.stands.strip().lower() == "first"
            stands = _plain(ruling.first_statement if first_stands else ruling.second_statement)
            gives_way = _plain(ruling.second_statement if first_stands else ruling.first_statement)
            why = _plain(ruling.why)[:_MOST_WHY_CHARS]
            record = record_decision(
                state, update, point="technical_specification",
                question="The specification contradicts itself: which statement stands?",
                options=[stands, gives_way], decision=stands, rationale=why, decided_by="auto",
            )
            kept.append({"decision": record["id"], "finding": ruling.finding, "stands": stands,
                         "gives_way": gives_way, "why": why})
        _save(root, kept)
        logger.info("The specification's contradictions: %d ruling(s) kept", len(kept))
        return kept
    except Exception:  # noqa: BLE001 - the run goes on with its findings open, as it would have
        logger.warning("Could not settle the specification's contradictions", exc_info=True)
        return []


def forget(root: str | Path) -> None:
    """The rulings no longer hold: the architect is revising the specification they quote. The call stays spent. Never raises."""
    try:
        if _asked(root):
            _save(root, [])
    except Exception:  # noqa: BLE001 - as above
        logger.debug("Could not clear the specification's rulings", exc_info=True)


def _kept(root: str | Path | None) -> list[dict[str, Any]]:
    if not root or not enabled():
        return []
    try:
        path = Path(root) / RULINGS_FILE
        if not path.is_file():
            return []
        return [r for r in json.loads(path.read_text(encoding="utf-8")).get("rulings") or [] if isinstance(r, dict)]
    except Exception:  # noqa: BLE001 - a request without the rulings is the request as it was
        logger.debug("Could not read the specification's rulings", exc_info=True)
        return []


def the_rulings_section(root: str | Path | None) -> str:
    """The block a request carries the rulings in; "" when there are none or it is off. Never raises."""
    rulings = _kept(root)
    if not rulings:
        return ""
    return f"\n\n{HEADING}\n" + "\n".join(
        f"- {r.get('decision')}: \"{r.get('stands')}\" stands, over \"{r.get('gives_way')}\". {r.get('why')} "
        "Build and test to the statement that stands."
        for r in rulings
    ) + "\n"


def with_the_rulings(request: dict[str, Any], root: str | Path | None) -> dict[str, Any]:
    """`request` with the rulings appended to its last message, for a stage the shared facts do not reach. Never raises."""
    try:
        section = the_rulings_section(root)
        if section and request.get("messages"):
            last = request["messages"][-1]
            if isinstance(last, dict) and isinstance(last.get("content"), str):
                last["content"] += section
    except Exception:  # noqa: BLE001 - as above
        logger.debug("Could not add the rulings to a request", exc_info=True)
    return request


__all__ = [
    "MOST_RULINGS", "ON_BY_DEFAULT", "RULINGS_FILE", "Ruling", "Rulings", "enabled", "explanation", "forget", "settle",
    "the_request", "the_rulings_section", "verified", "with_the_rulings",
]
