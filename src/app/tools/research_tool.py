"""One `research(question)` tool for a model measured to look things up, and none of the web tools for one that never
does (plan HK.11, LF.1307).

Measured before it: the web search and the page reader were offered to every model on every stage that reads
documentation (`WEB_TOOLS_OFFERED`, the run's "Always" choice) - about 3,300 characters of tool schema a request - and
the local model called them 0 times in 24 runs; published evidence says even a frontier model seldom searches while it
codes, and that a summarised answer beats raw results (OpenHands-Versa). A person in a team does not "have a search
tool": they ask a colleague a question and get a checked answer. So the tools are chosen by what the model was measured
to do (`app.models.research_check`, the model diagnosis's check, kept with its capabilities):

- **a model that looks things up and uses the answer** is offered one tool, `research(question)`, in place of the web
  search and the page reader. It runs the harness's own lookup (`app.graph.stuck_research`, plan HK.3): the installed
  package's own files first, short queries to the library's tracker and the question sites through the one outbound
  gate, the resolution read, ranked, then condensed by one call into a note - cause, change, versions, source -
  checked against the versions this project runs. The model gets that note, never pages or raw leads. Always on for
  such a model: it is the same lookup the harness already trusts for a stuck fixer, asked by the model instead;
- **a model measured never to look things up** is offered no web tool at all, behind `WEB_TOOLS_BY_MEASURED_TIER`
  (off until measured: the report leaves it to the owner, open point 2), so its requests shrink. The harness's own
  lookups at their fixed points (a stuck fixer, an install that failed) go on as the run's choice says;
- **a model not yet measured** is offered what it was before.

The run's "Internet lookups" choice still decides whether anything leaves: neither tool is offered unless it is
"Always" (`WEB_TOOLS_OFFERED`). Each question is one lookup note in the run's ledger, triggered `TRIGGER`, so the audit
can count the calls and join each note to what followed (plan HK.4).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: The tool's name, as a stage's tool list holds it.
TOOL_NAME = "research"
#: Questions one stage's tool answers; each is a few requests and one condensing call.
MOST_QUESTIONS = 3
#: Characters of a note handed back.
MOST_NOTE = 1_800
#: The ledger's trigger for a note the model asked for.
TRIGGER = "research tool"
#: What the tool says it does: the model diagnosis's check offers the same words, so it measures what a stage is offered.
DESCRIPTION = (
    "Ask one question whose answer may be newer than your training data: what a release of a library, a framework "
    "or a tool changed, which name replaced another, what an error message means and how others fixed it. The "
    "harness looks in the installed package's own files, the library's issue tracker and question sites, checks "
    "what it finds against the versions this project runs, and answers with a short note: the cause, the change "
    "to make, the versions it is about and its source - or that nothing checked was found."
)
QUESTION_HELP = ("One question, naming the library or tool and its version, e.g. \"somelib 2.0 what replaced "
                 "connect()\", or an error message as it was printed.")
#: What the tool answers when nothing checked was found.
NOTHING_CHECKED = ("Nothing checked was found for this question. Work from the project's own evidence: the installed "
                   "package's files, its tests and the build's output.")


class _ByMeasuredTier:
    """`WEB_TOOLS_BY_MEASURED_TIER` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A model the diagnosis measured never to look things up is offered no web search or page reader, "
                   "so its requests are smaller; the harness still looks errors up for it where the run's Internet "
                   "lookups choice allows. A model measured to look things up gets one research tool either way.")

    @staticmethod
    def enabled() -> bool:
        return is_on("WEB_TOOLS_BY_MEASURED_TIER", _ByMeasuredTier.ON_BY_DEFAULT)


by_measured_tier_switch = _ByMeasuredTier()


def withheld_from_non_callers() -> bool:
    return by_measured_tier_switch.enabled()


def _private_words(repo_root: str | Path | None) -> list[str]:
    """The product's own words, never sent (the one outbound gate's, `app.tools.outbound.private_words`)."""
    words = [Path(repo_root).name] if repo_root else []
    try:
        from app.tools import outbound

        words += [w for w in outbound.private_words(repo_root) if w not in words]
    except Exception:  # noqa: BLE001 - the folder's name alone
        pass
    return [w for w in words if w]


def _the_build_model() -> Any:
    from app.models import build_default_chat_model

    return build_default_chat_model()


def _checked(shown: str) -> str:
    """The part of a lookup's section a model may be handed: a condensed, version-checked note or the installed
    package's own answer; "" for raw leads, which never reach the model."""
    from app.graph import stuck_research

    text = str(shown or "").strip()
    if stuck_research.CONDENSED_HEADING in text or stuck_research.LOCAL_HEADING in text:
        return text[:MOST_NOTE]
    return ""


def build_research_tool(repo_root: str | Path | None = None, *, model: Any = None,
                        build_model: Callable[[], Any] | None = None) -> Any:
    """The `research(question)` tool for one stage: `model` condenses what is found (else the build model, built at
    the first question)."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    class _Question(BaseModel):
        question: str = Field(description=QUESTION_HELP)

    asked: list[str] = []

    def research(question: str) -> dict[str, Any]:
        from app.tools.research import found, over_its_share

        question = " ".join(str(question or "").split())
        if not question:
            return {"error": "Ask one question, naming the library or tool it is about."}
        if len(asked) >= MOST_QUESTIONS:
            return {"error": f"This stage has asked its {MOST_QUESTIONS} questions. Work from what the answers said "
                             "and the project's own evidence."}
        refusal = over_its_share("web")
        if refusal:
            return {"error": refusal}
        asked.append(question)
        try:
            from app.agents.stage_memory import current_stage_key
            from app.graph import stuck_research

            root = repo_root or "."
            condenser = model if model is not None else (build_model or _the_build_model)()
            shown, _query = stuck_research.research(
                root, question, "", _private_words(repo_root), trigger=TRIGGER,
                stage_name=current_stage_key() or TOOL_NAME, model=condenser, always_condensed=True)
        except Exception:  # noqa: BLE001 - the stage goes on without it
            logger.debug("Could not research a question", exc_info=True)
            shown = ""
        note = _checked(shown)
        answer = {"note": note} if note else {"note": NOTHING_CHECKED}
        found(f"{TOOL_NAME} {question}", {"excerpt": answer["note"]})
        return answer

    return StructuredTool.from_function(func=research, name=TOOL_NAME, description=DESCRIPTION,
                                        args_schema=_Question)


def tools_by_tier(repo_root: str | Path | None = None, *, model: Any = None) -> list[Any] | None:
    """The web tools a stage is offered by the model's measured verdict: [the research tool] for a model that looks
    things up; [] for one that never does, with `WEB_TOOLS_BY_MEASURED_TIER` on; None - what was offered before - for a
    model not yet measured, with the switch off, or when the run's Internet lookups choice offers no web tools. Never
    raises."""
    try:
        from app.tools import web_search

        if not web_search.offered():
            return None
        from app.models import research_check

        verdict = research_check.verdict_of_the_build_model(model)
        if verdict is True:
            return [build_research_tool(repo_root)]
        if verdict is False and withheld_from_non_callers():
            return []
    except Exception:  # noqa: BLE001 - offered as before
        logger.debug("Could not choose the web tools by the model's measured tier", exc_info=True)
    return None


__all__ = ["DESCRIPTION", "MOST_QUESTIONS", "NOTHING_CHECKED", "TOOL_NAME", "TRIGGER", "build_research_tool",
           "by_measured_tier_switch", "tools_by_tier", "withheld_from_non_callers"]
