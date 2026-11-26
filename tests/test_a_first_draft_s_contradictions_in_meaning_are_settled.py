"""A first draft's statements that contradict each other in different words are found by one call and settled before
its first review (plan PA.7, the rest).

Measured on a stored small run: its review raised as blocking `data_flows` "If the file contains malformed JSON, it
logs an error and exits." against `reliability_and_observability` "corrupted files result in starting with an empty
store rather than crashing." The two share no value, so the mechanical pass, which compares what sections repeat,
could not find them. The specification below is that run's first draft as it was stored.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from workflow_nodes import a_specification

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CAPTURED = (Path(__file__).parent / "captured"
            / "technical-specification-a-malformed-file-stops-it-and-starts-it-empty.md").read_text(encoding="utf-8")

EXITS = ("Startup Flow: The service reads DATA_DIR from environment variables. It ensures the directory exists. It "
         "attempts to read 'notes.json' from DATA_DIR. If the file is missing or empty, it initializes an in-memory "
         "store as an empty array. If the file contains malformed JSON, it logs an error and exits. If valid, it "
         "parses the JSON array into memory.")
STARTS_EMPTY = ("On startup, stored data is validated against the expected schema (id: integer, title: string, body: "
                "string); non-conforming records are stripped or coerced to maintain internal consistency, and "
                "corrupted files result in starting with an empty store rather than crashing.")
SETTLED = ("On startup, stored data is validated against the expected schema (id: integer, title: string, body: "
           "string); non-conforming records are stripped or coerced, and a file of malformed JSON stops the service "
           "with a logged error.")


def _the_stored_draft():
    """The stored specification's sections, as the architect's answer holds them."""
    from app.agents.principal_architect import TechnicalSpecificationOutput

    fields = TechnicalSpecificationOutput.model_fields
    sections: dict[str, list[str]] = {}
    name = ""
    for line in CAPTURED.splitlines():
        if line.startswith("## "):
            name = re.sub(r"\W+", "_", line[3:].strip().lower()).strip("_").replace("advice_and_", "advice_")
            continue
        if name in fields and line.startswith("- "):
            sections.setdefault(name, []).append(line[2:].strip())
    scope = " ".join(sections.pop("product_scope", []))
    return a_specification(product_scope=scope, **sections)


class _Model(BaseChatModel):
    """The model endpoint: names the two startup statements as contradicting, then rewrites the second."""

    asked: list = []

    @property
    def _llm_type(self) -> str:
        return "stand-in"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        asked = str(messages[-1].content)
        self.asked.append(asked)
        if "--- The statements ---" in asked:
            numbers = [int(m.group(1)) for text in (EXITS, STARTS_EMPTY)
                       for m in [re.search(r"\[(\d+)\] `[a-z_]+`: " + re.escape(text[:60]), asked)] if m]
            reply = {"contradictions": [{"statements": numbers, "about": "a malformed data file at startup"}]}
        else:
            reply = {"lines": [{"section": "reliability_and_observability", "old": STARTS_EMPTY, "new": SETTLED}]}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps(reply)))])


def test_the_mechanical_pass_cannot_find_them():
    from app.graph.specification_consistency import disagreements

    shown = {line for entry in disagreements(_the_stored_draft()) for _, line in entry.lines}

    assert EXITS not in shown and STARTS_EMPTY not in shown


def test_two_statements_that_disagree_in_different_words_are_settled_before_the_review():
    from app.graph.specification_consistency import settled

    model = _Model()
    model.asked = []

    specification = settled(_the_stored_draft(), model)

    assert SETTLED in specification.reliability_and_observability
    assert STARTS_EMPTY not in specification.reliability_and_observability
    assert EXITS in specification.data_flows
    settle = [text for text in model.asked if "written in separate parts" in text and "--- The statements" not in text]
    assert len(settle) == 1 and EXITS in settle[0] and STARTS_EMPTY in settle[0]


def test_a_short_draft_is_left_to_its_reviewer():
    from app.graph.specification_consistency import settled

    model = _Model()
    model.asked = []

    settled(a_specification(data_flows=[EXITS], reliability_and_observability=[STARTS_EMPTY]), model)

    assert model.asked == []


def test_the_request_names_no_product_and_no_control():
    from app.graph.specification_consistency import Disagreement, settle_request
    from app.graph.specification_meaning import find_request

    asked = find_request([("data_flows", "a line")]) + settle_request(
        [Disagreement("meaning", "x", "y", [("data_flows", "a line")])])

    assert "cannot both be true" in asked
    assert not BANNED.search(asked)
