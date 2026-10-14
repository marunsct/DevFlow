"""A frontier stage gathers on the build model and writes on the frontier model.

Measured on one run: of a frontier model's 143 calls before any product was
built, 120 only gathered facts - listed the workspace, read a file, read a
page of documentation, looked a package up - and each one reasoned for 2 to
5 minutes before asking (77 minutes in all). The reasoning a stage needs is
in what it writes, not in deciding which file to read next.

So a stage running on the judgement model makes its gathering turns on the
build model, with reasoning off. The moment the build model would do more than
gather (`GATHERING_TOOLS`) - calls the stage's answer tool or any tool that
writes or runs, replies without a tool call, or has used
`MOST_GATHERING_TURNS` - that turn is asked of the judgement model instead,
with everything gathered in front of it. Its answer is the judgement model's
own; the build model's attempt at it is discarded.

After the judgement model's first turn the build model is offered each next
turn again, up to `MOST_IN_A_ROW` gathering turns between two of the judgement
model's: every change is still the judgement model's to make, but a read it
would have spent 2 to 3 minutes reasoning towards is made in seconds.
Measured on one run: a building stage on the judgement model spent 40
minutes, half its turns reading a file or a passage of one.
`MOST_BUILD_TURNS` bounds the build model's attempts in a visit, after which
the judgement model takes every turn.

The pair is registered by the workflow (`gather_with`), keyed by the
judgement model, so every agent built on that model gets it without each
stage threading it through.
"""

from __future__ import annotations

import logging
import weakref
from typing import Any

logger = logging.getLogger(__name__)

#: Gathering turns one visit makes on the build model before the judgement
#: model's first turn.
MOST_GATHERING_TURNS = 12
#: Gathering turns on the build model between two of the judgement model's,
#: once the judgement model has taken a turn.
MOST_IN_A_ROW = 3
#: The build model's attempts in one visit; past them the judgement model
#: takes every turn.
MOST_BUILD_TURNS = 30

_GATHERERS: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()
_BY_ID: dict[int, Any] = {}


def gather_with(judgement_model: Any, gathering_model: Any) -> None:
    """Agents built on `judgement_model` gather on `gathering_model`."""
    if judgement_model is None or gathering_model is None or judgement_model is gathering_model:
        return
    try:
        _GATHERERS[judgement_model] = gathering_model
    except TypeError:
        _BY_ID[id(judgement_model)] = gathering_model


def gatherer_for(model: Any) -> Any:
    """The model `model`'s agents gather on, or None."""
    if model is None:
        return None
    try:
        found = _GATHERERS.get(model)
    except TypeError:
        found = None
    return found if found is not None else _BY_ID.get(id(model))


#: The calls that only gather: they read the workspace, documentation or a
#: registry and change nothing. Any other call - a write, an edit, a command -
#: is the stage's work, and is the judgement model's to make. Measured on one
#: run: a building stage escalated to the judgement model made its first 12
#: turns - writes and test runs - on the build model it had been escalated from.
GATHERING_TOOLS = frozenset({
    "ls", "read_file", "glob", "grep", "read_docs", "look_up_package", "inspect_repository",
    "read_repository_file", "read_command_output",
})


def _answers(response: Any, answer_tool: str) -> bool:
    """Whether a reply is more than a step of gathering: an answer, or the stage's own work."""
    messages = getattr(response, "result", None) or []
    last = messages[-1] if messages else None
    calls = list(getattr(last, "tool_calls", None) or []) + list(getattr(last, "invalid_tool_calls", None) or [])
    if not calls:
        return True
    return any(str(call.get("name") or "") == answer_tool or str(call.get("name") or "") not in GATHERING_TOOLS
               for call in calls)


def build_gathering_middleware(gathering_model: Any, answer_tool: str) -> Any:
    """Middleware that runs a visit's gathering turns on `gathering_model`."""
    from langchain.agents.middleware import AgentMiddleware

    from app.agents.stage_memory import store

    class GatheringMiddleware(AgentMiddleware):
        def __init__(self) -> None:
            super().__init__()
            # Where the visit is counted outside a graph run, where there is
            # no stage key to keep it under.
            self._visit: dict[str, Any] = {}

        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            visit = store("gathering", self._visit)
            written = bool(visit.get("writing"))
            streak = int(visit.get("streak", 0))
            attempts = int(visit.get("attempts", 0))
            if visit.get("done") or attempts >= MOST_BUILD_TURNS or (written and streak >= MOST_IN_A_ROW):
                visit["streak"] = 0
                return handler(request)
            visit["attempts"] = attempts + 1
            try:
                gathered = handler(request.override(model=gathering_model))
            except Exception:  # noqa: BLE001 - the judgement model takes the turn, and the rest
                logger.info("A gathering turn failed on the build model; the judgement model takes it", exc_info=True)
                visit["done"] = True
                gathered = None
            limit = MOST_IN_A_ROW if written else MOST_GATHERING_TURNS
            if gathered is not None and not _answers(gathered, answer_tool) and streak + 1 <= limit:
                visit["streak"] = streak + 1
                if not written and streak + 1 >= MOST_GATHERING_TURNS:
                    visit["writing"] = True
                    visit["streak"] = MOST_IN_A_ROW
                return gathered
            if not written:
                logger.info("Gathered in %d turn(s) on the build model; the judgement model writes", streak + 1)
            visit["writing"] = True
            visit["streak"] = 0
            return handler(request)

    return GatheringMiddleware()
