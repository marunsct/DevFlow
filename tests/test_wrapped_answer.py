"""An answer the model put inside a single key.

One run's `specialist_testing` sent

    {"SpecialistOutput": {"changed_files": [...], "decisions": [...], ...}}

at 16:34:00, again at 16:34:16, and was still sending it at 16:34:33 after
three corrections. Every one was rejected, so `settled_answer` could not
recognise an answer and the stage went on. The log read

    Stage specialist_testing sent an answer that does not satisfy its schema
    (SpecialistOutput); returning the validation errors

naming the wrapper as though it were a field, because to pydantic that is what
it is: one unexpected key, and every required field missing. The correction
listed each missing field - true, and useless, because the model had written
all of them one level down.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from app.agents.settled_answer import _answer_in, _why_it_was_not_accepted
from app.agents.specialists import SpecialistOutput
from app.agents.wrapped_answer import unwrapped

ANSWER = {
    "changed_files": ["simple-to-do-list-app/app.mjs"],
    "decisions": ["Exported default and adjusted import syntax"],
    "tests": ["app.test.mjs"],
    "verification": [],
}


@pytest.mark.parametrize(
    "key", ["SpecialistOutput", "specialist_output", "specialistOutput", "SPECIALISTOUTPUT"]
)
def test_the_schema_name_as_a_wrapper_is_removed(key: str) -> None:
    assert unwrapped({key: ANSWER}, SpecialistOutput) == ANSWER


@pytest.mark.parametrize("key", ["response", "output", "answer", "result", "data"])
def test_a_generic_wrapper_carrying_the_fields_is_removed(key: str) -> None:
    """The value is the answer whatever the wrapper is called."""
    assert unwrapped({key: ANSWER}, SpecialistOutput) == ANSWER


def test_an_unwrapped_answer_is_untouched() -> None:
    assert unwrapped(ANSWER, SpecialistOutput) == ANSWER


def test_an_answer_with_one_real_field_is_untouched() -> None:
    """A single top-level key is not, on its own, a wrapper."""
    payload = {"changed_files": ["a.js"]}

    assert unwrapped(payload, SpecialistOutput) == payload


def test_a_single_key_that_means_nothing_to_the_schema_is_untouched() -> None:
    payload = {"note": {"a": 1, "b": 2, "c": 3}}

    assert unwrapped(payload, SpecialistOutput) == payload


def test_a_schema_that_owns_the_key_is_never_unwrapped() -> None:
    """A schema with a field called `response` must not be unwrapped out of its
    own answer."""

    class Reply(BaseModel):
        response: dict

    payload = {"response": {"a": 1}}

    assert unwrapped(payload, Reply) == payload


@pytest.mark.parametrize("payload", [None, [], "text", {}, {"a": "not an object"}])
def test_what_is_not_a_wrapped_object_comes_back_as_it_went_in(payload) -> None:
    assert unwrapped(payload, SpecialistOutput) == payload


# --- and the reason it exists ---------------------------------------------


def test_the_measured_message_is_now_an_answer() -> None:
    message = AIMessage(content=json.dumps({"SpecialistOutput": ANSWER}), id="m")

    found = _answer_in(message, SpecialistOutput)

    assert found is not None
    assert found.changed_files == ["simple-to-do-list-app/app.mjs"]


def test_it_is_no_longer_diagnosed_as_a_wall_of_missing_fields() -> None:
    message = AIMessage(content=json.dumps({"SpecialistOutput": ANSWER}), id="m")

    assert _why_it_was_not_accepted(message, SpecialistOutput) == ""


def test_a_wrapped_answer_that_is_genuinely_wrong_is_still_diagnosed() -> None:
    """Unwrapping must not turn a bad answer into an accepted one."""
    broken = dict(ANSWER, verification=[{"command": ["npm", "test"]}])
    message = AIMessage(content=json.dumps({"SpecialistOutput": broken}), id="m")

    why = _why_it_was_not_accepted(message, SpecialistOutput)

    assert "exit_code" in why
