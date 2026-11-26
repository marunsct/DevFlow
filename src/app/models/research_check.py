"""Whether a model looks up what is newer than its training, and uses the answer: one check of the model diagnosis,
its verdict kept with the model's capabilities (plan HK.11, LF.1307).

Measured before it: the web search and the page reader were offered to every model, and the local model called them
0 times in 24 runs. Calling a lookup needs a model to know what it does not know, and plain prompting does not give
that reliably (RetrievalQA, SeaKR), so whether a model does it is measured, not assumed - once, shaped like the stage
where it matters:

- a builder is asked to write a file against a library release that came out after its training data ends (a
  library no model can know, so nothing it remembers is right), with `research` - the same tool, the same words, that
  a stage is offered (`app.tools.research_tool`) - and a file writer offered;
- it **calls** the lookup when it asks before it writes;
- it **uses** the answer when the file it then writes calls the name the answer gave, which only the answer holds.

Asked `TRIES` times; a model that calls and uses on at least `PASSES` of them is kept as one that looks things up
(capability `FIELD`), with a note of how many it called and used. A server that does not answer leaves the verdict
unknown; one that refuses the request (a 4xx) is a "no", as for every other capability. The owner's value on the
settings page wins, as for every capability. Run with the other capability probes (`capabilities.measure`), and at a
run's start for a model whose capabilities were found before this check existed (`measure_if_new`).
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

#: The capability field the verdict is kept under (`app.models.capabilities.FIELDS`).
FIELD = "researches"
TRIES = 3
#: Tries that must both call the lookup and use its answer.
PASSES = 2
#: Replies one try may take: the first, the one after the answer, and a follow-up question or two.
MOST_STEPS = 4
REPLY_TOKENS = 6_000

#: A library no model was trained on, a release line it changed, and the name only the answer gives.
LIBRARY = "tidewell"
VERSION = "4.0.0"
NEW_NAME = "attach_store"
_SYSTEM = "You are a backend specialist building a product. You write the project's files with the tools you are given."
_REQUEST = (
    f"This project uses the Python library {LIBRARY} {VERSION}, released after your training data ends; its 4 "
    "release line changed how a store is opened. Write the file orders-svc/store.py: open a "
    f"{LIBRARY} store at the address in the STORE_URL environment variable and keep it as the module's `store`."
)
_ANSWER = (
    f"--- A note on this question, condensed from what others found ---\n"
    f"Cause: {LIBRARY} {VERSION} removed `{LIBRARY}.open()`.\n"
    f"Change: open a store with `{LIBRARY}.{NEW_NAME}(url)`; it returns the store.\n"
    f"Versions it is about: {VERSION}\n"
    f"Source: the {LIBRARY} release notes for {VERSION}."
)


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required}}}


def _research_tool() -> dict:
    from app.tools.research_tool import DESCRIPTION, QUESTION_HELP, TOOL_NAME

    return _tool(TOOL_NAME, DESCRIPTION, {"question": {"type": "string", "description": QUESTION_HELP}}, ["question"])


_WRITE = _tool("write_artifact", "Write a file of the project, replacing it whole.",
               {"relative_path": {"type": "string"}, "content": {"type": "string"}}, ["relative_path", "content"])


def _reply(response: Any) -> tuple[dict, str]:
    data = response if isinstance(response, dict) else response.model_dump(warnings=False)
    choice = (data.get("choices") or [{}])[0] or {}
    return choice.get("message") or {}, str(choice.get("finish_reason") or "")


def _calls(message: dict) -> list[tuple[str, str, dict]]:
    out = []
    for number, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except ValueError:
            arguments = {}
        out.append((str(call.get("id") or f"call-{number}"), str(function.get("name") or ""),
                    arguments if isinstance(arguments, dict) else {}))
    return out


def one_try(model: Any) -> tuple[bool, bool, str]:
    """(it called the lookup before writing, it used the answer, what it did instead). Raises what the server raised."""
    from app.tools.research_tool import TOOL_NAME

    create = model.root_client.chat.completions.create
    messages: list[dict] = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": _REQUEST}]
    tools = [_research_tool(), _WRITE]
    answered = False
    for _step in range(MOST_STEPS):
        message, finish = _reply(create(model=model.model_name, messages=messages, tools=tools,
                                        max_tokens=REPLY_TOKENS, stream=False))
        calls = _calls(message)
        writes = [args for _id, name, args in calls if name == "write_artifact"]
        if writes:
            if not answered:
                return (any(name == TOOL_NAME for _id, name, _a in calls), False, "wrote the file before the answer")
            used = NEW_NAME in str(writes[0].get("content") or "")
            return True, used, "" if used else "wrote the file without the answer's name"
        if not calls:
            text = str(message.get("content") or "")
            if not answered:
                return False, False, f"answered without looking it up ({finish or 'no finish'})"
            used = NEW_NAME in text
            return True, used, "" if used else "answered without the answer's name"
        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            for call_id, name, args in calls]})
        for call_id, name, _args in calls:
            said = _ANSWER if name == TOOL_NAME else json.dumps({"error": f"No tool named {name}."})
            messages.append({"role": "tool", "tool_call_id": call_id, "content": said})
        answered = answered or any(name == TOOL_NAME for _id, name, _a in calls)
    return answered, False, "no file written after the answer"


def measure(model: Any) -> dict[str, dict]:
    """{FIELD: found} for `model`: True when it called the lookup and used its answer on at least `PASSES` of `TRIES`;
    False when it did not, or the server refused the request; {} when the server did not answer. Never raises."""
    from app.models.capabilities import _found, _refused  # noqa: PLC2701 - the capabilities' own verdict rules

    def one(_n: int) -> tuple[bool, bool, str] | Exception:
        try:
            return one_try(model)
        except Exception as error:  # noqa: BLE001 - judged below
            return error

    try:
        with ThreadPoolExecutor(max_workers=TRIES) as pool:
            outcomes = list(pool.map(one, range(TRIES)))
    except Exception:  # noqa: BLE001 - unknown
        logger.debug("Could not measure whether the model looks things up", exc_info=True)
        return {}
    tried = [o for o in outcomes if not isinstance(o, Exception)]
    errors = [o for o in outcomes if isinstance(o, Exception)]
    if not tried:
        if errors and all(_refused(error) for error in errors):
            return {FIELD: _found(False, "measured", f"the request with a lookup offered was refused: {str(errors[0])[:80]}")}
        logger.info("Whether the model looks things up is left unknown: the server did not answer")
        return {}
    called = sum(1 for c, _u, _n in tried if c)
    both = sum(1 for c, u, _n in tried if c and u)
    notes = [note for _c, _u, note in tried if note]
    note = (f"a file against a release newer than its training, a lookup offered: called it {called}/{len(tried)}, "
            f"used the answer {both}/{len(tried)}" + (f"; {notes[0]}" if notes else ""))
    return {FIELD: _found(both >= PASSES, "measured", note)}


def measure_if_new(model: Any, name: str) -> bool | None:
    """`name`'s kept verdict, measured now and kept when there is none (a model whose capabilities were found before
    this check). Never raises; None when it stays unknown."""
    try:
        from app.models import capabilities

        kept = capabilities.value(name, FIELD)
        if isinstance(kept, bool) or not name:
            return kept if isinstance(kept, bool) else None
        found = measure(model)
        if not found:
            return None
        from app.models.registry import merge_into_fitness

        merge_into_fitness(name, {capabilities.FOUND_KEY: {**capabilities.found_values(name), **found}})
        return bool(found[FIELD]["value"])
    except Exception:  # noqa: BLE001 - unknown
        logger.debug("Could not measure whether the model looks things up", exc_info=True)
        return None


def verdict_of_the_build_model(model: Any = None) -> bool | None:
    """Whether the model that builds and fixes looks things up: `model`'s kept verdict, else the run's pinned or served
    model's; None when no name has one. Never raises."""
    try:
        from app.models.capabilities import value
        from app.models.knowledge_cutoff import _names  # noqa: PLC2701 - one way of naming the build model

        for name in _names(model):
            found = value(name, FIELD)
            if isinstance(found, bool):
                return found
    except Exception:  # noqa: BLE001 - unknown
        logger.debug("Could not read whether the model looks things up", exc_info=True)
    return None


# --- what the model did in runs (tool review 2026-11-26, TR.8, LF.1542) ---------------------------------------------
#
# The check's "yes" did not predict what the model does inside a stage: the local model passed it 3 of 3, and was then
# offered `research` 2,343 times in runs and called it 0 times (the web pair before it: 1,883 offers, 0 calls). So each
# finished run's transcript is counted per model that answered - replies to a request that offered a lookup, and lookup
# calls - and kept with the model; with `WEB_TOOLS_BY_MEASURED_TIER` on, enough offers and no call make the model one
# that never looks things up, whatever the check said (`app.tools.research_tool.tools_by_tier`). The owner's value on
# the settings page still wins.

#: The tools a stage looks things up with, as its tool list holds them: the research tool and the web pair.
LOOKUP_TOOLS: frozenset[str] = frozenset({"research", "search_the_web", "read_web_page"})
#: Where a model's lookups in runs are kept in its fitness file: {run: [offers, calls]}, oldest first.
USE_KEY = "lookups_in_runs"
#: The newest runs that offered the model a lookup kept; older ones age out.
RUNS_KEPT = 20
#: Offers with no call, over at least `RUNS_WITHOUT_A_CALL` kept runs, that make a model one that never looks things up.
OFFERS_WITHOUT_A_CALL = 300
RUNS_WITHOUT_A_CALL = 2


def _tool_names(entry: dict) -> set[str] | None:
    tools = entry.get("tools")
    return {str(name) for name in tools} if isinstance(tools, list) else None


def lookup_use(entries: Any) -> dict[str, tuple[int, int]]:
    """{model: (its replies to a request that offered a lookup, its lookup calls)} over a run's transcript entries, by
    the name the server answered with; a reply naming no model is not counted."""
    offered: dict[str, bool] = {}
    use: dict[str, list[int]] = {}
    for entry in entries or ():
        if not isinstance(entry, dict):
            continue
        stage = str(entry.get("stage") or "")
        if entry.get("kind") == "model_request":
            names = _tool_names(entry)
            if names is not None:
                offered[stage] = bool(names & LOOKUP_TOOLS)
        elif entry.get("kind") == "model_response":
            model = str(entry.get("answered_by") or "")
            if not model:
                continue
            calls = sum(1 for call in entry.get("tool_calls") or [] if isinstance(call, dict)
                        and str(call.get("name") or "") in LOOKUP_TOOLS)
            if offered.get(stage) or calls:
                counted = use.setdefault(model, [0, 0])
                counted[0] += int(bool(offered.get(stage)))
                counted[1] += calls
    return {model: (offers, calls) for model, (offers, calls) in use.items()}


def _kept_use(name: str) -> dict[str, list[int]]:
    try:
        from app.models.capabilities import _record  # noqa: PLC2701 - the one reader of a model's fitness file

        kept = _record(name).get(USE_KEY)
    except Exception:  # noqa: BLE001 - nothing kept
        kept = None
    return {str(run): list(counts) for run, counts in kept.items()} if isinstance(kept, dict) else {}


def keep_the_run_s_use(run_id: str) -> None:
    """Count a finished run's lookups per model from its transcript and keep them with each model, replacing what an
    earlier finish of the same run kept. Never raises."""
    try:
        from app.models.registry import merge_into_fitness
        from app.observability.transcript import read_transcript

        for model, (offers, calls) in lookup_use(read_transcript(run_id, {"model_request", "model_response"})).items():
            kept = _kept_use(model)
            kept.pop(str(run_id), None)
            kept[str(run_id)] = [offers, calls]
            merge_into_fitness(model, {USE_KEY: dict(list(kept.items())[-RUNS_KEPT:])})
    except Exception:  # noqa: BLE001 - the run is finished either way
        logger.debug("Could not keep the run's lookups", exc_info=True)


def never_looks_things_up_in_runs(model: Any = None) -> bool:
    """Whether the runs kept for the build model offered it a lookup at least `OFFERS_WITHOUT_A_CALL` times over at
    least `RUNS_WITHOUT_A_CALL` runs and it called none; False where the owner set its `FIELD`. Never raises."""
    try:
        from app.models.capabilities import owner_values
        from app.models.knowledge_cutoff import _names  # noqa: PLC2701 - one way of naming the build model

        names = _names(model)
        if any(FIELD in owner_values(name) for name in names):
            return False
        for name in names:
            kept = _kept_use(name)
            if kept:
                offers = sum(int(counts[0]) for counts in kept.values())
                calls = sum(int(counts[1]) for counts in kept.values())
                return calls == 0 and offers >= OFFERS_WITHOUT_A_CALL and len(kept) >= RUNS_WITHOUT_A_CALL
    except Exception:  # noqa: BLE001 - unknown, so as the check says
        logger.debug("Could not read the model's lookups in runs", exc_info=True)
    return False


__all__ = ["FIELD", "LIBRARY", "LOOKUP_TOOLS", "NEW_NAME", "OFFERS_WITHOUT_A_CALL", "PASSES", "RUNS_KEPT",
           "RUNS_WITHOUT_A_CALL", "TRIES", "USE_KEY", "keep_the_run_s_use", "lookup_use", "measure", "measure_if_new",
           "never_looks_things_up_in_runs", "one_try", "verdict_of_the_build_model"]
