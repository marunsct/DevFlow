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
- the reasoning switch: how many tokens a small puzzle costs with no
  switch, with `reasoning_effort` "none" and "low" (and each level the
  server lists below "low"), with the chat template's thinking off, with the
  effort given as the chat template's own argument, and with a per-request
  reasoning budget of 64 tokens and of none;
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
#: The reasoning probe's question: one a reasoning model does reason about, so a switch that works shows (IK.1).
#: Measured: "What is 12 plus 30?" cost one model 47 tokens as served and 38-48 every other way - nothing to remove,
#: so every switch read "not honoured" though the model's template took one. The same puzzle the per-process probe
#: asks (`thinking.least_reasoning_effort`); its answer is one number whatever the effort.
_QUESTION = (
    "A farmer has 17 sheep; all but 9 run away; then he buys twice as many as "
    "remain and sells a third of the total. How many sheep? Reply with the "
    "number only."
)
_ANSWER = "18"
#: Below this many output tokens as served the question cost too little for any switch to show: the switches are
#: "not measurable", not "not honoured" (IK.1).
MEASURABLE_FROM_TOKENS = 200
#: A switch is honoured when the question costs under this share of what it costs as served.
HONOURED_BELOW = 0.7
#: The reasoning budget the probe sends, and the longest reply (reasoning and answer) that counts as held to it: the
#: budget is per thinking block, so a reply of two or three blocks may spend two or three budgets (IK.3).
BUDGET_PROBE_TOKENS = 64
BUDGET_HELD_AT_MOST = 256
#: The effort names chat templates use, least first: a level the server lists below "low" is tried too (IK.2).
EFFORT_LEVELS_IN_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
#: The check that names a tool the request does not fit: answered with it only where a named choice is enforced (IK.6).
NAMED_AGAINST_THE_REQUEST = "a named tool the request does not fit"


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

    #: "forced" - a structured answer forces its tool; "offered" - it is offered and asked for; "required" - the
    #: engine refuses a named tool choice but enforces `required`, so a named choice is sent as `required`.
    structured_answers: str = "forced"
    #: Forcing works only with thinking off: force then, offer otherwise.
    force_only_without_thinking: bool = False
    #: The `reasoning_effort` that reasons least, "" to send none.
    least_reasoning_effort: str = ""
    #: Whether the chat template's thinking switch is honoured.
    template_thinking_switch: bool = False
    advice: tuple[str, ...] = ()
    #: False when the probe question cost too few tokens as served for any switch to show: the switches are then
    #: not measurable rather than not honoured, and nothing is kept for them (IK.1).
    reasoning_measurable: bool = True
    #: Where the least effort is sent: "field" - the request's `reasoning_effort`; "template" - the chat template's
    #: own `reasoning_effort` argument, for a server that lets a top-level value overwrite or erase it (IK.2).
    effort_route: str = "field"
    #: Whether the server ends reasoning at a per-request budget (`reasoning_budget_tokens`) and the model answers.
    reasoning_budget: bool = False
    #: Whether a budget of zero still gets the right answer.
    zero_budget_answers: bool = False
    #: The effort the chat template reasons at when a request sends none, as the template writes it; "" unread.
    template_default_effort: str = ""


@dataclass(frozen=True)
class Diagnosis:
    model: str
    measured_at: str
    checks: tuple[Check, ...]
    reasoning_tokens: dict[str, int | None] = field(default_factory=dict)
    settings: Settings = Settings()
    #: Whether each way of asking the reasoning question got its right answer.
    reasoning_answered: dict[str, bool] = field(default_factory=dict)


def speaks_chat_completions(model: Any) -> bool:
    """Whether `model` has the OpenAI-style client every check calls (a hosted model's own client does not)."""
    return callable(getattr(getattr(getattr(getattr(model, "root_client", None), "chat", None), "completions", None),
                            "create", None))


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


def _template_argument(effort: str) -> dict:
    return {"extra_body": {"chat_template_kwargs": {"reasoning_effort": effort}}}


def _reasoning_ways(levels: tuple[str, ...] = ()) -> list[tuple[str, dict]]:
    """Each way the reasoning question is asked: (label, request fields).

    The effort is tried as the request's field and as the chat template's own argument: on llama.cpp a top-level
    "none" sets the template's thinking flag and erases the effort, so a template that reads only the effort falls
    back to its own default - "none" then reasons as much as "high" (IK.2). A per-request reasoning budget is tried
    at 64 tokens and at none: a server that enforces one ends the thinking there and the model must answer (IK.3).
    """
    from app.models.reply_salvage import ENOUGH

    ways: list[tuple[str, dict]] = [
        ("as served", {}), ("effort none", {"reasoning_effort": "none"}), ("effort low", {"reasoning_effort": "low"}),
        ("template thinking off", _THINKING_OFF), ("template effort none", _template_argument("none")),
    ]
    low = EFFORT_LEVELS_IN_ORDER.index("low")
    for level in levels:
        if level in EFFORT_LEVELS_IN_ORDER[1:low]:
            ways += [(f"effort {level}", {"reasoning_effort": level}),
                     (f"template effort {level}", _template_argument(level))]
    ways += [
        (f"budget {BUDGET_PROBE_TOKENS}", {"extra_body": {"reasoning_budget_tokens": BUDGET_PROBE_TOKENS,
                                                          "reasoning_budget_message": ENOUGH}}),
        ("budget 0", {"extra_body": {"reasoning_budget_tokens": 0}}),
    ]
    return ways


def _reasoning_cost(model: Any, levels: tuple[str, ...] = ()) -> tuple[dict[str, int | None], dict[str, bool]]:
    """Output tokens the reasoning question costs each way (None where the server refused it), and whether each way
    got the right answer."""
    out: dict[str, int | None] = {}
    answered: dict[str, bool] = {}
    for label, extra in _reasoning_ways(levels):
        try:
            message, _finish, usage = _message(_create(model)(
                model=model.model_name, messages=[{"role": "user", "content": _QUESTION}],
                max_tokens=REPLY_TOKENS, stream=False, **extra))
            out[label] = int(usage.get("completion_tokens") or 0) or None
            answered[label] = _ANSWER in str(message.get("content") or "")
        except Exception:  # noqa: BLE001
            out[label] = None
            answered[label] = False
    return out, answered


def _served_reasoning(model: Any) -> tuple[tuple[str, ...], str]:
    """(the effort levels the server's chat template lists, the effort the template uses when none is sent), from its
    `/props` (`server_profile`); ((), "") for a server without one. No model call."""
    try:
        from app.models import server_profile

        key = getattr(model, "openai_api_key", None)
        key = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key or "")
        profile = server_profile.read(str(getattr(model, "openai_api_base", "") or ""), key,
                                      str(getattr(model, "model_name", "") or ""))
    except Exception:  # noqa: BLE001 - a server that says nothing of itself
        return (), ""
    if profile is None:
        return (), ""
    return tuple(profile.reasoning_effort_levels), str(profile.template_default_effort or "")


#: Tools by the names a stage is offered, so "the right one of many" is asked the way a stage is.
_STAGE_TOOL_NAMES = ("ls", "read_file", "glob", "grep", "write_artifact", "edit_artifact", "replace_lines",
                     "delete_artifact", "move_artifact", "run_terminal_command", "read_command_output",
                     "ask_specification", "read_specification", "web_search", "fetch_url")


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
        # The tool the request fits is not the one named: answered with the named one only where the name is enforced.
        # A server that reads a named choice as `auto` passes "one tool named" by the model's own choice (IK.6).
        _tool_check(model, NAMED_AGAINST_THE_REQUEST, tools=[_WEATHER, _READ], ask=_ASK_WEATHER, wanted="read_file",
                    args_ok=lambda a: True, extra=_named(_READ)),
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
            _tool_check(model, "a structured answer, required", tools=[*_stage_tools(), answer], ask=_a_stage_s_work(),
                        wanted=answer["function"]["name"], args_ok=_reported(schema), only_offered_names=True,
                        extra={"tool_choice": "required"}),
            _tool_check(model, "forced after a long request", tools=[*_stage_tools(), answer],
                        ask=_a_stage_s_work(_A_LONG_PROJECT + "\n"), wanted=answer["function"]["name"],
                        args_ok=_reported(schema), extra=named, tries=2),
        ]
    except Exception:  # noqa: BLE001 - the stage schemas could not be loaded: the small checks stand
        logger.debug("Could not ask the stage-shaped questions", exc_info=True)
    checks += [_parallel_check(model), _recall_check(model)]
    probed, probe_advice = _existing_probes(model, name)
    checks += probed
    levels, template_default = _served_reasoning(model)
    cost, answered = _reasoning_cost(model, levels)
    settings = settled(checks, cost, answered, template_default=template_default)
    if probe_advice:
        settings = Settings(**{**asdict(settings), "advice": (*settings.advice, *probe_advice)})
    diagnosis = Diagnosis(name, datetime.now(timezone.utc).isoformat(timespec="seconds"), tuple(checks), cost, settings,
                          answered)
    logger.info("Diagnosed %s in %.0f s: %s", name, time.monotonic() - started, "; ".join(settings.advice))
    return diagnosis


def settled(checks: list[Check], cost: dict[str, int | None], answered: dict[str, bool] | None = None, *,
            template_default: str = "") -> Settings:
    """The settings the checks call for, and why, in words."""
    by = {c.name: c for c in checks}
    advice: list[str] = []
    against = by.get(NAMED_AGAINST_THE_REQUEST)
    forced = by["one tool named"].works and by["a tool required"].works
    if forced and against is not None and not against.works:
        # The named tool was called because the request fits it, not because it was named (IK.6).
        forced = False
        advice.append(f"a named tool choice is not enforced ({against.name} {against.passed}/{against.tries}): the "
                      "model chose the named tool by itself")
    required_in_a_stage = by.get("a structured answer, required")
    # `required` enforced on a small request and on one shaped like a stage's: the form to send whenever a named
    # choice falls short, whatever the reason it did (IK.6).
    required_ok = bool(by["a tool required"].works and required_in_a_stage is not None and required_in_a_stage.works)
    stage_shaped = [by[n] for n in ("a structured answer forced", "forced after a long request") if n in by]
    if forced and stage_shaped and not all(c.works for c in stage_shaped):
        offered = by.get("a structured answer, offered")
        failing = ", ".join(f"{c.name} {c.passed}/{c.tries}" for c in stage_shaped if not c.works)
        if required_ok:
            forced = False
            advice.append(f"a named tool choice falls short on a request shaped like a stage's ({failing}) while "
                          "`required` works there: a structured answer's named choice is sent as `required`")
        elif offered is not None and offered.works:
            forced = False
            advice.append("forcing works on a small request but not on one shaped like a stage's; offered, the "
                          "answer is given: structured answers are offered")
        else:
            advice.append(f"a stage-shaped structured answer is unreliable forced ({failing}) and offered does no "
                          "better: forced stays; long stages are where this build may fall short")
    forced_without_thinking = by["one tool named, thinking off"].works
    # An engine that takes only the strings none, auto and required refuses the named form with a 400 about its
    # type, which says nothing about forcing: `required` forces. Measured on an LM Studio server, where `auto` made
    # the model's output fail the engine's own parser and `required` never did. A llama.cpp server reads the named
    # form as `auto` without a word (measured: structured answers forced 0/3, required 3/3), so whatever the reason
    # the named form failed, `required` is sent where it works.
    only_strings = any("Supported string values" in note for note in by["one tool named"].notes)
    required_works = not forced and required_ok
    if forced:
        structured, only_off = "forced", False
    elif required_works:
        structured, only_off = "required", False
        if only_strings:
            advice.append("the engine refuses a named tool choice but enforces `required`: a structured answer's "
                          "named choice is sent as `required`")
        elif not any("`required`" in line for line in advice):
            advice.append("a named tool choice is not enforced but `required` is: a structured answer's named choice "
                          "is sent as `required`")
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
    reasoning = _reasoning_settled(cost, answered or {}, template_default)
    advice += reasoning.pop("advice")
    return Settings(structured, only_off, advice=tuple(advice), **reasoning)


def _reasoning_settled(cost: dict[str, int | None], answered: dict[str, bool], template_default: str) -> dict:
    """The reasoning settings the probe's costs call for: least effort and its route, the template switch, the budget."""
    served = cost.get("as served")
    advice: list[str] = []
    out = {"least_reasoning_effort": "", "template_thinking_switch": False, "reasoning_measurable": True,
           "effort_route": "field", "reasoning_budget": False, "zero_budget_answers": False,
           "template_default_effort": template_default}
    if template_default:
        advice.append(f"with nothing sent, the chat template reasons at its own default ({template_default})")
    if not served or served < MEASURABLE_FROM_TOKENS:
        # A question answered in a few dozen tokens has no reasoning to remove: no switch can show (IK.1).
        out["reasoning_measurable"] = False
        advice.append(f"reasoning switches not measurable: the reasoning question cost {served or 'no'} output tokens "
                      f"as served, under {MEASURABLE_FROM_TOKENS}; nothing is kept for them")
        return {**out, "advice": advice}

    def honoured(tokens: int | None) -> bool:
        return bool(tokens) and tokens < HONOURED_BELOW * served

    # (tokens, route, effort) of each effort that reasoned clearly less than as served; the field first on a tie.
    candidates = sorted(
        (tokens, label.startswith("template "), label.rsplit(" ", 1)[1])
        for label, tokens in cost.items()
        if (label.startswith("effort ") or label.startswith("template effort ")) and honoured(tokens)
    )
    if candidates:
        _tokens, template, effort = candidates[0]
        out["least_reasoning_effort"], out["effort_route"] = effort, "template" if template else "field"
    out["template_thinking_switch"] = honoured(cost.get("template thinking off"))
    held = cost.get(f"budget {BUDGET_PROBE_TOKENS}")
    out["reasoning_budget"] = bool(honoured(held) and held <= BUDGET_HELD_AT_MOST
                                   and answered.get(f"budget {BUDGET_PROBE_TOKENS}"))
    out["zero_budget_answers"] = bool(out["reasoning_budget"] and cost.get("budget 0") and answered.get("budget 0"))
    effort = out["least_reasoning_effort"]
    named = (f"reasoning_effort={effort}" + (" as the chat template's argument" if out["effort_route"] == "template"
                                             else "")) if effort else "reasoning_effort not honoured"
    advice.append(f"reasoning switch: {named}; template thinking switch "
                  f"{'honoured' if out['template_thinking_switch'] else 'not honoured'}")
    advice.append("a per-request reasoning budget is enforced"
                  + ("; a zero budget still answers" if out["zero_budget_answers"] else "")
                  if out["reasoning_budget"] else "a per-request reasoning budget is not enforced")
    return {**out, "advice": advice}


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
        return Diagnosis(found["model"], found["measured_at"], checks, dict(found.get("reasoning_tokens") or {}), settings,
                         dict(found.get("reasoning_answered") or {}))
    except Exception:  # noqa: BLE001 - never diagnosed, or kept by an older harness
        return None


def apply(model: Any, diagnosis: Diagnosis | None) -> None:
    """Use the diagnosis's settings for this model's server from now on in this process. Never raises."""
    if diagnosis is None:
        return
    try:
        from app.models import _NAMED_CHOICE_BECOMES_REQUIRED, _NO_FORCED_TOOL_WHILE_THINKING

        server = (str(getattr(model, "openai_api_base", "") or ""), str(getattr(model, "model_name", "") or ""))
        if diagnosis.settings.structured_answers == "required":
            _NAMED_CHOICE_BECOMES_REQUIRED.add(server)
        # Forced only with thinking off is offered too: thinking is not
        # switched per call here, so a forced call would still reason.
        if diagnosis.settings.structured_answers == "offered" or diagnosis.settings.force_only_without_thinking:
            _NO_FORCED_TOOL_WHILE_THINKING.add(server)
        # A named choice answered with that tool: asked for on the calls where only the answer is allowed (PA.16).
        from app.models.named_answer import HONOURED

        # Not where a stage-shaped named choice itself failed: "forced" can stay when nothing better works, and a
        # server that reads the named form as `auto` would then get a named choice in place of the `required` it
        # enforces (IK.6).
        stage_forced = next((c for c in diagnosis.checks if c.name == "a structured answer forced"), None)
        if (diagnosis.settings.structured_answers == "forced" and not diagnosis.settings.force_only_without_thinking
                and (stage_forced is None or stage_forced.works)):
            HONOURED.add(server)
        else:
            HONOURED.discard(server)
        # The reply ceiling the deep diagnosis chose for a model seen looping
        # (`app.models.deep_diagnosis`, used behind `MODEL_GUIDANCE`).
        from app.models import deep_diagnosis, model_guidance

        deep = deep_diagnosis.recorded(diagnosis.model) or {}
        model_guidance.set_ceiling(server, deep.get("reply_ceiling"))
        if diagnosis.reasoning_tokens and diagnosis.settings.reasoning_measurable:
            # The switch the diagnosis measured, so the per-process probe of
            # `thinking.least_reasoning_effort` does not ask again; where the
            # probe could not tell, nothing is kept and that probe measures (IK.1).
            from app.agents import thinking

            thinking.measured(server, diagnosis.settings.least_reasoning_effort or None,
                              diagnosis.settings.effort_route)
        # Whether the server enforces a per-request reasoning budget, and the budget that turns thinking off where
        # the model has no switch for it (IK.3, IK.4; used behind `REASONING_BUDGET`).
        from app.models import reasoning_budget

        reasoning_budget.learnt(server, diagnosis.settings)
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
            from app.models.diagnosis_flight import one_at_a_time

            # One diagnosis of a model at a time: a run started beside another waits for its result (LF.1568).
            with one_at_a_time(name):
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
    lines.append("  reasoning output tokens for the reasoning question: "
                 + ", ".join(f"{k} {v if v is not None else 'refused'}" for k, v in diagnosis.reasoning_tokens.items()))
    lines.append(f"  settings: structured answers {diagnosis.settings.structured_answers}"
                 + (" (thinking off)" if diagnosis.settings.force_only_without_thinking else ""))
    lines += [f"  - {line}" for line in diagnosis.settings.advice]
    return "\n".join(lines)


__all__ = ["the_model_answers", "Check", "Diagnosis", "PASSES_AT", "RECORD_KEY", "Settings", "TRIES", "apply", "diagnose", "diagnose_if_new",
           "keep", "recorded", "report", "settled"]
