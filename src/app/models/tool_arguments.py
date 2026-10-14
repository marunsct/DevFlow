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


def _repaired(value: Any, schema: Any, definitions: dict[str, Any], depth: int) -> Any:
    if depth > _MOST_DEPTH:
        return value
    options = _alternatives(schema, definitions)
    if not options:
        return value
    wanted = set().union(*(_types(option) for option in options))
    if isinstance(value, str) and "string" not in wanted and wanted & {"object", "array"}:
        try:
            decoded = json.loads(value)
        except ValueError:
            return _as_lines(value, options, definitions)
        if (isinstance(decoded, dict) and "object" in wanted) or (isinstance(decoded, list) and "array" in wanted):
            value = decoded
        else:
            return value
    if isinstance(value, dict):
        for option in options:
            properties = option.get("properties")
            if isinstance(properties, dict):
                return {
                    key: _repaired(item, properties[key], definitions, depth + 1) if key in properties else item
                    for key, item in value.items()
                }
        return value
    if isinstance(value, list):
        for option in options:
            if "items" in option:
                return [_repaired(item, option["items"], definitions, depth + 1) for item in value]
        return value
    return value


def with_structure_decoded(arguments: Any, parameters: Any) -> Any:
    """`arguments` with each JSON string decoded where `parameters` wants an object or a list."""
    if not isinstance(arguments, dict) or not isinstance(parameters, dict):
        return arguments
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
        parsed = _parsed_leniently(call.get("args")) if name in parameters else None
        if parsed is None:
            kept.append(call)
            continue
        message.tool_calls.append({"name": name, "args": parsed, "id": call.get("id"), "type": "tool_call"})
        logger.warning("A call to %s whose arguments were not strict JSON was read leniently", name)
    message.invalid_tool_calls = kept


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
            schema = parameters.get(str(call.get("name") or ""))
            if schema is not None:
                call["args"] = with_structure_decoded(call.get("args"), schema)
    return result
