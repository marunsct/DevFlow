"""An object a tool's schema wants, sent as a string of JSON, is the object.

Measured on one run's tools-and-models stage: its answer's `technology_stack`
arrived as a JSON string five times running, each refusal answered with "I'll
resend it as an object" and the same string - about 12,000 output tokens and
2.5 minutes an attempt.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.agents.tools_models import ToolsAndModelsOutput
from app.models import CompatibleChatOpenAI
from app.models.tool_arguments import with_structure_decoded

STACK = {"language": "TypeScript", "framework": "Hono", "database": "JSON file", "testing_framework": "vitest"}


def _parameters(schema):
    return convert_to_openai_tool(schema)["function"]["parameters"]


def test_a_nested_object_sent_as_a_string_is_decoded_and_validates():
    sent = {"frameworks": [], "technology_stack": json.dumps(STACK), "open_questions": ["None"]}

    decoded = with_structure_decoded(sent, _parameters(ToolsAndModelsOutput))

    assert ToolsAndModelsOutput.model_validate(decoded).technology_stack.framework == "Hono"
    assert decoded["open_questions"] == ["None"]


def test_a_list_sent_as_a_string_is_decoded_and_strings_are_left_alone():
    parameters = _parameters(ToolsAndModelsOutput)

    decoded = with_structure_decoded({"open_questions": '["a", "b"]', "frameworks": "not json"}, parameters)

    assert decoded["open_questions"] == ["a", "b"]
    assert decoded["frameworks"] == "not json", "what does not parse is the schema's to refuse"
    text = {"type": "object", "properties": {"note": {"type": "string"}}}
    assert with_structure_decoded({"note": '{"a": 1}'}, text) == {"note": '{"a": 1}'}, "a string the schema allows stays one"


def test_the_model_client_decodes_the_answer_tool_s_arguments(monkeypatch):
    from langchain_openai import ChatOpenAI

    model = CompatibleChatOpenAI(model="m", base_url="http://localhost:1/v1", api_key="k", max_retries=1)
    reply = AIMessage(content="", tool_calls=[{
        "name": "ToolsAndModelsOutput", "id": "c1", "args": {"technology_stack": json.dumps(STACK)},
    }])
    monkeypatch.setattr(ChatOpenAI, "_generate", lambda self, *a, **k: ChatResult(generations=[ChatGeneration(message=reply)]))

    result = model._generate([], tools=[convert_to_openai_tool(ToolsAndModelsOutput)])

    assert result.generations[0].message.tool_calls[0]["args"]["technology_stack"]["language"] == "TypeScript"


def test_only_calls_to_a_tool_with_a_schema_are_changed():
    from app.models.tool_arguments import decode_structured_arguments

    calls = [{"name": "other", "id": "a", "args": {"technology_stack": json.dumps(STACK)}}]
    result = ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])

    decode_structured_arguments(result, [convert_to_openai_tool(ToolsAndModelsOutput)])

    assert isinstance(result.generations[0].message.tool_calls[0]["args"]["technology_stack"], str)
    assert decode_structured_arguments(result, None) is result


def test_prose_where_a_list_of_strings_is_wanted_is_one_item_per_line():
    """One run's specification sent eleven list fields as paragraphs, and every one was refused."""
    from app.agents.principal_architect import TechnicalSpecificationOutput

    sent = {"product_scope": "Notes.", "component_boundaries": "\nSix modules:\n- notes-api/src/app.ts routes\n2. notes-api/src/store.ts keeps notes\n\n"}

    decoded = with_structure_decoded(sent, _parameters(TechnicalSpecificationOutput))

    assert decoded["component_boundaries"] == ["Six modules:", "notes-api/src/app.ts routes", "notes-api/src/store.ts keeps notes"]
    assert TechnicalSpecificationOutput.model_validate(decoded).product_scope == "Notes."
    objects = {"type": "object", "properties": {"stack": {"type": "array", "items": {"type": "object"}}}}
    assert with_structure_decoded({"stack": "a\nb"}, objects) == {"stack": "a\nb"}, "only lists of strings"
