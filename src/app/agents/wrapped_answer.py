"""Unwrap an answer the model put inside a single key.

Small models routinely emit the structured response wrapped in one key named
after the schema, or after the idea of an answer:

    {"SpecialistOutput": {"changed_files": [...], "decisions": [...], ...}}
    {"response": {"status": "accepted", ...}}

 Every one was rejected, so `settled_answer` could not
recognise an answer, so the stage went on. The log for it reads

    Stage specialist_testing sent an answer that does not satisfy its schema
    (SpecialistOutput); returning the validation errors

which names the wrapper as though it were a field, because to pydantic that is
what it is: one unexpected key, and every required field missing.

The correction those attempts received listed each missing field, which is true
and useless - the model had written all of them, one level down. Nothing in the
message said "you have wrapped it", because nothing looked.

Unwrapping is safe when it is unambiguous, and that is the only time it is
done: a single top-level key whose value is an object that carries the
schema's own field names. An object that merely has one key is left alone.
"""

from __future__ import annotations

import re
from typing import Any

#: How much of the inner object must be the schema's own fields before a single
#: key is certainly a wrapper. Two fields, or half of what is there.
MIN_FIELDS_IN_COMMON = 2


def _schema_fields(schema: Any) -> set[str]:
    fields = getattr(schema, "model_fields", None)
    if isinstance(fields, dict):
        return set(fields)
    return set()


def _normalised(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def unwrapped(payload: Any, schema: Any) -> Any:
    """`payload` with a single wrapper key removed, or `payload` unchanged.

    Two ways to be sure, either of which is enough:

    - the key is the schema's own name, however it is spelled
      (`SpecialistOutput`, `specialist_output`, `specialistOutput`);
    - the value is an object carrying the schema's fields, which is what a
      wrapper called `response` or `output` or `answer` contains.
    """
    if not isinstance(payload, dict) or len(payload) != 1:
        return payload
    (key, value), = payload.items()
    if not isinstance(value, dict) or not value:
        return payload

    fields = _schema_fields(schema)
    if fields and key in fields:
        # A schema with one field called `response` would be unwrapped out of
        # its own answer. Never touch a key the schema actually declares.
        return payload

    name = _normalised(getattr(schema, "__name__", ""))
    if name and _normalised(key) == name:
        return value

    if not fields:
        return payload
    shared = fields & set(value)
    if len(shared) >= MIN_FIELDS_IN_COMMON or (shared and len(shared) >= len(value) / 2):
        return value
    return payload


__all__ = ["MIN_FIELDS_IN_COMMON", "unwrapped"]
