"""A model request's record names what it carried, block by block (Initiative BF).

The transcript said how many messages a request resent and which tools it
offered, not what its input was spent on: the system prompt, the tool schemas,
the project memory, the specification, the harness's notes or the conversation.
Without that, no change aimed at the input (a prefix-cache discipline, a
bounded fix cycle, a sliced specification) could say what it moved.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents import project_memory
from app.observability import transcript

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "loop"


def _kpi():
    spec = importlib.util.spec_from_file_location("loop_kpi_bf", ROOT / "kpi.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MEMORY = "[Project memory: the files.]\n\n=== docs/technical_specification.md ===\nSPEC IN MEMORY\n=== app/main.py ===\ncode\n"
REQUEST = "Build your part.\n\n--- The specification for your files: build exactly to it ---\nTHE SPEC\n\n--- Your work order ---\nwrite it\n"


def _conversation():
    opening = project_memory._with_memory([HumanMessage(content=REQUEST)], MEMORY)[0]
    return [
        SystemMessage(content="You are a specialist."),
        opening,
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "a"}, "id": "c1"}]),
        ToolMessage(content="contents of a", tool_call_id="c1"),
        HumanMessage(content="The workspace as it stands now:\n  a (3 lines)"),
        HumanMessage(content="[A note from the harness: answer now.]"),
    ]


def test_the_memory_says_how_much_of_the_opening_request_it_is():
    opening = project_memory._with_memory([HumanMessage(content=REQUEST)], MEMORY)[0]

    assert opening.additional_kwargs[transcript.MEMORY_CHARS] == len(MEMORY) + 2
    assert opening.content.endswith(REQUEST)


def test_every_block_is_named_and_the_sizes_add_up_to_the_request():
    whole = transcript._messages_of(_conversation())
    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]

    blocks = transcript.prompt_blocks(whole, {"invocation_params": {"tools": tools}})

    assert {"system", "tool_schemas", "project_memory", "specification", "request",
            "conversation", "workspace", "notes"} <= set(blocks)
    carried = sum(len(transcript._text_of(m["content"])) for m in whole)
    carried += sum(len(transcript.json.dumps(m["tool_calls"], default=str)) for m in whole if m.get("tool_calls"))
    assert sum(v for k, v in blocks.items() if k != "tool_schemas") == carried
    # The specification is counted wherever it sits: in the memory and in the request.
    assert blocks["specification"] >= len("SPEC IN MEMORY") + len("THE SPEC")


def test_the_request_record_carries_its_blocks(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(transcript, "record", lambda run, stage, kind, **fields: recorded.append({"kind": kind, **fields}))
    callback = transcript.build_transcript_callback("run-x", "specialist_backend_0")

    callback.on_chat_model_start({"name": "m"}, [_conversation()], invocation_params={"tools": []})

    assert recorded and recorded[0]["kind"] == "model_request"
    assert recorded[0]["blocks"]["project_memory"] > 0


def test_the_kpis_report_each_block_s_share_and_misses_after_a_tool_change():
    kpi = _kpi()
    records = [
        {"at": "2026-10-19T00:00:00+00:00", "stage": "s", "kind": "model_request",
         "tools": ["a", "b"], "blocks": {"system": 100, "conversation": 300}},
        {"at": "2026-10-19T00:00:05+00:00", "stage": "s", "kind": "model_response",
         "usage": {"input_tokens": 100, "output_tokens": 10, "input_token_details": {"cache_read": 0}}},
        {"at": "2026-10-19T00:00:06+00:00", "stage": "s", "kind": "model_request",
         "tools": ["a"], "blocks": {"system": 100, "conversation": 500}},
        {"at": "2026-10-19T00:00:09+00:00", "stage": "s", "kind": "model_response",
         "usage": {"input_tokens": 150, "output_tokens": 10, "input_token_details": {"cache_read": 20}}},
    ]

    got = kpi.kpis(records)

    assert abs(got["prompt_block_share_system"] - 0.2) < 0.01
    assert abs(got["prompt_block_share_conversation"] - 0.8) < 0.01
    assert got["cache_miss_after_tool_change"] == 1


def test_a_record_from_before_blocks_were_named_reports_no_share():
    got = _kpi().kpis([{"at": "2026-10-19T00:00:00+00:00", "stage": "s", "kind": "model_request", "tools": ["a"]}])

    assert not any(key.startswith("prompt_block_share_") for key in got)


def test_an_opening_request_in_several_messages_is_all_request():
    """Measured live: an architect's opening turn came as several human messages,
    and all but the first were counted as conversation."""
    whole = transcript._messages_of([
        SystemMessage(content="You are the architect."),
        HumanMessage(content="Write the specification."),
        HumanMessage(content="--- Original uploaded documents ---\n" + "brief " * 100),
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"file_path": "a"}, "id": "c1"}]),
        ToolMessage(content="contents", tool_call_id="c1"),
    ])

    blocks = transcript.prompt_blocks(whole, {})

    assert blocks["request"] > 600
    assert blocks["conversation"] < 100


def test_the_specialists_advice_is_not_counted_as_the_specification():
    text = ("--- What the specialists advise, before you write the specification ---\n" + "advice " * 50
            + "\n--- Approved technical specification (/docs/technical_specification.md) ---\nTHE SPEC\n")

    assert transcript._specification_in(text) == len(text) - text.index("--- Approved technical")
