"""Tool arguments sent as a JSON string where the tool's schema wants an object or a list.

A model writing a tool call writes its arguments as JSON, and some write a
nested object as a string of JSON instead - `"technology_stack": "{\"language\":
...}"`. The schema refuses it ("Input should be an object"), and the model is
told so. Measured on one run's tools-and-models stage: it was told five times,
each time said it would send an object, and each time sent the string again -
about 12,000 output tokens and 2.5 minutes per attempt, the stage still going.

The value is not wrong, only wrapped once too often. Where the tool's own
parameter schema says a field is an object or a list, and the model sent a
string that parses as exactly that, the string is decoded; prose where a list
of strings is wanted is read one item per line. A string the schema allows, or
one that does not parse to the shape wanted, is left alone for the schema to
judge.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)

#: The deepest a schema is followed: far past any answer this harness asks for.
_MOST_DEPTH = 12


def _resolved(schema: Any, definitions: dict[str, Any]) -> Any:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < _MOST_DEPTH:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        schema = definitions.get(name, {})
        seen += 1
    return schema


def _alternatives(schema: Any, definitions: dict[str, Any]) -> list[dict[str, Any]]:
    schema = _resolved(schema, definitions)
    if not isinstance(schema, dict):
        return []
    for key in ("anyOf", "oneOf"):
        if isinstance(schema.get(key), list):
            return [s for option in schema[key] for s in _alternatives(option, definitions)]
    return [schema]


def _types(schema: dict[str, Any]) -> set[str]:
    kind = schema.get("type")
    if isinstance(kind, list):
        return {str(k) for k in kind}
    if isinstance(kind, str):
        return {kind}
    if "properties" in schema:
        return {"object"}
    if "items" in schema:
        return {"array"}
    return set()


#: A list marker at the start of a line: `-`, `*`, `•`, `1.`, `2)`.
_MARKER = re.compile(r"^\s*(?:[-*\u2022]|\d{1,3}[.)])\s+")


def _as_lines(value: str, options: list[dict[str, Any]], definitions: dict[str, Any]) -> Any:
    """Prose where a list of strings is wanted: one item per line, list markers taken off.

    One run's specification sent eleven of its list fields as paragraphs of
    text, one entry to a line, and all were refused - about 40,000 output
    tokens to write again. Only for a list whose items are plain strings; any
    other shape is left for the schema to refuse.
    """
    for option in options:
        items = _alternatives(option.get("items"), definitions) if "items" in option else []
        if items and all(_types(item) == {"string"} for item in items):
            lines = [_MARKER.sub("", line).strip() for line in value.splitlines()]
            return [line for line in lines if line]
    return value


_LEAKED_LIST = re.compile(r'^\s*\[?\s*"?(?P<inside>[^\]]*?"\s*,\s*"[^\]]*?)"?\s*\]')


def _the_list_it_held(value: list[Any], items: Any, definitions: dict[str, Any]) -> list[Any]:
    """A list of strings sent as one string holding the list's own text, as that list.

    One run's fixer sent `["npm\\", \\"run\\", \\"build\\"],category:"]` - the
    command's three words and the next argument's name inside one string -
    and was refused it as a program named all of that, again and again.
    """
    if len(value) != 1 or not isinstance(value[0], str):
        return value
    if not all(_types(item) == {"string"} for item in _alternatives(items, definitions)):
        return value
    match = _LEAKED_LIST.match(value[0] if value[0].lstrip().startswith(("[", '"')) else '"' + value[0])
    if not match:
        return value
    try:
        words = json.loads('["' + match.group("inside").strip().lstrip('"') + '"]')
    except ValueError:
        return value
    return words if words and all(isinstance(word, str) and word for word in words) else value


def _decoded(text: str) -> Any:
    """`text` as JSON, or as JSON with its open brackets closed when it was cut off; None when it is neither."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    if text.lstrip()[:1] not in ("{", "["):
        return None
    from app.agents.settled_answer import _repair_json

    repaired = _repair_json(text)
    try:
        parsed = json.loads(repaired, strict=False) if repaired else None
    except ValueError:
        return None
    # A list cut off partway ends in the entry the cut ran through: that one
    # is not whole, and its absent fields would refuse the answer.
    if isinstance(parsed, list) and parsed:
        parsed = parsed[:-1]
    return parsed


def _as_entries(value: dict[str, Any]) -> list[Any]:
    """An object where a list is wanted, as that list.

    One local model sent each list section of a specification as one object -
    `{"functions": [...]}`, `{"ui_shell": {...}, "task_store": {...}}` - and
    every answer was refused. An object holding one list is that list; any
    other is one entry per key, its value after it.
    """
    if len(value) == 1 and isinstance(next(iter(value.values())), list):
        return list(next(iter(value.values())))
    return [
        f"{key}: " + (item if isinstance(item, str) else "; ".join(
            f"{k}: {v if isinstance(v, str) else json.dumps(v)}" for k, v in item.items()
        ) if isinstance(item, dict) else json.dumps(item))
        for key, item in value.items()
    ]


def _repaired(value: Any, schema: Any, definitions: dict[str, Any], depth: int) -> Any:
    if depth > _MOST_DEPTH:
        return value
    options = _alternatives(schema, definitions)
    if not options:
        return value
    wanted = set().union(*(_types(option) for option in options))
    if isinstance(value, str) and "string" not in wanted and wanted & {"object", "array"}:
        decoded = _decoded(value)
        if decoded is None:
            return _as_lines(value, options, definitions)
        if (isinstance(decoded, dict) and "object" in wanted) or (isinstance(decoded, list) and "array" in wanted):
            value = decoded
        elif isinstance(decoded, dict) and "array" in wanted:
            value = _as_entries(decoded)
        else:
            return value
    if isinstance(value, dict) and "array" in wanted and "object" not in wanted:
        value = _as_entries(value)
    if isinstance(value, dict) and wanted == {"string"}:
        # An entry written as an object where the schema wants a line of text:
        # one run's specification sent every function contract as
        # `{"file": ..., "name": ..., "signature": ...}`. Its fields, in order.
        return "; ".join(
            f"{key}: {item if isinstance(item, str) else json.dumps(item)}" for key, item in value.items()
        )
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and "string" in wanted and not wanted & {"integer", "number"}):
        # A number where a text is wanted - a sprint named by its number among
        # dependencies the schema keeps as text. Written as text it loses nothing.
        return str(value)
    if (isinstance(value, list) and "string" in wanted and "array" not in wanted and value
            and all(isinstance(item, str) for item in value)):
        # Lines of text written as a list where the schema wants one text: one
        # run's sprint plan sent its rollback notes so, six times, and each
        # answer was refused for it. One line each.
        return "\n".join(value)
    if isinstance(value, dict):
        for option in options:
            properties = option.get("properties")
            if isinstance(properties, dict):
                # A field the schema forbids holds nothing it can keep: dropped,
                # not refused. Only where extra fields are forbidden outright.
                closed = option.get("additionalProperties") is False
                return {
                    key: _repaired(item, properties[key], definitions, depth + 1) if key in properties else item
                    for key, item in value.items()
                    if key in properties or not closed
                }
        return value
    if isinstance(value, list):
        for option in options:
            if "items" in option:
                value = _the_list_it_held(value, option["items"], definitions)
                return [_repaired(item, option["items"], definitions, depth + 1) for item in value]
        return value
    return value


#: Names a model wraps a call's arguments in.
_WRAPPERS = ("args", "arguments", "kwargs", "parameters", "input", "params")


def _unwrapped(arguments: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    """A call's arguments sent inside one wrapper key - `{"args": {...}}` - as the arguments.

    One run's fixer sent `run_terminal_command {"args": {"category": "test",
    "command": [...]}}` and was refused it as an unexpected argument. Only when
    the one key is no parameter of the tool and everything inside it is.
    """
    properties = parameters.get("properties") if isinstance(parameters.get("properties"), dict) else {}
    if len(arguments) != 1 or not properties:
        return arguments
    (key, inner), = arguments.items()
    if key in properties or key not in _WRAPPERS or not isinstance(inner, dict) or not inner:
        return arguments
    return inner if set(inner) <= set(properties) else arguments


def with_structure_decoded(arguments: Any, parameters: Any) -> Any:
    """`arguments` with each JSON string decoded where `parameters` wants an object or a list."""
    if not isinstance(arguments, dict) or not isinstance(parameters, dict):
        return arguments
    arguments = _unwrapped(arguments, parameters)
    definitions = {**(parameters.get("definitions") or {}), **(parameters.get("$defs") or {})}
    try:
        return _repaired(arguments, parameters, definitions, 0)
    except Exception:  # noqa: BLE001 - a repair that cannot run changes nothing
        return arguments


def _parameters_by_tool(tools: Any) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for tool in tools or []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(function, dict) and isinstance(function.get("parameters"), dict):
            found[str(function.get("name") or "")] = function["parameters"]
    return found


def _parsed_leniently(arguments: Any) -> dict[str, Any] | None:
    """A call's argument text as an object: raw line breaks in strings allowed, open brackets closed."""
    if not isinstance(arguments, str) or "{" not in arguments:
        return None
    from app.agents.settled_answer import _repair_json

    for text in (arguments, _repair_json(arguments)):
        if not text:
            continue
        try:
            parsed = json.loads(text, strict=False)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


#: The argument that marks a call as the part of an answer that arrived before
#: the reply was cut off. No schema has it, so the answer is refused, and the
#: refusal (`cut_off_notice`) asks for the fields still to come.
CUT_OFF = "__cut_off__"

#: The fields of an answer that arrived whole, by (run, stage, tool), until
#: the rest arrives.
_HELD: dict[tuple[str, str, str], dict[str, Any]] = {}
_HELD_DOCS: dict[tuple[str, str, str], str] = {}

_SCHEMA_DOCUMENTS: dict[str, tuple[str, str]] = {
    "TechnicalSpecificationOutput": ("technical_specification", "docs/technical_specification.md"),
    "SprintPlanOutput": ("sprint_plan", "docs/sprint_plan.md"),
    "MilestonePlanOutput": ("milestone_plan", "docs/milestone_plan.md"),
}


def _find_workspace_path(run_id: str) -> Path | None:
    if not run_id:
        return None
    try:
        from app.server.workspaces import workspace_root

        root = workspace_root()
        matches = list(root.glob(f"**/workspace-{run_id}")) + list(root.glob(f"workspace-{run_id}"))
        if matches and matches[0].is_dir():
            return matches[0]
    except Exception:
        pass
    for base in (Path("/app/data/workspaces"), Path("data/workspaces"), Path("/app/data"), Path("data")):
        try:
            matches = list(base.glob(f"**/workspace-{run_id}"))
            if matches and matches[0].is_dir():
                return matches[0]
        except Exception:
            pass
    return None


def _sync_partial_document(
    key: tuple[str, str, str],
    held: dict[str, Any],
    workspace_override: Path | None = None,
) -> str | None:
    """Render and write the partial fields to the document on disk, returning the relative path."""
    run, stage, name = key
    if name not in _SCHEMA_DOCUMENTS or not held:
        return None
    template_name, rel_path = _SCHEMA_DOCUMENTS[name]
    workspace = workspace_override or _find_workspace_path(run)
    if not workspace or not workspace.is_dir():
        return None
    try:
        if name == "TechnicalSpecificationOutput":
            from app.agents.specification_document import render_specification

            content = render_specification(held)
        else:
            from app.doc_templates import render_document

            content = render_document(template_name, o=held)
        target = workspace / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _HELD_DOCS[key] = rel_path
        return rel_path
    except Exception:
        logger.warning("Could not sync partial document %s", rel_path, exc_info=True)
        return None

_DANGLING_KEY = re.compile(r',\s*"([^"\\]+)"\s*:?\s*$')


def _answer_key(name: str) -> tuple[str, str, str]:
    run = ""
    stage = ""
    try:
        from langgraph.config import get_config

        from app.tracing import APP_RUN_ID_KEY, APP_STAGE_KEY

        configurable = (get_config() or {}).get("configurable", {})
        run = str(configurable.get(APP_RUN_ID_KEY) or "")
        stage = str(configurable.get(APP_STAGE_KEY) or "")
    except Exception:  # noqa: BLE001 - outside a graph run there is no stage to hold for
        pass
    if not run or not stage:
        try:
            from app.observability.log_context import current_run_id, current_stage

            run = run or str(current_run_id() or "")
            stage = stage or str(current_stage() or "")
        except Exception:  # noqa: BLE001
            pass
    return (run, stage, name)


def what_arrived_whole(arguments: Any) -> tuple[dict[str, Any], str] | None:
    """The fields of a cut-off object that arrived whole, and the field it stopped in.

    One run's specification stage lost five answers of about 35,000
    characters each: the call's arguments simply stopped - `..."example":
    "..."}]\n\n, "file_plan": ` - with the reply marked finished. Everything
    before the field it stopped in was whole.
    """
    from app.agents.settled_answer import _repair_json

    if isinstance(arguments, dict):
        parsed = dict(arguments)
        stopped_in = list(parsed)[-1] if parsed else ""
        parsed.pop(stopped_in, None)
        return (parsed, stopped_in)

    text = str(arguments or "").rstrip().rstrip(",")
    dangling = _DANGLING_KEY.search(text)
    body = text[: dangling.start()] if dangling else text
    repaired = _repair_json(body)
    if not repaired:
        return None
    try:
        parsed = json.loads(repaired, strict=False)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    if dangling:
        return parsed, dangling.group(1)
    # Stopped inside the last field's value: what was closed for it is not all of it.
    stopped_in = list(parsed)[-1]
    parsed.pop(stopped_in)
    return (parsed, stopped_in)


def cut_off_notice(
    exception: Exception,
    schema: Any,
    stopped_in: str | None = None,
    key: tuple[str, str, str] | None = None,
) -> str | None:
    """What a refused cut-off answer is told: what was kept, and what to send. None for any other refusal."""
    if CUT_OFF not in str(exception):
        return None
    name = getattr(schema, "__name__", "")
    target_key = key or _answer_key(name)
    held = _HELD.get(target_key, {})
    fields = list(getattr(schema, "model_fields", {}) or {})
    missing = [field for field in fields if field not in held]
    stopped_text = f" in `{stopped_in}`" if stopped_in else ""
    doc_note = ""
    doc_written = _sync_partial_document(target_key, held) or _HELD_DOCS.get(target_key)
    if doc_written:
        doc_note = f" The document `{doc_written}` has been filled with the sections generated so far."
    return (
        f"Your answer was cut off at the output limit before it ended{stopped_text}. "
        f"These fields arrived whole and are kept: {', '.join(sorted(held)) or 'none'}.{doc_note} "
        f"Do not start over or repeat the fields already kept. "
        f"Call {name} again with only the fields still to send: {', '.join(missing)}. "
        f"Continue directly from where the reply stopped. "
        f"They are joined to the ones kept. Keep each entry to one line."
    )


def _where_it_fails(arguments: Any) -> str:
    """Why a call's argument text is not an object, and the text around the place, for the log."""
    text = str(arguments or "")
    try:
        json.loads(text, strict=False)
    except ValueError as error:
        at = getattr(error, "pos", 0) or 0
        return f"{error}; around it: {text[max(0, at - 120):at + 120]!r}"
    return "it parses, but not to an object"


def _recovered_calls(message: Any, parameters: dict[str, dict[str, Any]]) -> None:
    """Calls to a known tool whose arguments were not strict JSON, made calls again.

    The client keeps a call whose arguments do not parse apart, as an invalid
    call, and nothing reads it: the stage sees a reply with no call at all.
    Measured on one run's specification stage: two answers of about 21,000
    tokens each, `finish_reason` "tool_calls", none recorded - and on the
    second the stage was started again from the beginning. A long text
    field with a line break written raw inside a string is the commonest
    reason, and a strict parser refuses it.
    """
    invalid = list(getattr(message, "invalid_tool_calls", None) or [])
    if not invalid:
        return
    kept = []
    for call in invalid:
        name = str(call.get("name") or "")
        if name not in parameters:
            for tool_name in parameters:
                if tool_name.lower() == name.lower() or (not name and tool_name[0].isupper()):
                    name = tool_name
                    break
        parsed = _parsed_leniently(call.get("args")) if name in parameters else None
        if parsed is None and name in parameters:
            whole = what_arrived_whole(call.get("args"))
            key = _answer_key(name)
            if whole:
                arrived, stopped_in = whole
                _HELD[key] = {**_HELD.get(key, {}), **with_structure_decoded(arrived, parameters[name])}
                logger.warning(
                    "A call to %s was cut off in `%s` after %d characters; %d whole field(s) kept, "
                    "the rest asked for", name, stopped_in, len(str(call.get("args") or "")), len(_HELD[key]),
                )
                message.tool_calls.append({
                    "name": name, "args": {**_HELD[key], CUT_OFF: stopped_in},
                    "id": call.get("id"), "type": "tool_call",
                })
                continue
            logger.warning(
                "A call to %s could not be read even leniently (%d characters): %s",
                name, len(str(call.get("args") or "")), _where_it_fails(call.get("args")),
            )
        if parsed is None:
            kept.append(call)
            continue
        message.tool_calls.append({"name": name, "args": parsed, "id": call.get("id"), "type": "tool_call"})
        logger.warning("A call to %s whose arguments were not strict JSON was read leniently", name)
    message.invalid_tool_calls = kept


def with_every_call_the_server_sent(message: Any, raw_calls: Any) -> None:
    """Each tool call in the server's reply that the message holds neither as a call nor as an invalid one, added as invalid.

    One run's specification stage had three replies end with `finish_reason`
    "tool_calls" and about 15,000 tokens written after the reasoning, and
    recorded no call and no invalid call for any of them. A call the client
    drops is filed here as an invalid call, so it is logged and recorded and
    read leniently (`_recovered_calls`) like any other that did not parse.
    """
    if not isinstance(raw_calls, list) or message is None:
        return
    held = {c.get("id") for c in [*(message.tool_calls or []), *(message.invalid_tool_calls or [])]}
    for raw in raw_calls:
        if not isinstance(raw, dict) or raw.get("id") in held:
            continue
        function = raw.get("function") if isinstance(raw.get("function"), dict) else {}
        arguments = function.get("arguments")
        logger.warning(
            "The server sent a call to %s (%s, %d characters) that the client kept nowhere",
            function.get("name") or "?", type(arguments).__name__, len(str(arguments or "")),
        )
        message.invalid_tool_calls.append({
            "name": function.get("name"), "id": raw.get("id"), "type": "invalid_tool_call",
            "args": arguments if isinstance(arguments, str) else json.dumps(arguments),
            "error": "the client kept this call nowhere",
        })


_NAMESPACE_PREFIX = re.compile(r"^(?:functions?|tools?|default_api)[._:]", re.IGNORECASE)


def _bare(name: str) -> str:
    cleaned = _NAMESPACE_PREFIX.sub("", name)
    return re.sub(r"[^a-z0-9]", "", cleaned.lower())


def _the_call_it_wraps(call: dict[str, Any], parameters: dict[str, Any]) -> None:
    """A call wrapping an offered tool's call - its name in one argument, its arguments in another - made that call.

    Measured on one run: a sprint planner sent its whole plan as
    `Skill({"skill": "SprintPlanOutput", "arguments": {...}})`. `Skill` is not
    offered, so the call was refused and the plan thrown away; its next
    answer, sent properly, had dropped half of it. A call to a tool not
    offered, holding exactly one value that names an offered tool and one
    object, is that tool's call with that object. Never raises.
    """
    try:
        name, args = str(call.get("name") or ""), call.get("args")
        if name in parameters or not isinstance(args, dict):
            return
        named = [value.strip() for value in args.values() if isinstance(value, str) and value.strip() in parameters]
        objects = [value for value in args.values() if isinstance(value, dict)]
        if len(named) != 1 or len(objects) != 1 or len(args) != 2:
            return
        logger.info("A call to `%s` wrapping `%s` taken as that call", name, named[0])
        call["name"], call["args"] = named[0], objects[0]
    except Exception:  # noqa: BLE001 - the refusal stands
        return


def _taken_as_the_tool_it_learned_elsewhere(call: dict[str, Any], parameters: dict[str, Any]) -> None:
    """A call to a tool known by another harness's name, renamed to the offered one it means (M.5). Never raises."""
    try:
        from app.models.registry import TOOL_ALIASES

        name = str(call.get("name") or "")
        if name in parameters or name not in TOOL_ALIASES or not isinstance(call.get("args"), dict):
            return
        target, renames = TOOL_ALIASES[name]
        schema = parameters.get(target)
        if schema is None:
            return
        args = {renames.get(key, key): value for key, value in call["args"].items()}
        wanted = set((schema or {}).get("properties") or {})
        if not set((schema or {}).get("required") or []) <= set(args) or not set(args) <= wanted:
            return
        logger.info("A call to `%s`, a name from elsewhere, taken as `%s`", name, target)
        call["name"], call["args"] = target, args
    except Exception:  # noqa: BLE001 - the refusal stands
        return


def _the_offered_tool_meant(name: str, parameters: dict[str, Any], args: Any = None) -> str | None:
    """The one offered tool a call to `name`, which is not offered, plainly means; None if none or unclear.

    Measured on one run: a 1-bit build model called `Read` with `file_path`
    for `read_file`, over and over, each refused as "not a valid tool". The
    same name in another spelling, or the one offered tool whose name starts
    with it (`Read` for `read_file`, `Grep` for `grep`), is what was meant.
    """
    if not name or name in parameters:
        return None
    unprefixed = _NAMESPACE_PREFIX.sub("", name)
    if unprefixed in parameters:
        return unprefixed
    bare = _bare(name)
    if not bare:
        return None
    same = [tool for tool in parameters if _bare(tool) == bare]
    if len(same) == 1:
        return same[0]
    starting = [tool for tool in parameters if _bare(tool).startswith(bare)]
    if len(starting) == 1:
        return starting[0]
    filed = [tool for tool in starting if _bare(tool) == bare + "file"]
    if len(filed) == 1:
        return filed[0]
    return _the_one_its_arguments_fit(args, parameters)


def _the_one_its_arguments_fit(args: Any, parameters: dict[str, Any]) -> str | None:
    """The one offered tool that takes every argument given and is given all it requires; None if not one.

    By the arguments when the name says nothing: one run's 1-bit planner
    called `global_99` sixteen times with `pattern`, `path` and
    `output_mode` - only `grep` takes all three - and each was refused.
    """
    if not isinstance(args, dict) or not args:
        return None
    given = set(args)
    # Never a stage's answer tool, named after its schema's class: a stray
    # call is not taken as the stage's answer.
    fitting = [
        tool for tool, schema in parameters.items()
        if tool == tool.lower()
        and given <= set((schema or {}).get("properties") or {})
        and set((schema or {}).get("required") or []) <= given
    ]
    return fitting[0] if len(fitting) == 1 else None


def decode_structured_arguments(result: Any, tools: Any) -> Any:
    """Each tool call in a chat result, its arguments decoded where its tool's schema wants structure."""
    parameters = _parameters_by_tool(tools)
    if not parameters:
        return result
    for generation in getattr(result, "generations", None) or []:
        message = getattr(generation, "message", None)
        try:
            _recovered_calls(message, parameters)
        except Exception:  # noqa: BLE001 - a recovery that cannot run changes nothing
            logger.info("Invalid tool calls could not be recovered", exc_info=True)
        for call in getattr(message, "tool_calls", None) or []:
            _the_call_it_wraps(call, parameters)
            _taken_as_the_tool_it_learned_elsewhere(call, parameters)
            offered = _the_offered_tool_meant(str(call.get("name") or ""), parameters, call.get("args"))
            if offered is not None:
                logger.info("A call to `%s`, which is not offered, taken as `%s`", call.get("name"), offered)
                call["name"] = offered
            schema = parameters.get(str(call.get("name") or ""))
            if schema is not None:
                call["args"] = with_the_written_parameters_apart(call.get("args"), schema)
                if isinstance(call["args"], dict) and CUT_OFF in call["args"]:
                    # Kept like any cut-off answer's whole fields: the stage is
                    # told what arrived and asked for the rest (`cut_off_notice`).
                    key = _answer_key(str(call.get("name") or ""))
                    stopped_in = call["args"].pop(CUT_OFF)
                    _HELD[key] = {**_HELD.get(key, {}), **with_structure_decoded(call["args"], schema)}
                    call["args"] = {**_HELD[key], CUT_OFF: stopped_in}
                    continue
                call["args"] = with_structure_decoded(call.get("args"), schema)
                _joined_to_what_was_kept(call)
    return result


#: One field written in the model's tag form, `<parameter=name>value</parameter>`,
#: the last one possibly cut off before its closing tag.
_A_WRITTEN_PARAMETER = re.compile(r"<parameter=([\w-]+)>\s*(.*?)(?:</parameter>|$)", re.S)
#: Where one call written in the tag form ends and the next begins.
_BETWEEN_CALLS = re.compile(r"</function>\s*</tool_call>\s*<tool_call>\s*<function=[\w.-]+>\s*", re.S)


def with_the_written_parameters_apart(args: Any, schema: Any) -> Any:
    """`args` with fields the model wrote in tag form inside another field's value taken apart.

    Measured on one gate run: the architect wrote its specification as
    `<parameter=product_scope>...</parameter></function></tool_call><tool_call>
    <function=TechnicalSpecificationOutput><parameter=data_contracts>...`, the
    server's parser put all 111,127 characters of it into `product_scope`, and
    every section after the first was lost inside it, with the model's own
    tags in the text. Each field is taken back out by its tag; one the reply
    stopped inside (no closing tag) is marked cut off, so the rest is asked for.
    """
    if not isinstance(args, dict):
        return args
    fields = set((schema or {}).get("properties") or {}) if isinstance(schema, dict) else set()
    taken: dict[str, Any] = {}
    stopped_in = ""
    for key, value in list(args.items()):
        if not isinstance(value, str) or ("</parameter>" not in value and "<parameter=" not in value):
            continue
        first, closed, rest = value.partition("</parameter>")
        if not closed:
            first, _, rest = value.partition("<parameter=")
            rest = "<parameter=" + rest
        taken[key] = first.rstrip()
        rest = _BETWEEN_CALLS.sub("", rest)
        for match in _A_WRITTEN_PARAMETER.finditer(rest):
            name, text = match.group(1), match.group(2)
            if fields and name not in fields:
                continue
            if not match.group(0).rstrip().endswith("</parameter>"):
                stopped_in = name
                continue
            taken[name] = text.strip()
    if not taken:
        return args
    logger.warning(
        "A call carried %d field(s) written in tag form inside another; taken apart%s",
        len(taken), f", stopped in `{stopped_in}`" if stopped_in else "",
    )
    merged = {**args, **taken}
    if stopped_in:
        merged[CUT_OFF] = stopped_in
    return merged


def _joined_to_what_was_kept(call: dict[str, Any], key: tuple[str, str, str] | None = None) -> None:
    """The rest of a cut-off answer, joined to the fields kept from it."""
    args = call.get("args")
    if not isinstance(args, dict) or CUT_OFF in args:
        return
    target_key = key or _answer_key(str(call.get("name") or ""))
    held = _HELD.pop(target_key, None)
    if held:
        merged = dict(held)
        for k, v in args.items():
            if k in merged and isinstance(merged[k], list) and isinstance(v, list):
                merged[k] = [*merged[k], *v]
            elif k in merged and isinstance(merged[k], str) and isinstance(v, str) and not merged[k].endswith(v):
                merged[k] = f"{merged[k]} {v}".strip()
            else:
                merged[k] = v
        call["args"] = merged
        logger.warning("The rest of a cut-off %s arrived; joined to the %d field(s) kept", call.get("name"), len(held))
