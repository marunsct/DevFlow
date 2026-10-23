"""What a model and its server do with tools and reasoning, measured once per model and kept with it (owner, 2026-10-23).

How the harness asks a model for something is the harness's choice; whether
that way works is the model's and its server's. A structured answer is asked
for by forcing a tool; some servers refuse that while the model reasons (one
run failed on its first call), some models write a call the server's parser
cannot read when forced, or a name that was never offered. The harness learnt
each of those from a failed call, in the run, one process at a time.

So a model not seen before is asked a few small questions, each the way a
stage would ask it, and what came back is kept beside the model's other
measurements (`registry.fitness_dir`) under its served name:

- tools offered, a tool required, one tool named - with thinking as the server
  has it and with it off - each tried a few times: answered with the right
  tool and arguments, refused, or written wrongly;
- a name that was never offered, when the request invites one;
- the reasoning switch: how many tokens a short question costs with no
  switch, with `reasoning_effort` "none" and "low", and with the chat
  template's thinking off;
- reply salvage (`app.models.reply_salvage`).

From those, the settings the harness uses for that model (`Settings`):
whether a structured answer forces its tool or offers it, which reasoning
switch it sends. They are applied when a run starts on the model
(`apply`), not decided call by call. The server's sampling is the owner's
(ADR-0008): it is recommended, never sent.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

#: Tries of each tool check: a low-bit model is right some of the time.
TRIES = 3
#: A check passes at this share of its tries.
PASSES_AT = 2 / 3
REPLY_TOKENS = 2_048
#: The key the diagnosis is kept under in the model's fitness file.
RECORD_KEY = "diagnostics"

_WEATHER = {"type": "function", "function": {
    "name": "get_weather", "description": "The current weather in a city.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}
_WRITE = {"type": "function", "function": {
    "name": "write_artifact", "description": "Write a file of the project, replacing it whole.",
    "parameters": {"type": "object", "properties": {"relative_path": {"type": "string"}, "content": {"type": "string"}},
                   "required": ["relative_path", "content"]}}}
_READ = {"type": "function", "function": {
    "name": "read_file", "description": "Read a file of the project.",
    "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}}
_ASK_WEATHER = "What is the weather in Paris right now? Use the tool."
#: Invites a name the model may know from elsewhere (`edit_file`, `str_replace`).
_ASK_EDIT = "In notes.txt, change the word 'draft' to 'final'. The file holds: 'This is a draft.' Make the change."
_QUESTION = "What is 12 plus 30? Reply with the number only."


@dataclass(frozen=True)
class Check:
    name: str
    tries: int = 0
    passed: int = 0
    refused: int = 0
    #: What a failed try did instead, one short note each.
    notes: tuple[str, ...] = ()

    @property
    def works(self) -> bool:
        return self.tries > 0 and self.passed / self.tries >= PASSES_AT


@dataclass(frozen=True)
class Settings:
    """What the harness does for this model, from its diagnosis."""

    #: "forced" - a structured answer forces its tool; "offered" - it is offered and asked for.
    structured_answers: str = "forced"
    #: Forcing works only with thinking off: force then, offer otherwise.
    force_only_without_thinking: bool = False
    #: The `reasoning_effort` that reasons least, "" to send none.
    least_reasoning_effort: str = ""
    #: Whether the chat template's thinking switch is honoured.
    template_thinking_switch: bool = False
    advice: tuple[str, ...] = ()


@dataclass(frozen=True)
class Diagnosis:
    model: str
    measured_at: str
    checks: tuple[Check, ...]
    reasoning_tokens: dict[str, int | None] = field(default_factory=dict)
    settings: Settings = Settings()


def _create(model: Any) -> Any:
    return model.root_client.chat.completions.create


def _message(response: Any) -> tuple[dict, str, dict]:
    data = response if isinstance(response, dict) else response.model_dump(warnings=False)
    choice = (data.get("choices") or [{}])[0] or {}
    return choice.get("message") or {}, str(choice.get("finish_reason") or ""), data.get("usage") or {}


def _refused(error: Exception) -> bool:
    from app.agents.thinking import the_server_refused_the_request

    try:
        return bool(the_server_refused_the_request(error))
    except Exception:  # noqa: BLE001
        return False


def _tool_check(model: Any, name: str, *, tools: list[dict], ask: str | list[dict], wanted: str, args_ok: Any,
                extra: dict | None = None, tries: int = TRIES, only_offered_names: bool = False) -> Check:
    passed = refused = 0
    notes: list[str] = []
    for _ in range(tries):
        try:
            message, finish, _usage = _message(_create(model)(
                model=model.model_name, messages=ask if isinstance(ask, list) else [{"role": "user", "content": ask}],
                tools=tools,
                max_tokens=REPLY_TOKENS, stream=False, **(extra or {})))
        except Exception as error:  # noqa: BLE001 - what the server said is the finding
            if _refused(error):
                refused += 1
                notes.append(f"refused: {str(error)[:120]}")
            else:
                notes.append(f"error: {type(error).__name__}: {str(error)[:120]}")
            continue
        calls = message.get("tool_calls") or []
        if not calls:
            text = str(message.get("content") or "")
            notes.append(f"no call ({finish}): " + (" ".join(text.split())[:100] or "empty"))
            continue
        function = calls[0].get("function") or {}
        called = str(function.get("name") or "")
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except ValueError:
            notes.append(f"unreadable arguments for {called}: {str(function.get('arguments'))[:80]}")
            continue
        if called != wanted:
            offered = {str((t.get("function") or {}).get("name") or "") for t in tools}
            if only_offered_names and called in offered:
                # Another tool it was given - reading a file before changing
                # it - is a step, not a name it made up.
                passed += 1
                notes.append(f"called `{called}` first (offered)")
                continue
            notes.append(f"called `{called}`, not `{wanted}`" + ("" if called in offered else " (not offered)"))
            continue
        if not args_ok(arguments):
            notes.append(f"wrong arguments: {json.dumps(arguments)[:100]}")
            continue
        passed += 1
    return Check(name, tries, passed, refused, tuple(notes))


def _named(tool: dict) -> dict:
    return {"tool_choice": {"type": "function", "function": {"name": tool["function"]["name"]}}}


_THINKING_OFF = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}


def _paris(arguments: dict) -> bool:
    return "paris" in str(arguments.get("city", "")).lower()


def _the_edit(arguments: dict) -> bool:
    return str(arguments.get("relative_path", "")).endswith("notes.txt") and "final" in str(arguments.get("content", ""))


def _reasoning_cost(model: Any) -> dict[str, int | None]:
    """Output tokens a one-number question costs each way; None where the server refused it."""
    out: dict[str, int | None] = {}
    for label, extra in (("as served", {}), ("effort none", {"reasoning_effort": "none"}),
                         ("effort low", {"reasoning_effort": "low"}), ("template thinking off", _THINKING_OFF)):
        try:
            _message_, _finish, usage = _message(_create(model)(
                model=model.model_name, messages=[{"role": "user", "content": _QUESTION}],
                max_tokens=REPLY_TOKENS, stream=False, **extra))
            out[label] = int(usage.get("completion_tokens") or 0) or None
        except Exception:  # noqa: BLE001
            out[label] = None
    return out


#: Tools by the names a stage is offered, so "the right one of many" is asked the way a stage is.
_STAGE_TOOL_NAMES = ("ls", "read_file", "glob", "grep", "write_artifact", "edit_artifact", "replace_lines",
                     "delete_artifact", "move_artifact", "run_terminal_command", "read_command_output",
                     "code_graph", "ask_specification", "read_specification", "web_search", "fetch_url")


def _stage_tools() -> list[dict]:
    tools = []
    for name in _STAGE_TOOL_NAMES:
        if name == "read_file":
            tools.append(_READ)
            continue
        if name == "write_artifact":
            tools.append(_WRITE)
            continue
        tools.append({"type": "function", "function": {
            "name": name, "description": f"The {name.replace('_', ' ')} tool of the workspace.",
            "parameters": {"type": "object", "properties": {"argument": {"type": "string"}}, "required": ["argument"]}}})
    return tools


def _answer_tool() -> tuple[dict, Any]:
    """A stage's own structured answer, as the tool it is asked for by, and its model."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.agents.specialists import SpecialistOutput

    return convert_to_openai_tool(SpecialistOutput), SpecialistOutput


def _a_stage_s_work(opening: str = "") -> list[dict]:
    """A fix stage's conversation at the point it answers: it edited a file and ran the tests, which passed.

    Asked to report work nothing in the conversation shows it doing, a model
    rightly reports none ("I did not change app/routes.py in this session"):
    the work is in the conversation, as a stage's is.
    """
    return [
        {"role": "user", "content": opening + "Fix the defect: creating an item answers 200; it must answer 201. "
                                              "When it is fixed, give your structured answer."},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "edit_artifact", "arguments": json.dumps({"argument": "app/routes.py: status_code=200 -> 201"})}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "Changed app/routes.py (1 line)."},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c2", "type": "function", "function": {
            "name": "run_terminal_command", "arguments": json.dumps({"argument": "pytest -q"})}}]},
        {"role": "tool", "tool_call_id": "c2", "content": "exit 0\n3 passed in 0.41s"},
    ]
_ASK_READ = "Read the file app/main.py."
#: What a stage's request carries before it is asked: the project, about 20,000 tokens of it.
_A_LONG_PROJECT = "".join(
    f"=== app/module_{n}.py ===\ndef handler_{n}(request):\n    value = request.get('v{n}')\n"
    f"    if value is None:\n        return {{'error': 'missing v{n}'}}, 400\n    return {{'value': value}}, 200\n\n"
    for n in range(420))


_ASK_TWO = "What is the weather in Paris and in Tokyo right now? Ask for both at once."
#: A fact in the middle of a request about 24,000 tokens long, asked for at its end.
_THE_CODE = "K7-QX-42"
_A_LONG_REQUEST_WITH_A_FACT = (
    _A_LONG_PROJECT[: len(_A_LONG_PROJECT) // 2]
    + f"\n# The release code of this project is {_THE_CODE}.\n"
    + _A_LONG_PROJECT[len(_A_LONG_PROJECT) // 2:]
    + "\nWhat is the release code of this project? Reply with the code only."
)


def _parallel_check(model: Any) -> Check:
    """Whether one reply can hold more than one call: two cities, one reply."""
    passed, notes = 0, []
    for _ in range(TRIES):
        try:
            message, _finish, _usage = _message(_create(model)(
                model=model.model_name, messages=[{"role": "user", "content": _ASK_TWO}], tools=[_WEATHER],
                max_tokens=REPLY_TOKENS, stream=False))
        except Exception as error:  # noqa: BLE001
            notes.append(f"error: {str(error)[:100]}")
            continue
        cities = {str((json.loads((c.get("function") or {}).get("arguments") or "{}")).get("city", "")).lower()
                  for c in message.get("tool_calls") or []}
        if {"paris", "tokyo"} <= cities:
            passed += 1
        else:
            notes.append(f"{len(message.get('tool_calls') or [])} call(s) in the reply")
    return Check("two calls in one reply", TRIES, passed, 0, tuple(notes))


def _recall_check(model: Any) -> Check:
    """Whether a fact in the middle of a long request is still read at its end."""
    try:
        message, finish, _usage = _message(_create(model)(
            model=model.model_name, messages=[{"role": "user", "content": _A_LONG_REQUEST_WITH_A_FACT}],
            max_tokens=REPLY_TOKENS, stream=False))
    except Exception as error:  # noqa: BLE001
        return Check("a fact in a long request", 1, 0, 0, (f"error: {str(error)[:100]}",))
    text = str(message.get("content") or "")
    ok = _THE_CODE in text
    return Check("a fact in a long request", 1, int(ok), 0, () if ok else (f"answered ({finish}): {text[:80]}",))


def _existing_probes(model: Any, name: str) -> tuple[list[Check], list[str]]:
    """The harness's own tool-fitness and edit-format probes (`app.models.fitness`), as checks; the edit rates kept."""
    checks: list[Check] = []
    advice: list[str] = []
    try:
        from app.models.fitness import edit_probe, probe

        fitness = probe(model)
        checks.append(Check("the five tool-fitness probes", fitness.total, fitness.passed, 0, tuple(fitness.misses)))
        rates = edit_probe(model)
        from app.models.registry import WELL_FORMED_EDITS, record_edit_rates

        record_edit_rates(name, rates)
        checks.append(Check("find-and-replace edits well formed", 100, round(100 * rates.get("edit", 0)), 0,
                            (f"whole files {rates.get('whole', 0):.0%}",)))
        if rates.get("edit", 1) < WELL_FORMED_EDITS:
            advice.append(f"find-and-replace edits are well formed {rates.get('edit', 0):.0%} of the time (under "
                          f"{WELL_FORMED_EDITS:.0%}): whole-file writes are the safer edit for short files")
    except Exception:  # noqa: BLE001 - a client these probes cannot drive
        logger.debug("Could not run the fitness probes", exc_info=True)
    return checks, advice


def _reported(schema: Any) -> Any:
    def check(arguments: dict) -> bool:
        try:
            answer = schema.model_validate(arguments)
        except Exception:  # noqa: BLE001 - not the shape asked for
            return False
        return any("routes.py" in f for f in answer.changed_files)
    return check


def diagnose(model: Any, name: str = "") -> Diagnosis:
    """Ask `model` the diagnostic questions; uses the model's server for a few minutes. Never raises."""
    from app.models.reply_salvage import served_name

    name = name or served_name(model)
    started = time.monotonic()
    checks = [
        _tool_check(model, "tools offered", tools=[_WEATHER], ask=_ASK_WEATHER, wanted="get_weather", args_ok=_paris),
        _tool_check(model, "a tool required", tools=[_WEATHER], ask=_ASK_WEATHER, wanted="get_weather", args_ok=_paris,
                    extra={"tool_choice": "required"}),
        _tool_check(model, "one tool named", tools=[_WEATHER, _READ], ask=_ASK_WEATHER, wanted="get_weather",
                    args_ok=_paris, extra=_named(_WEATHER)),
        _tool_check(model, "one tool named, thinking off", tools=[_WEATHER, _READ], ask=_ASK_WEATHER,
                    wanted="get_weather", args_ok=_paris, extra={**_named(_WEATHER), **_THINKING_OFF}),
        _tool_check(model, "only offered names", tools=[_READ, _WRITE], ask=_ASK_EDIT, wanted="write_artifact",
                    args_ok=_the_edit, only_offered_names=True),
        _tool_check(model, "the right one of many tools", tools=_stage_tools(), ask=_ASK_READ, wanted="read_file",
                    args_ok=lambda a: str(a.get("file_path", "")).endswith("app/main.py")),
    ]
    try:
        answer, schema = _answer_tool()
        named = {"tool_choice": {"type": "function", "function": {"name": answer["function"]["name"]}}}
        checks += [
            _tool_check(model, "a structured answer forced", tools=[*_stage_tools(), answer], ask=_a_stage_s_work(),
                        wanted=answer["function"]["name"], args_ok=_reported(schema), extra=named),
            _tool_check(model, "a structured answer, offered", tools=[*_stage_tools(), answer], ask=_a_stage_s_work(),
                        wanted=answer["function"]["name"], args_ok=_reported(schema)),
            _tool_check(model, "forced after a long request", tools=[*_stage_tools(), answer],
                        ask=_a_stage_s_work(_A_LONG_PROJECT + "\n"), wanted=answer["function"]["name"],
                        args_ok=_reported(schema), extra=named, tries=2),
        ]
    except Exception:  # noqa: BLE001 - the stage schemas could not be loaded: the small checks stand
        logger.debug("Could not ask the stage-shaped questions", exc_info=True)
    checks += [_parallel_check(model), _recall_check(model)]
    probed, probe_advice = _existing_probes(model, name)
    checks += probed
    cost = _reasoning_cost(model)
    settings = settled(checks, cost)
    if probe_advice:
        settings = Settings(**{**asdict(settings), "advice": (*settings.advice, *probe_advice)})
    diagnosis = Diagnosis(name, datetime.now(timezone.utc).isoformat(timespec="seconds"), tuple(checks), cost, settings)
    logger.info("Diagnosed %s in %.0f s: %s", name, time.monotonic() - started, "; ".join(settings.advice))
    return diagnosis


def settled(checks: list[Check], cost: dict[str, int | None]) -> Settings:
    """The settings the checks call for, and why, in words."""
    by = {c.name: c for c in checks}
    advice: list[str] = []
    forced = by["one tool named"].works and by["a tool required"].works
    stage_shaped = [by[n] for n in ("a structured answer forced", "forced after a long request") if n in by]
    if forced and stage_shaped and not all(c.works for c in stage_shaped):
        offered = by.get("a structured answer, offered")
        if offered is not None and offered.works:
            forced = False
            advice.append("forcing works on a small request but not on one shaped like a stage's; offered, the "
                          "answer is given: structured answers are offered")
        else:
            failing = ", ".join(f"{c.name} {c.passed}/{c.tries}" for c in stage_shaped if not c.works)
            advice.append(f"a stage-shaped structured answer is unreliable forced ({failing}) and offered does no "
                          "better: forced stays; long stages are where this build may fall short")
    forced_without_thinking = by["one tool named, thinking off"].works
    if forced:
        structured, only_off = "forced", False
    elif forced_without_thinking:
        structured, only_off = "forced", True
        advice.append("a forced tool works only with thinking off: structured answers are forced with thinking off")
    else:
        structured, only_off = "offered", False
        advice.append("forcing a tool does not work: structured answers offer their tool and ask for it")
    if not by["tools offered"].works:
        advice.append("even an offered tool is called wrongly: check the server's tool-call parser for this template")
    wrong = [n for n in by["only offered names"].notes if n.endswith("(not offered)")]
    if wrong:
        advice.append("the model calls tools that were not offered (" + "; ".join(wrong[:2]) + "): their names are "
                      "taken as aliases where `registry.TOOL_ALIASES` knows them")
    if "two calls in one reply" in by and not by["two calls in one reply"].works:
        advice.append("one reply holds one call: a stage takes one step a call, so its calls budget goes less far")
    if "a fact in a long request" in by and not by["a fact in a long request"].works:
        advice.append("a fact in the middle of a 24,000-token request was not read: long requests (the project "
                      "memory, a large specification) are unreliable on this build")
    served = cost.get("as served")
    efforts = {label: tokens for label, tokens in cost.items() if label.startswith("effort") and tokens}
    least = min(efforts, key=efforts.get) if efforts else ""
    effort = least.split(" ", 1)[1] if least and served and efforts[least] < 0.7 * served else ""
    switch = bool(served and cost.get("template thinking off") and cost["template thinking off"] < 0.7 * served)
    advice.append(f"reasoning switch: {'reasoning_effort=' + effort if effort else 'reasoning_effort not honoured'}; "
                  f"template thinking switch {'honoured' if switch else 'not honoured'}")
    return Settings(structured, only_off, effort, switch, tuple(advice))


def keep(diagnosis: Diagnosis) -> None:
    from app.models.registry import merge_into_fitness

    merge_into_fitness(diagnosis.model, {RECORD_KEY: asdict(diagnosis)})


def recorded(name: str) -> Diagnosis | None:
    """The kept diagnosis of `name`, or None."""
    from app.models.registry import _slug, fitness_dir

    try:
        found = json.loads((fitness_dir() / f"{_slug(name)}.json").read_text(encoding="utf-8")).get(RECORD_KEY)
        checks = tuple(Check(**{**c, "notes": tuple(c.get("notes") or ())}) for c in found.get("checks") or ())
        settings = Settings(**{**found.get("settings", {}), "advice": tuple((found.get("settings") or {}).get("advice") or ())})
        return Diagnosis(found["model"], found["measured_at"], checks, dict(found.get("reasoning_tokens") or {}), settings)
    except Exception:  # noqa: BLE001 - never diagnosed, or kept by an older harness
        return None


def apply(model: Any, diagnosis: Diagnosis | None) -> None:
    """Use the diagnosis's settings for this model's server from now on in this process. Never raises."""
    if diagnosis is None:
        return
    try:
        from app.models import _NO_FORCED_TOOL_WHILE_THINKING

        server = (str(getattr(model, "openai_api_base", "") or ""), str(getattr(model, "model_name", "") or ""))
        # Forced only with thinking off is offered too: thinking is not
        # switched per call here, so a forced call would still reason.
        if diagnosis.settings.structured_answers == "offered" or diagnosis.settings.force_only_without_thinking:
            _NO_FORCED_TOOL_WHILE_THINKING.add(server)
        # The reply ceiling the deep diagnosis chose for a model seen looping
        # (`app.models.deep_diagnosis`, used behind `MODEL_GUIDANCE`).
        from app.models import deep_diagnosis, model_guidance

        deep = deep_diagnosis.recorded(diagnosis.model) or {}
        model_guidance.set_ceiling(server, deep.get("reply_ceiling"))
        if diagnosis.reasoning_tokens:
            # The switch the diagnosis measured, so the per-process probe of
            # `thinking.least_reasoning_effort` does not ask again.
            from app.agents import thinking

            with thinking._least_effort_lock:
                thinking._least_effort.setdefault(server, diagnosis.settings.least_reasoning_effort or None)
    except Exception:  # noqa: BLE001
        logger.debug("Could not apply the model's diagnosis", exc_info=True)


def the_model_answers(model: Any) -> bool:
    """Whether the model server answers one small request at all - before anything about the model is measured.

    Measured on one run's start: the server had no model loaded and answered
    every request "No model loaded" (400). The diagnosis ran in no time and
    kept each refusal as the model's: "forcing a tool does not work", "reply
    salvage not supported", no guidance - all of it about a server, none about
    the model. Never raises.
    """
    try:
        response = _create(model)(model=model.model_name, messages=[{"role": "user", "content": "Reply with: ready"}],
                                  max_tokens=64, stream=False)
        data = response if isinstance(response, dict) else response.model_dump(warnings=False)
        return bool(data.get("choices"))
    except Exception as error:  # noqa: BLE001 - it does not answer
        logger.info("The model server does not answer, so nothing about the model is measured: %s", str(error)[:160])
        return False


def diagnose_if_new(model: Any) -> Diagnosis | None:
    """The kept diagnosis of the served model, diagnosed now when there is none, and applied. Never raises."""
    try:
        from app.models.reply_salvage import served_name

        name = served_name(model)
        diagnosis = recorded(name)
        if diagnosis is None:
            if not the_model_answers(model):
                return None
            diagnosis = diagnose(model, name)
            keep(diagnosis)
        apply(model, diagnosis)
        return diagnosis
    except Exception:  # noqa: BLE001
        logger.debug("Could not diagnose the model", exc_info=True)
        return None


def report(diagnosis: Diagnosis) -> str:
    lines = [f"model {diagnosis.model} (measured {diagnosis.measured_at})"]
    for check in diagnosis.checks:
        lines.append(f"  {check.name:<30} {check.passed}/{check.tries} passed, {check.refused} refused"
                     + (f"  - {check.notes[0]}" if check.notes else ""))
        for note in check.notes[1:]:
            lines.append(f"  {'':<30} - {note}")
    lines.append("  reasoning output tokens for a one-number question: "
                 + ", ".join(f"{k} {v if v is not None else 'refused'}" for k, v in diagnosis.reasoning_tokens.items()))
    lines.append(f"  settings: structured answers {diagnosis.settings.structured_answers}"
                 + (" (thinking off)" if diagnosis.settings.force_only_without_thinking else ""))
    lines += [f"  - {line}" for line in diagnosis.settings.advice]
    return "\n".join(lines)


__all__ = ["the_model_answers", "Check", "Diagnosis", "PASSES_AT", "RECORD_KEY", "Settings", "TRIES", "apply", "diagnose", "diagnose_if_new",
           "keep", "recorded", "report", "settled"]
