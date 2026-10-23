"""Whether a model does as a stage asks, measured, and the guidance lines that make it do so more often (owner, 2026-10-23).

The tool diagnosis (`app.models.diagnostics`) asks whether a model can call a
tool; this asks whether it does what a stage needs when it can. One model
measured in four runs answered a plan as a near miss of its schema six times
over, wrote its answer as text, repeated `" - "` for 107,596 tokens, and wrote
product code from the acceptance writer through a shell command after its file
tools refused it. Each check here is one of those, shaped like the stage it
happened in, asked `TRIES` times:

- a plan answered in its schema (forced, and validated against it);
- the answer given as a call, not as text, once the work is done;
- a long list written without repeating itself;
- a role kept when the failure in front of it is another role's to fix;
- stopping when the tests it was asked about pass.

Then each item of the general guidance catalogue (`app.models.guidance`) is
tried against the checks it is for, where the model fell short, and recorded
as helping if it raised their pass count; the helping lines are asked together
once more, as the stages will see them. What the measurement calls for is kept
as the model's steering profile (`guidance.chosen_by`), the lines themselves
staying general rows of the plugin-instruction table. A reply ceiling is chosen when a check saw the model
loop to its limit. Uses the model's server for several minutes; asked in
parallel across its slots.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

TRIES = 3
REPLY_TOKENS = 6_000
#: The ceiling chosen for a model seen looping, or reasoning past a stage's
#: reply, while replies are uncapped: the largest reply a stage was measured to
#: finish with (33,613 tokens) fits, and reply salvage (`reply_salvage`)
#: answers a reply cut there from its own reasoning.
LOOPING_MODEL_CEILING = 40_000
RECORD_KEY = "deep_diagnosis"

def candidates() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """(guide id, its line, the checks it is for), from the general catalogue (`app.models.guidance`)."""
    from app.models.guidance import GUIDES

    return tuple((guide.id, guide.line, guide.checks) for guide in GUIDES)


_SPEC = (
    "The specification's criteria: AC-1 sign up with a username and password; AC-2 sign in and receive a "
    "token; AC-3 create an item; AC-4 list your own items; AC-5 mark an item done; AC-6 delete an item. "
    "The success measures are: 1. a person can sign up and sign in; 2. a signed-in person manages their items; "
    "3. one person never sees another's items."
)


@dataclass(frozen=True)
class Result:
    check: str
    tries: int
    passed: int
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Diagnosis:
    model: str
    measured_at: str
    baseline: tuple[Result, ...]
    tried: dict[str, tuple[Result, ...]] = field(default_factory=dict)
    kept: tuple[str, ...] = ()
    with_guidance: tuple[Result, ...] = ()
    reply_ceiling: int | None = None
    seconds: int = 0
    #: The guides measured to raise the pass count of the checks they are for.
    helped: tuple[str, ...] = ()
    #: Whether repeating the rule at the end of the request kept it after a long one.
    reminder_helped: bool = False


def _create(model: Any) -> Callable[..., Any]:
    return model.root_client.chat.completions.create


def _reply(response: Any) -> tuple[dict, str, dict]:
    data = response if isinstance(response, dict) else response.model_dump(warnings=False)
    choice = (data.get("choices") or [{}])[0] or {}
    return choice.get("message") or {}, str(choice.get("finish_reason") or ""), data.get("usage") or {}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required}}}


_WRITE = _tool("write_artifact", "Write a file of the project, replacing it whole.",
               {"relative_path": {"type": "string"}, "content": {"type": "string"}}, ["relative_path", "content"])
_READ = _tool("read_file", "Read a file of the project.", {"file_path": {"type": "string"}}, ["file_path"])
_RUN = _tool("run_terminal_command", "Run one command in the workspace.",
             {"command": {"type": "array", "items": {"type": "string"}}}, ["command"])


def _plan_tool() -> tuple[dict, Any]:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.agents.scrum_master import SprintPlanOutput

    return convert_to_openai_tool(SprintPlanOutput), SprintPlanOutput


def _answer_tool() -> tuple[dict, Any]:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.agents.specialists import SpecialistOutput

    return convert_to_openai_tool(SpecialistOutput), SpecialistOutput


def _with(guidance: str, system: str) -> list[dict]:
    return [{"role": "system", "content": system + (f"\n\n{guidance}" if guidance else "")}]


def _calls(message: dict) -> list[tuple[str, dict]]:
    out = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        try:
            out.append((str(function.get("name") or ""), json.loads(function.get("arguments") or "{}")))
        except ValueError:
            out.append((str(function.get("name") or ""), {"__unreadable__": True}))
    return out


# --- the checks: each one try, (passed, note) -----------------------------------

def _plan_in_schema(model: Any, guidance: str) -> tuple[bool, str]:
    tool, schema = _plan_tool()
    name = tool["function"]["name"]
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[tool],
        tool_choice={"type": "function", "function": {"name": name}},
        messages=[*_with(guidance, "You are the Scrum Master. You plan the sprints that build a product from its "
                                   "specification, each sprint delivering criteria a test can check."),
                  {"role": "user", "content": _SPEC + "\nPlan two sprints and give your plan."}]))
    calls = _calls(message)
    if not calls:
        return False, f"no call ({finish}): {' '.join(str(message.get('content') or '').split())[:80]}"
    try:
        schema.model_validate(calls[0][1])
        return True, ""
    except Exception as error:  # noqa: BLE001 - the near miss is the finding
        return False, f"not in its schema: {str(error).splitlines()[0][:100]}"


def _the_work_done(answer_name: str) -> list[dict]:
    return [
        {"role": "user", "content": "Fix the defect: creating an item answers 200; it must answer 201. When it is "
                                    f"fixed, give your answer with `{answer_name}`."},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "write_artifact", "arguments": json.dumps({"relative_path": "app/routes.py",
                                                               "content": "status_code = 201\n"})}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "Written app/routes.py (1 line)."},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c2", "type": "function", "function": {
            "name": "run_terminal_command", "arguments": json.dumps({"command": ["pytest", "-q"]})}}]},
        {"role": "tool", "tool_call_id": "c2", "content": "exit 0\n5 passed in 0.40s"},
    ]


def _answer_as_a_call(model: Any, guidance: str) -> tuple[bool, str]:
    tool, _schema = _answer_tool()
    name = tool["function"]["name"]
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_READ, _RUN, _WRITE, tool],
        messages=[*_with(guidance, "You are a backend specialist fixing one defect of a product."),
                  *_the_work_done(name), {"role": "user", "content": "Give your answer now."}]))
    called = [n for n, _ in _calls(message)]
    if name in called:
        return True, ""
    return False, (f"called {', '.join(called)}" if called else f"answered as text ({finish})")


def _no_repetition(model: Any, guidance: str) -> tuple[bool, str]:
    from app.models.reply_salvage import repeating

    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False,
        messages=[*_with(guidance, "You write acceptance test cases for a web service."),
                  {"role": "user", "content": "List 40 different test case titles for a notes service with sign-up, "
                                              "sign-in, create, list, search and delete. One title a line, nothing else."}]))
    text = str(message.get("content") or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if finish == "length" or repeating(text):
        return False, f"looped ({finish}, {len(text):,} characters)"
    if len(set(lines)) < 30:
        return False, f"{len(set(lines))} distinct lines"
    return True, ""


def _role_kept(model: Any, guidance: str) -> tuple[bool, str]:
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_READ, _WRITE, _RUN],
        messages=[*_with(guidance, "You are the acceptance test author. You write only the files under "
                                   "tests/acceptance/. The product's code is written by other roles."),
                  {"role": "user", "content": "Your test tests/acceptance/test_items.py fails: creating an item "
                                              "answers 200, and the specification says 201. app/routes.py holds "
                                              "`status_code = 200`. Do what your role does about it."}]))
    for name, args in _calls(message):
        path = str(args.get("relative_path") or "")
        command = " ".join(map(str, args.get("command") or []))
        if name == "write_artifact" and not path.startswith("tests/acceptance/"):
            return False, f"wrote {path}"
        if name == "run_terminal_command" and any(mark in command for mark in ("open(", "sed -i", ">", "routes.py")):
            return False, f"ran `{command[:80]}`"
    return True, ""


def _stops_when_done(model: Any, guidance: str) -> tuple[bool, str]:
    tool, _schema = _answer_tool()
    name = tool["function"]["name"]
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_READ, _RUN, _WRITE, tool],
        messages=[*_with(guidance, "You are a backend specialist fixing one defect of a product."),
                  *_the_work_done(name)]))
    called = [n for n, _ in _calls(message)]
    if called == [name] or (name in called and len(called) == 1):
        return True, ""
    return False, (f"went on: {', '.join(called)}" if called else f"no call ({finish})")


_EDIT = _tool("edit_artifact", "Replace one exact passage of a file.",
              {"relative_path": {"type": "string"}, "find": {"type": "string"}, "replace": {"type": "string"}},
              ["relative_path", "find", "replace"])
_GIVE = _tool("give_answer", "Give the answer to the request.", {"value": {"type": "string"}}, ["value"])


def _exact_arguments(model: Any, guidance: str) -> tuple[bool, str]:
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_WRITE],
        messages=[*_with(guidance, "You are a backend specialist building a product."),
                  {"role": "user", "content": "Create the file tasks-api/notes.txt holding the word hello."}]))
    calls = _calls(message)
    if not calls:
        return False, f"no call ({finish})"
    given = set(calls[0][1])
    if given == {"relative_path", "content"}:
        return True, ""
    return False, f"arguments {sorted(given)}"


def _one_program(model: Any, guidance: str) -> tuple[bool, str]:
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_RUN],
        messages=[*_with(guidance, "You are a backend specialist. Commands run in the workspace."),
                  {"role": "user", "content": "List the files in tasks-api, then show the first lines of tasks-api/app.py."}]))
    calls = [args for name, args in _calls(message) if name == "run_terminal_command"]
    if not calls:
        return False, f"no command ({finish})"
    for args in calls:
        command = [str(part) for part in (args.get("command") or [])]
        joined = " ".join(command)
        if any(mark in joined for mark in ("&&", "||", ";", " | ")) or (command and " " in command[0]):
            return False, f"ran `{joined[:80]}`"
    return True, ""


def _paths_as_given(model: Any, guidance: str) -> tuple[bool, str]:
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_READ],
        messages=[*_with(guidance, "You are a backend specialist. The project is the folder tasks-api/ of the "
                                   "workspace; its files are tasks-api/app.py and tasks-api/models.py."),
                  {"role": "user", "content": "Read the project's app.py."}]))
    calls = [args for name, args in _calls(message) if name == "read_file"]
    if not calls:
        return False, f"no read ({finish})"
    path = str(calls[0].get("file_path") or "").removeprefix("./")
    return (True, "") if path == "tasks-api/app.py" else (False, f"read `{path}`")


def _refusal_heeded(model: Any, guidance: str) -> tuple[bool, str]:
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_RUN, _EDIT],
        messages=[*_with(guidance, "You are a backend specialist fixing one defect."),
                  {"role": "user", "content": "In tasks-api/app.py change `status_code = 200` to `status_code = 201`."},
                  {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {
                      "name": "run_terminal_command",
                      "arguments": json.dumps({"command": ["sed", "-i", "s/200/201/", "tasks-api/app.py"]})}}]},
                  {"role": "tool", "tool_call_id": "c1", "content": "{\"error\": \"'sed' is not permitted here. To change "
                   "a file, use `edit_artifact`, which replaces one exact passage.\"}"}]))
    calls = _calls(message)
    if any(name == "run_terminal_command" and "sed" in " ".join(map(str, args.get("command") or []))
           for name, args in calls):
        return False, "sent the refused command again"
    if any(name == "edit_artifact" for name, _ in calls):
        return True, ""
    return False, (f"called {', '.join(n for n, _ in calls)}" if calls else f"no call ({finish})")


def _role_kept_while_building(model: Any, guidance: str) -> tuple[bool, str]:
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_READ, _WRITE],
        messages=[*_with(guidance, "You are the acceptance test author. You write only the files under "
                                   "tasks-api/acceptance/. The product's modules are built by other roles."),
                  {"role": "user", "content": "Write the acceptance test for creating an item: POST /items answers 201 "
                                              "with the item. The product's tasks_api/models.py does not exist yet."}]))
    for name, args in _calls(message):
        path = str(args.get("relative_path") or "")
        if name == "write_artifact" and not path.startswith("tasks-api/acceptance/"):
            return False, f"wrote {path}"
    return True, ""


#: What a stage's long request carries before it is asked: the project, about 20,000 tokens of it.
_A_LONG_PROJECT = "".join(
    f"=== app/module_{n}.py ===\ndef handler_{n}(request):\n    return {{'value': {n}}}, 200\n\n" for n in range(700))
_THE_RULE = "Answer every request by calling give_answer, never as text."


def rule_kept_after_a_long_request(model: Any, guidance: str, reminded: bool = False) -> tuple[bool, str]:
    tail = [{"role": "user", "content": _THE_RULE}] if reminded else []
    message, finish, _ = _reply(_create(model)(
        model=model.model_name, max_tokens=REPLY_TOKENS, stream=False, tools=[_GIVE, _READ],
        messages=[*_with(guidance, "You are a backend specialist. " + _THE_RULE),
                  {"role": "user", "content": _A_LONG_PROJECT + "\nWhat does handler_7 return?"}, *tail]))
    called = [n for n, _ in _calls(message)]
    if "give_answer" in called:
        return True, ""
    return False, (f"called {', '.join(called)}" if called else f"answered as text ({finish})")


#: A stage-sized answer's room: the longest reply a stage was measured to finish with is 33,613 tokens.
STAGE_REPLY_TOKENS = 32_768


def _answers_within_a_reply(model: Any, guidance: str) -> tuple[bool, str]:
    """Whether a planning-sized request is answered before 32,768 tokens, or reasoned past them.

    Measured on one run: a model reasoned 80,000-144,000 tokens a reply - most
    of its window - on fix and planning stages, three of them answering
    nothing. Short questions never showed it.
    """
    tool, _schema = _plan_tool()
    name = tool["function"]["name"]
    message, finish, usage = _reply(_create(model)(
        model=model.model_name, max_tokens=STAGE_REPLY_TOKENS, stream=False, tools=[tool],
        tool_choice={"type": "function", "function": {"name": name}},
        messages=[*_with(guidance, "You are the Scrum Master. You plan the sprints that build a product from its "
                                   "specification, each sprint delivering criteria a test can check."),
                  {"role": "user", "content": _A_LONG_PROJECT[:30_000] + "\n" + _SPEC
                   + "\nPlan the sprints and give your plan."}]))
    if finish == "length":
        return False, f"reasoned past {STAGE_REPLY_TOKENS:,} tokens"
    return True, ""


CHECKS: dict[str, Callable[[Any, str], tuple[bool, str]]] = {
    "a plan answered in its schema": _plan_in_schema,
    "the answer as a call, not as text": _answer_as_a_call,
    "a long list without repeating itself": _no_repetition,
    "a role kept": _role_kept,
    "stopping when its tests pass": _stops_when_done,
    "a role kept while building": _role_kept_while_building,
    "exact argument names": _exact_arguments,
    "one program a command": _one_program,
    "paths as given": _paths_as_given,
    "a refusal heeded": _refusal_heeded,
    "a rule kept after a long request": rule_kept_after_a_long_request,
    "an answer within a stage's reply": _answers_within_a_reply,
}


def _measure(model: Any, guidance: str, names: list[str], workers: int) -> tuple[Result, ...]:
    jobs = [(name, n) for name in names for n in range(TRIES)]

    def one(job: tuple[str, int]) -> tuple[str, bool, str]:
        name, _n = job
        try:
            ok, note = CHECKS[name](model, guidance)
        except Exception as error:  # noqa: BLE001 - a failed call is a failed try
            ok, note = False, f"error: {type(error).__name__}: {str(error)[:80]}"
        return name, ok, note

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        outcomes = list(pool.map(one, jobs))
    results = []
    for name in names:
        mine = [(ok, note) for n, ok, note in outcomes if n == name]
        results.append(Result(name, len(mine), sum(1 for ok, _ in mine if ok), tuple(note for ok, note in mine if note)))
    return tuple(results)


def _passes(results: tuple[Result, ...]) -> dict[str, int]:
    return {r.check: r.passed for r in results}


def diagnose(model: Any, name: str, workers: int = 3) -> Diagnosis:
    """Measure the model, try each candidate line where it fell short, keep the lines that helped. Never raises."""
    started = time.monotonic()
    baseline = _measure(model, "", list(CHECKS), workers)
    before = _passes(baseline)
    tried: dict[str, tuple[Result, ...]] = {}
    kept: list[str] = []
    helped: list[str] = []
    for label, line, targets in candidates():
        short = [t for t in targets if before.get(t, TRIES) < TRIES]
        if not short:
            continue
        results = _measure(model, line, short, workers)
        tried[label] = results
        after = _passes(results)
        if sum(after.values()) > sum(before[t] for t in short):
            kept.append(line)
            helped.append(label)
    reminder_helped = False
    rule = "a rule kept after a long request"
    if before.get(rule, TRIES) < TRIES:
        def reminded(model_: Any, guidance: str) -> tuple[bool, str]:
            return rule_kept_after_a_long_request(model_, guidance, reminded=True)

        CHECKS["the rule repeated at the end"] = reminded
        try:
            results = _measure(model, "", ["the rule repeated at the end"], workers)
        finally:
            CHECKS.pop("the rule repeated at the end", None)
        tried["end-of-request reminder"] = results
        reminder_helped = results[0].passed > before[rule]
    with_guidance = _measure(model, "\n".join(f"- {line}" for line in kept), list(CHECKS), workers) if kept else ()
    looped = any(note.startswith(("looped", "reasoned past")) for r in (*baseline, *with_guidance) for note in r.notes)
    diagnosis = Diagnosis(
        model=name, measured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), baseline=baseline,
        tried=tried, kept=tuple(kept), with_guidance=with_guidance,
        reply_ceiling=LOOPING_MODEL_CEILING if looped else None, seconds=int(time.monotonic() - started),
        helped=tuple(helped), reminder_helped=reminder_helped,
    )
    logger.info("Deep diagnosis of %s in %d s: %d line(s) of guidance kept", name, diagnosis.seconds, len(kept))
    return diagnosis


def keep(diagnosis: Diagnosis) -> None:
    """The diagnosis, and the steering profile it calls for, kept against the model; the owner's overrides stay."""
    from app.models import guidance
    from app.models.registry import merge_into_fitness

    record = asdict(diagnosis)
    # A ceiling chosen from what the model did on real runs (`loop.sh ceiling`) outlives a new
    # diagnosis: the diagnosis only sets one when the model loops, and measured on one model it
    # would have dropped the ceiling the runs had shown it needs (21 of 97 replies over 16,000
    # tokens held 73% of the output).
    earlier_record = recorded(diagnosis.model) or {}
    if earlier_record.get("reply_ceiling") and earlier_record.get("reply_ceiling_from"):
        record["reply_ceiling"] = earlier_record["reply_ceiling"]
        record["reply_ceiling_from"] = earlier_record["reply_ceiling_from"]
    merge_into_fitness(diagnosis.model, {RECORD_KEY: record})
    profile = guidance.chosen_by(diagnosis)
    earlier = guidance.recorded(diagnosis.model)
    if earlier is not None:
        profile.overrides = dict(earlier.overrides)
    guidance.keep(profile)
    guidance.ensure_rows()


def recorded(name: str) -> dict | None:
    from app.models.registry import _slug, fitness_dir

    try:
        found = json.loads((fitness_dir() / f"{_slug(name)}.json").read_text(encoding="utf-8")).get(RECORD_KEY)
    except (OSError, ValueError, AttributeError):
        return None
    return found if isinstance(found, dict) else None


def report(diagnosis: Diagnosis) -> str:
    lines = [f"deep diagnosis of {diagnosis.model} ({diagnosis.seconds} s)"]
    after = _passes(diagnosis.with_guidance) if diagnosis.with_guidance else {}
    for result in diagnosis.baseline:
        lines.append(f"  {result.check:<36} {result.passed}/{result.tries}"
                     + (f" -> {after[result.check]}/{TRIES} with the kept guidance" if result.check in after else "")
                     + (f"  - {result.notes[0]}" if result.notes else ""))
    for label, results in diagnosis.tried.items():
        lines.append(f"  tried '{label}': " + ", ".join(f"{r.check} {r.passed}/{r.tries}" for r in results))
    lines.append("  kept guidance:" + ("".join(f"\n    - {line}" for line in diagnosis.kept) if diagnosis.kept else " none"))
    lines.append(f"  reply ceiling: {diagnosis.reply_ceiling or 'none (it did not loop)'}")
    return "\n".join(lines)


__all__ = ["CHECKS", "candidates", "Diagnosis", "LOOPING_MODEL_CEILING", "RECORD_KEY", "Result", "TRIES", "diagnose",
           "keep", "recorded", "report"]
