"""An answer cut at the reply cap is read without what the model wrote past its end (LF.1607).

Measured on one run: an advisor's answer call ended at its 16,000-token cap. Its last recommendation ran several more
together in one string, then the model's own call markup, then ` } ]` over and over to the cap. The lenient reading
closed the open string and list, and the call was taken whole: a 29,732-character recommendation, all of it in the
next stage's request. The fixtures are that reply's shape, shortened.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

from app.agents.settled_answer import _answer_in
from app.agents.specialist_advice import SpecialistAdvice
from app.models.tool_arguments import decode_structured_arguments

WHOLE = [
    "AC-1: Send POST /notes with body {title:Test,body:Content} and assert response.status == 201.",
    "AC-2: After creating two notes, send GET /notes and assert response.status == 200 and both are listed.",
    "AC-3: Create a note, send GET /notes/{id} and assert response.status == 200 with its title and body.",
]
RUN_ON = (
    "AC-4: Send GET /notes/99999 and assert response.status == 404; send GET /notes/{validId} and assert 200 with "
    "the note body {id:<int>,title:<string>,body:<string>}., "
    "AC-5: Send PUT /notes/99999 and assert response.status == 404, confirming the not-found path., "
    "AC-6: Send DELETE /notes/{validId} twice and assert 204, then 404."
)
#: The model's own call markup, then a closing pair written to the cap.
RUNAWAY = "]</parameter></function></tool_call> --- End of pasted response ---<tool_call>] }</tool_call>" + " } ]" * 300


def _cut_off_call(arguments: str, name: str = "SpecialistAdvice") -> ChatResult:
    """A reply that ended at the cap with one call whose argument text was left open (an invalid call)."""
    message = AIMessage(
        content="",
        response_metadata={"finish_reason": "length"},
        invalid_tool_calls=[{"name": name, "args": arguments, "id": "call_1", "error": "Unterminated string",
                             "type": "invalid_tool_call"}],
    )
    return ChatResult(generations=[ChatGeneration(message=message, generation_info={"finish_reason": "length"})])


def _recommendations(result: ChatResult) -> list[str]:
    (call,) = result.generations[0].message.tool_calls
    return call["args"]["recommendations"]


def _open_call(entries: list[str], last: str) -> str:
    """The argument text as the server sent it: the last string never closed."""
    return '{"recommendations": [' + "".join(json.dumps(e) + ", " for e in entries) + '"' + last


def test_a_cut_off_answer_keeps_the_entries_it_ran_together_and_none_of_the_loop() -> None:
    result = _cut_off_call(_open_call(WHOLE, RUN_ON + RUNAWAY))

    decode_structured_arguments(result, [convert_to_openai_tool(SpecialistAdvice)])

    assert _recommendations(result) == [
        *WHOLE,
        "AC-4: Send GET /notes/99999 and assert response.status == 404; send GET /notes/{validId} and assert 200 "
        "with the note body {id:<int>,title:<string>,body:<string>}.",
        "AC-5: Send PUT /notes/99999 and assert response.status == 404, confirming the not-found path.",
        "AC-6: Send DELETE /notes/{validId} twice and assert 204, then 404.",
    ]


def test_a_cut_off_answer_whose_tail_was_cut_is_recorded_as_salvaged() -> None:
    """The transcript's `salvaged` is read from the generation: the audit counts it, not only "cut at the cap"."""
    result = _cut_off_call(_open_call(WHOLE, RUN_ON + RUNAWAY))

    decode_structured_arguments(result, [convert_to_openai_tool(SpecialistAdvice)])

    assert result.generations[0].generation_info["harness_salvaged"] == "runaway_tail_cut"


def test_entries_past_the_schema_s_limit_stay_joined_in_its_last_entry() -> None:
    """Taken apart past the list's limit, the answer would be refused; joined, nothing written is lost."""
    nine = [f"AC-{n}: Assert the case numbered {n} answers as specified." for n in range(1, 10)]
    result = _cut_off_call(_open_call(nine, "AC-10: Assert ten., AC-11: Assert eleven., AC-12: Assert twelve." + RUNAWAY))

    decode_structured_arguments(result, [convert_to_openai_tool(SpecialistAdvice)])

    assert _recommendations(result) == [*nine, "AC-10: Assert ten.; AC-11: Assert eleven.; AC-12: Assert twelve."]
    SpecialistAdvice.model_validate({"recommendations": _recommendations(result)})


def test_a_run_on_entry_not_numbered_like_the_ones_before_is_kept_whole_without_its_loop() -> None:
    plain = ["Test the create route end to end.", "Test the list route with two notes."]
    last = "Test the fetch route for a missing id, and test the update route for a missing id too."
    result = _cut_off_call(_open_call(plain, last + RUNAWAY))

    decode_structured_arguments(result, [convert_to_openai_tool(SpecialistAdvice)])

    assert _recommendations(result) == [*plain, last]


def test_a_cut_off_answer_with_no_runaway_is_read_as_before() -> None:
    """An entry cut part way through a sentence is not runaway: nothing of it is cut."""
    result = _cut_off_call(_open_call(WHOLE, "AC-4: Send GET /notes/99999 and assert response.status == 4"))

    decode_structured_arguments(result, [convert_to_openai_tool(SpecialistAdvice)])

    assert _recommendations(result) == [*WHOLE, "AC-4: Send GET /notes/99999 and assert response.status == 4"]


class Review(BaseModel):
    verdict: str
    summary: str


def test_a_text_field_that_loops_to_the_cap_keeps_what_came_before_the_loop() -> None:
    arguments = '{"verdict": "approved", "summary": "Every route answers as specified.' + "0" * 600

    result = _cut_off_call(arguments, name="Review")
    decode_structured_arguments(result, [convert_to_openai_tool(Review)])

    (call,) = result.generations[0].message.tool_calls
    assert call["args"] == {"verdict": "approved", "summary": "Every route answers as specified."}


def test_an_answer_written_as_text_and_cut_at_the_cap_is_read_without_what_ran_on() -> None:
    text = _open_call(WHOLE, "AC-4: Send GET /notes/99999 and assert 404." + RUNAWAY)

    answer = _answer_in(AIMessage(content=text, response_metadata={"finish_reason": "length"}), SpecialistAdvice)

    assert answer is not None
    assert answer.recommendations == [*WHOLE, "AC-4: Send GET /notes/99999 and assert 404."]
