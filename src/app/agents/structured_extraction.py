"""A stage's answer given in prose is asked again with nothing but its schema allowed (behind `STRUCTURED_EXTRACTION`).

A stage gives its answer by calling its answer tool. On the OpenAI API that
call can be forced; on llama.cpp it cannot - a named `tool_choice` is read as
`auto`, and measured against one model even `"required"` with one tool
offered was answered "Hi! How can I help you?" three times of three. Under
`auto` a prose answer is legal, so a model that writes its answer as text was
told why and asked again, and wrote text again.

What a llama.cpp server does enforce is `response_format` with a JSON schema
sent with no tools: its grammar covers the whole schema from the first token
after the model's reasoning. So when a stage's reply was prose where its
answer was due, the conversation is sent once more with no tools and the
answer's schema as the response format, and the object that comes back is
handed to the stage as the call of its answer tool - the answer the stage was
asked for, in the shape it was asked for. A server that refuses the schema
(its converter does not take every JSON Schema keyword), or an object that
does not validate, leaves the stage to the reminder it had before.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `STRUCTURED_EXTRACTION` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The most the asked-again answer may run: an answer, a whole file in it included.
REPLY_TOKENS = 16_000
#: Said at the end of the asked-again request.
ASK = ("Give your answer now, as one JSON object in the answer's schema and nothing else - every field the type "
       "the schema names, from what this conversation has established.")


def enabled() -> bool:
    return is_on("STRUCTURED_EXTRACTION", ON_BY_DEFAULT)


def _the_object_in(text: str) -> dict | None:
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        found = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def answered_in_its_schema(request: Any, schema: Any, stage_name: str = "") -> Any | None:
    """The stage's answer, asked of its conversation with only its schema allowed; None when it cannot be had. Never raises."""
    if not enabled() or not isinstance(schema, type):
        return None
    try:
        from langchain.agents.middleware.types import ModelResponse
        from langchain_core.messages import AIMessage, HumanMessage

        model = getattr(request, "model", None)
        client = getattr(getattr(model, "root_client", None), "chat", None)
        if client is None or not hasattr(model, "_get_request_payload"):
            return None
        system = getattr(request, "system_message", None)
        messages = [*([system] if system is not None else []), *list(getattr(request, "messages", None) or []),
                    HumanMessage(content=ASK)]
        payload = model._get_request_payload(messages)
        for key in ("tools", "tool_choice", "parallel_tool_calls"):
            payload.pop(key, None)
        payload["stream"] = False
        payload["max_tokens"] = min(int(payload.get("max_tokens") or REPLY_TOKENS), REPLY_TOKENS)
        payload["response_format"] = {"type": "json_schema", "json_schema": {
            "name": schema.__name__, "schema": schema.model_json_schema()}}
        response = client.completions.create(**payload)
        data = response if isinstance(response, dict) else response.model_dump(warnings=False)
        content = str((((data.get("choices") or [{}])[0] or {}).get("message") or {}).get("content") or "")
        found = _the_object_in(content)
        if found is None:
            logger.info("Stage %s's answer asked again in its schema came back with no object", stage_name or "?")
            return None
        from app.agents.settled_answer import validated_leniently

        answer = validated_leniently(schema, found)
        arguments = answer.model_dump(mode="json") if hasattr(answer, "model_dump") else found
        logger.info("Stage %s answered in prose; its answer was asked again in its schema and given", stage_name or "?")
        return ModelResponse(result=[AIMessage(content="", tool_calls=[
            {"name": schema.__name__, "args": arguments, "id": f"call_{uuid.uuid4().hex[:12]}", "type": "tool_call"}])])
    except Exception as error:  # noqa: BLE001 - the reminder it had before
        logger.info("Stage %s's answer could not be asked again in its schema: %s: %s", stage_name or "?",
                    type(error).__name__, str(error)[:200])
        return None


__all__ = ["ASK", "ON_BY_DEFAULT", "REPLY_TOKENS", "answered_in_its_schema", "enabled"]
