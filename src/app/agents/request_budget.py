"""One input budget per request: a stage's request parts ordered and cut to what its model's window leaves (LF.1274).

Measured (deep review 2026-11-24, D.14): a 91,776-token slot reserves 32,000 for the reply, is summarised from about
43,000, and the specification alone was about 34,000 tokens; no one budget covered what a request carried. LF.1270
sized the agent-loop fixer's request; the rewrite path's one-file fix requests stayed at 84,000-99,000 characters on a
small static page and 75,000-97,000 on a small API, and every builder of a medium run's first sprint opened on 178,000
-197,000 characters, about 65,000 of them the whole specification beside the parts of it its request already quoted.

**The target** (`opening_target`): the opening request - and the project memory given with it - leaves room for
`WORKING_CALLS` working calls, each as large as one command's output may be, before the conversation is first
summarised (`ContextBudget.trigger_tokens`); at least `LEAST_OPENING_CHARACTERS`.

**The parts** (`Part`), each tagged:

- `INSTRUCTION`: the stage's own instruction. Never cut, never moved: those before every other part open the request,
  the rest close it.
- `EVIDENCE`: what this piece of work is about (a defect, what failed, the file to correct). Never cut; first.
- `KEPT`: what binds the work and is kept whole (earlier attempts as measured, fixes to keep, rulings). Next.
- `STANDING`: context that is the same whatever the work - the API, the facts, the specification, the project. Under
  `STANDING_HEADING`, each as its `cut` (cut to what the work touches) when it has one; still past the target, whole
  standing sections go, largest first, each named with where to read it (`Part.where`).

A request within its target is sent as it was built (`fit` is then not called: a small product's requests are as
before). `fit` says what it did (`Fitted`), and `noted` puts one `request_budget` record in the run's transcript,
which `scripts/loop/effects.py` counts. Fixers (both paths) are always held to the budget; every other stage's memory
only with `REQUEST_BUDGET_FOR_EVERY_STAGE` on (`for_every_stage_switch`, off until measured) - off, its record says
what would have been cut (`applied` false).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Working calls the opening request leaves room for before the conversation is first summarised.
WORKING_CALLS = 10
#: The smallest target, in characters, whatever the window: below it a stage is shown too little to act on.
LEAST_OPENING_CHARACTERS = 24_000
#: The share of the target the project memory keeps past it, at least: the files the evidence names.
MEMORY_LEAST_SHARE = 0.25

#: Where a fitted request's standing context begins; what comes before it is the work's evidence and what is kept.
STANDING_HEADING = ("--- Around this defect: the setup, the API and the facts, cut to what it touches (read the rest "
                    "when you need it) ---")

EVIDENCE, KEPT, STANDING, INSTRUCTION = "evidence", "kept", "standing", "instruction"

#: The transcript record of one request checked against its budget.
RECORD_KIND = "request_budget"
#: What an applied record of `REQUEST_BUDGET_FOR_EVERY_STAGE` says, which the switch-firing check reads.
SAID_FOR_EVERY_STAGE = "A stage's memory was held to its request's input budget"


class _ForEveryStage:
    """`REQUEST_BUDGET_FOR_EVERY_STAGE` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A stage other than a fixer whose opening request and project memory are past its input budget "
                   "is given the memory within what the budget leaves beside its request, each long workflow document "
                   "as its outline by line and the sections its request points at. Off: the memory is as before, and "
                   "the transcript still records what would have been cut. Fixers are held to the budget either way.")

    @staticmethod
    def enabled() -> bool:
        from app.switches import is_on

        return is_on("REQUEST_BUDGET_FOR_EVERY_STAGE", _ForEveryStage.ON_BY_DEFAULT)


#: Doubtful until measured (owner policy: quality first): small runs that score every hidden test today open past the
#: budget too, so the memory cut for every stage is measured before it is trusted (docs/measuring.md).
for_every_stage_switch = _ForEveryStage()


def opening_target(model: Any = None) -> int:
    """The opening request's size target, in characters, for `model`'s window (the deployment's when None)."""
    from app.agents.context_budget import CHARS_PER_TOKEN, ContextBudget

    try:
        from app.models import environment_of

        budget = ContextBudget.resolve(environment_of(model))
    except Exception:  # noqa: BLE001 - the deployment's own window
        budget = ContextBudget.resolve()
    room = budget.trigger_tokens * CHARS_PER_TOKEN - WORKING_CALLS * budget.tool_output_bytes
    return max(LEAST_OPENING_CHARACTERS, int(room))


@dataclass
class Part:
    """One part of a request: what kind it is, its text as built, its text cut to what the work touches, and where
    it can be read when it is left out (a path the stage can read)."""

    kind: str
    text: str
    cut: str | None = None
    where: str = ""


@dataclass
class Fitted:
    """A request fitted to its target: its text, its size as built and as sent, and what was cut or left out."""

    text: str
    built: int
    target: int
    cut: list[str] = field(default_factory=list)
    left_out: list[str] = field(default_factory=list)

    @property
    def sent(self) -> int:
        return len(self.text)


_A_HEADING = re.compile(r"^--- .+ ---[ \t]*$", re.M)


def sections(text: str) -> list[str]:
    """`text` split at each `--- heading ---` line, each section with its heading; the text before the first is one."""
    text = str(text or "")
    starts = [m.start() for m in _A_HEADING.finditer(text)]
    # A heading's own leading newlines go with it.
    starts = [len(text[:s].rstrip("\n")) for s in starts]
    bounds = sorted({0, *starts, len(text)})
    return [text[a:b] for a, b in zip(bounds, bounds[1:]) if text[a:b]]


def heading_of(section: str) -> str:
    found = _A_HEADING.search(section)
    return found.group(0).strip("- \t") if found else ""


def fit(parts: list[Part], *, target: int, memory: int = 0, cause: str = "",
        memory_text: Callable[[int], str] | None = None, heading: str = STANDING_HEADING) -> Fitted:
    """`parts` past their target: instructions where they stand, the evidence and `cause` first, what is kept whole
    next, the standing context cut and, while the request and its memory are still past `target`, whole standing
    sections left out, largest first.

    `memory`: the characters a project memory given beside the request will hold at least. `memory_text`: a memory
    held inside the request instead, rendered within the room the rest leaves it (at least `memory`), last of the
    standing context.
    """
    built = sum(len(p.text) for p in parts)
    first = next((i for i, p in enumerate(parts) if p.kind != INSTRUCTION), len(parts))
    opening = "".join(p.text.rstrip("\n") + "\n\n" for p in parts[:first] if p.text.strip())
    closing = "\n\n".join(t for p in parts[first:] if p.kind == INSTRUCTION if (t := p.text.strip("\n")))
    head = opening + "".join(p.text for p in parts if p.kind == EVIDENCE).rstrip("\n") + "\n" + cause
    kept = "\n\n".join(text for p in parts if p.kind == KEPT if (text := p.text.strip("\n")))
    cut = [heading_of(p.text) or "part of the setup" for p in parts
           if p.kind == STANDING and p.cut is not None and p.cut != p.text]
    standing: list[tuple[str, str]] = [
        (s.strip("\n") + "\n\n", p.where) for p in parts if p.kind == STANDING
        for s in sections(p.cut if p.cut is not None else p.text) if s.strip()]
    room = target - memory
    tail = len(closing) + 2 if closing else 0
    left_out: list[str] = []

    def total() -> int:
        return len(head) + len(kept) + len(heading) + 4 + sum(len(s) for s, _ in standing) + tail

    while standing and total() > room:
        largest = max(range(len(standing)), key=lambda i: len(standing[i][0]))
        section, where = standing.pop(largest)
        name = heading_of(section) or "part of the setup"
        left_out.append(f"{name} (in {where})" if where else name)
    named = ("Left out to keep this request small - each is in /docs or in the project, to read when you need it: "
             + "; ".join(left_out) + ".\n") if left_out else ""
    text = (head.rstrip("\n") + "\n\n" + kept + "\n\n" + heading + "\n" + named + "\n"
            + "".join(s for s, _ in standing).rstrip("\n") + "\n")
    if memory_text is not None:
        held = memory_text(max(memory, target - len(text) - tail - 2))
        if held:
            text += "\n" + held.strip("\n") + "\n"
    if closing:
        text += "\n" + closing + "\n"
    return Fitted(text=text, built=built, target=target, cut=cut, left_out=left_out)


def noted(stage: str, *, built: int, target: int, sent: int | None = None, fitted: Fitted | None = None,
          applied: bool = True, message: str = "") -> None:
    """One `request_budget` record of a request checked against its target: its size as built and as sent (each with
    the project memory given beside it, where there is one) and the sections cut or left out. `applied` False: what
    would have been sent and cut, the request having gone as built. Never raises."""
    try:
        from app.observability.transcript import _run_id_from_config, record

        record(_run_id_from_config(), stage, RECORD_KIND, target=target, built=built,
               sent=sent if sent is not None else fitted.sent if fitted is not None else built,
               cut=list(fitted.cut) if fitted is not None else [],
               left_out=list(fitted.left_out) if fitted is not None else [], applied=applied,
               **({"message": message} if message else {}))
    except Exception:  # noqa: BLE001 - a record must never fail the request it describes
        logger.debug("Could not record a request's budget", exc_info=True)


__all__ = [
    "EVIDENCE", "Fitted", "INSTRUCTION", "KEPT", "LEAST_OPENING_CHARACTERS", "MEMORY_LEAST_SHARE", "Part",
    "RECORD_KIND", "SAID_FOR_EVERY_STAGE", "STANDING", "STANDING_HEADING", "WORKING_CALLS", "fit",
    "for_every_stage_switch", "heading_of", "noted", "opening_target", "sections",
]
